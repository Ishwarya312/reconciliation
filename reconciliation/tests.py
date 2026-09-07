import pytz
from datetime import datetime
from decimal import Decimal
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import DataFile, ReconciliationRun, LedgerRecord, StatementRecord, MatchResult
from .engine import run_reconciliation

class ReconciliationEngineTests(TestCase):
    def setUp(self):
        # Create Dummy Data Files
        self.ledger_file = DataFile.objects.create(file=SimpleUploadedFile("l.csv", b""), file_type="LEDGER")
        self.stmt_file = DataFile.objects.create(file=SimpleUploadedFile("s.csv", b""), file_type="STATEMENT")
        
        self.dt = datetime(2025, 7, 1, 9, 15, 0, tzinfo=pytz.UTC)

    def test_exact_match(self):
        # 1 Ledger and 1 Statement with same ID
        ledger = LedgerRecord.objects.create(
            source_file=self.ledger_file, transaction_id="T-1", instrument="BTC-USD", 
            side="BUY", quantity=Decimal("1"), price=Decimal("100"), amount=Decimal("100"), 
            executed_at=self.dt, status="SETTLED"
        )
        stmt = StatementRecord.objects.create(
            source_file=self.stmt_file, transaction_id="T-1", instrument="BTC-USD", 
            side="BUY", quantity=Decimal("1"), price=Decimal("100"), amount=Decimal("100"), 
            executed_at=self.dt, status="SETTLED"
        )
        
        run = run_reconciliation(self.ledger_file, self.stmt_file)
        
        results = MatchResult.objects.filter(run=run)
        self.assertEqual(results.count(), 1)
        self.assertEqual(results.first().match_type, 'EXACT')
        self.assertEqual(results.first().ledger_record, ledger)
        self.assertEqual(results.first().statement_record, stmt)

    def test_fuzzy_match(self):
        # Same instrument, side, amount, but different ID and 1 hour drift
        ledger = LedgerRecord.objects.create(
            source_file=self.ledger_file, transaction_id="T-1", instrument="ETH-USD", 
            side="SELL", quantity=Decimal("10"), price=Decimal("20"), amount=Decimal("200"), 
            executed_at=self.dt, status="SETTLED"
        )
        # Statement has different ID and is executed 60 mins later
        dt_drift = datetime(2025, 7, 1, 10, 15, 0, tzinfo=pytz.UTC)
        stmt = StatementRecord.objects.create(
            source_file=self.stmt_file, transaction_id="EXT-1", instrument="ETH-USD", 
            side="SELL", quantity=Decimal("10"), price=Decimal("20"), amount=Decimal("200"), 
            executed_at=dt_drift, status="SETTLED"
        )
        
        run = run_reconciliation(self.ledger_file, self.stmt_file)
        
        results = MatchResult.objects.filter(run=run)
        self.assertEqual(results.count(), 1)
        self.assertEqual(results.first().match_type, 'FUZZY')
        self.assertEqual(results.first().time_discrepancy_seconds, 3600)

    def test_unmatched_records(self):
        # Ledger without statement
        LedgerRecord.objects.create(
            source_file=self.ledger_file, transaction_id="T-2", instrument="SOL-USD", 
            side="BUY", quantity=Decimal("1"), price=Decimal("10"), amount=Decimal("10"), 
            executed_at=self.dt, status="SETTLED"
        )
        # Statement without ledger
        StatementRecord.objects.create(
            source_file=self.stmt_file, transaction_id="EXT-2", instrument="ADA-USD", 
            side="SELL", quantity=Decimal("1"), price=Decimal("1"), amount=Decimal("1"), 
            executed_at=self.dt, status="SETTLED"
        )
        
        run = run_reconciliation(self.ledger_file, self.stmt_file)
        
        results = MatchResult.objects.filter(run=run)
        self.assertEqual(results.count(), 2)
        
        ledger_result = results.get(match_type='UNMATCHED_LEDGER')
        self.assertIsNone(ledger_result.statement_record)
        
        stmt_result = results.get(match_type='UNMATCHED_STATEMENT')
        self.assertIsNone(stmt_result.ledger_record)
