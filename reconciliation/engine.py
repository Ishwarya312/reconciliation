import csv
from decimal import Decimal
from datetime import datetime, timedelta
from typing import List, Tuple
from django.utils.dateparse import parse_datetime
import pytz

from .models import (
    DataFile, LedgerRecord, StatementRecord, 
    ReconciliationRun, MatchResult
)

# Constants for fuzzy matching
TIME_TOLERANCE_MINUTES = 120
AMOUNT_TOLERANCE_PERCENT = Decimal('0.02') # 2%

def normalize_side(side: str) -> str:
    side = side.upper().strip()
    if side in ['B', 'BUY']:
        return 'BUY'
    if side in ['S', 'SELL']:
        return 'SELL'
    return side

def parse_ledger_date(date_str: str) -> datetime:
    # Example: 2025-07-01T09:15:00Z
    try:
        dt = parse_datetime(date_str)
        if not dt:
            dt = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%SZ')
            dt = dt.replace(tzinfo=pytz.UTC)
        return dt
    except ValueError:
        return datetime.now(pytz.UTC)

def parse_statement_date(date_str: str) -> datetime:
    # Example: 2025-07-01 09:15:00
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        return dt.replace(tzinfo=pytz.UTC)
    except ValueError:
        return datetime.now(pytz.UTC)

def load_ledger_file(data_file: DataFile):
    content = data_file.file.read().decode('utf-8').splitlines()
    reader = csv.DictReader(content)
    
    records = []
    for row in reader:
        if row.get('state', '').upper() == 'CANCELLED':
            continue
            
        records.append(LedgerRecord(
            source_file=data_file,
            transaction_id=row['trade_id'],
            executed_at=parse_ledger_date(row['traded_at']),
            instrument=row['instrument'],
            side=normalize_side(row['side']),
            quantity=Decimal(row['quantity'] or 0),
            price=Decimal(row['price'] or 0),
            amount=Decimal(row['gross_amount'] or 0),
            status=row['state']
        ))
        
    LedgerRecord.objects.bulk_create(records, batch_size=500)
    data_file.processed = True
    data_file.save()

def load_statement_file(data_file: DataFile):
    content = data_file.file.read().decode('utf-8').splitlines()
    reader = csv.DictReader(content)
    
    records = []
    for row in reader:
        if row.get('status', '').upper() == 'CANCELLED':
            continue
            
        records.append(StatementRecord(
            source_file=data_file,
            transaction_id=row['reference'],
            executed_at=parse_statement_date(row['executed_at']),
            instrument=row['symbol'],
            side=normalize_side(row['direction']),
            quantity=Decimal(row['qty'] or 0),
            price=Decimal(row['unit_price'] or 0),
            amount=Decimal(row['total'] or 0),
            status=row['status']
        ))
        
    StatementRecord.objects.bulk_create(records, batch_size=500)
    data_file.processed = True
    data_file.save()

def calculate_discrepancies(ledger: LedgerRecord, statement: StatementRecord) -> Tuple[Decimal, int]:
    amt_diff = ledger.amount - statement.amount
    time_diff = int(abs((ledger.executed_at - statement.executed_at).total_seconds()))
    return amt_diff, time_diff

def run_reconciliation(ledger_file: DataFile, statement_file: DataFile) -> ReconciliationRun:
    run = ReconciliationRun.objects.create(
        ledger_file=ledger_file,
        statement_file=statement_file
    )
    
    # Fetch previous manual matches to carry them over
    manual_matches = MatchResult.objects.filter(
        match_type='MANUAL',
        ledger_record__transaction_id__in=LedgerRecord.objects.filter(source_file=ledger_file).values('transaction_id')
    )
    manual_pairs = {(m.ledger_record.transaction_id, m.statement_record.transaction_id): m for m in manual_matches if m.ledger_record and m.statement_record}

    # Fetch previous accepted unmatched records
    accepted_unmatched_ledgers = set(MatchResult.objects.filter(
        match_type='UNMATCHED_LEDGER', 
        resolved_by_human=True,
        ledger_record__transaction_id__in=LedgerRecord.objects.filter(source_file=ledger_file).values('transaction_id')
    ).values_list('ledger_record__transaction_id', flat=True))
    
    accepted_unmatched_statements = set(MatchResult.objects.filter(
        match_type='UNMATCHED_STATEMENT', 
        resolved_by_human=True,
        statement_record__transaction_id__in=StatementRecord.objects.filter(source_file=statement_file).values('transaction_id')
    ).values_list('statement_record__transaction_id', flat=True))

    ledgers = list(LedgerRecord.objects.filter(source_file=ledger_file))
    statements = list(StatementRecord.objects.filter(source_file=statement_file))
    
    matches = []
    matched_statement_ids = set()
    
    remaining_ledgers = []
    
    # Pass 0: Carry over manual matches and accepted unmatched
    for ledger in ledgers:
        if ledger.transaction_id in accepted_unmatched_ledgers:
            matches.append(MatchResult(
                run=run,
                match_type='UNMATCHED_LEDGER',
                ledger_record=ledger,
                resolved_by_human=True
            ))
            continue

        manual_match_found = False
        for stmt in statements:
            if stmt.transaction_id in accepted_unmatched_statements:
                # We handle statements below
                pass
                
            if (ledger.transaction_id, stmt.transaction_id) in manual_pairs and stmt.id not in matched_statement_ids:
                amt_diff, time_diff = calculate_discrepancies(ledger, stmt)
                matches.append(MatchResult(
                    run=run,
                    match_type='MANUAL',
                    ledger_record=ledger,
                    statement_record=stmt,
                    amount_discrepancy=amt_diff,
                    time_discrepancy_seconds=time_diff,
                    resolved_by_human=True
                ))
                matched_statement_ids.add(stmt.id)
                manual_match_found = True
                break
        
        if not manual_match_found:
            remaining_ledgers.append(ledger)

    ledgers = remaining_ledgers
    remaining_ledgers = []
    
    # Handle accepted unmatched statements
    for stmt in statements:
        if stmt.transaction_id in accepted_unmatched_statements and stmt.id not in matched_statement_ids:
            matches.append(MatchResult(
                run=run,
                match_type='UNMATCHED_STATEMENT',
                statement_record=stmt,
                resolved_by_human=True
            ))
            matched_statement_ids.add(stmt.id)

    # Pass 1: Exact Match by ID
    for ledger in ledgers:
        exact_stmt = next((s for s in statements if s.transaction_id == ledger.transaction_id and s.id not in matched_statement_ids), None)
        
        if exact_stmt:
            amt_diff, time_diff = calculate_discrepancies(ledger, exact_stmt)
            matches.append(MatchResult(
                run=run,
                match_type='EXACT',
                ledger_record=ledger,
                statement_record=exact_stmt,
                amount_discrepancy=amt_diff,
                time_discrepancy_seconds=time_diff
            ))
            matched_statement_ids.add(exact_stmt.id)
        else:
            remaining_ledgers.append(ledger)
            
    # Pass 2: Fuzzy Match
    unmatched_ledgers = []
    for ledger in remaining_ledgers:
        fuzzy_match = None
        for stmt in statements:
            if stmt.id in matched_statement_ids:
                continue
                
            if stmt.instrument == ledger.instrument and stmt.side == ledger.side:
                time_diff_minutes = abs((ledger.executed_at - stmt.executed_at).total_seconds()) / 60
                
                if ledger.amount > 0:
                    amt_diff_percent = abs(ledger.amount - stmt.amount) / ledger.amount
                else:
                    amt_diff_percent = 0 if ledger.amount == stmt.amount else 1
                    
                if time_diff_minutes <= TIME_TOLERANCE_MINUTES and amt_diff_percent <= AMOUNT_TOLERANCE_PERCENT:
                    fuzzy_match = stmt
                    break
                    
        if fuzzy_match:
            amt_diff, time_diff = calculate_discrepancies(ledger, fuzzy_match)
            matches.append(MatchResult(
                run=run,
                match_type='FUZZY',
                ledger_record=ledger,
                statement_record=fuzzy_match,
                amount_discrepancy=amt_diff,
                time_discrepancy_seconds=time_diff
            ))
            matched_statement_ids.add(fuzzy_match.id)
        else:
            unmatched_ledgers.append(ledger)
            
    # Pass 3: Unmatched
    for ledger in unmatched_ledgers:
        matches.append(MatchResult(
            run=run,
            match_type='UNMATCHED_LEDGER',
            ledger_record=ledger
        ))
        
    for stmt in statements:
        if stmt.id not in matched_statement_ids:
            matches.append(MatchResult(
                run=run,
                match_type='UNMATCHED_STATEMENT',
                statement_record=stmt
            ))
            
    MatchResult.objects.bulk_create(matches, batch_size=500)
    
    run.completed_at = datetime.now(pytz.UTC)
    run.save()
    
    return run
