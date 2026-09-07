from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import DataFile, ReconciliationRun, MatchResult, LedgerRecord, StatementRecord
from .serializers import ManualMatchSerializer, AcceptUnmatchedSerializer
from .engine import load_ledger_file, load_statement_file, run_reconciliation

from .tasks import process_global_reconciliation

def dashboard(request):
    runs = ReconciliationRun.objects.all().order_by('-started_at')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'upload_ledger':
            ledger_csv = request.FILES.get('ledger_file')
            if ledger_csv:
                ledger_file = DataFile.objects.create(file=ledger_csv, file_type='LEDGER')
                load_ledger_file(ledger_file)
                messages.success(request, "Ledger file uploaded and loaded successfully.")
                
        elif action == 'upload_statement':
            statement_csv = request.FILES.get('statement_file')
            if statement_csv:
                statement_file = DataFile.objects.create(file=statement_csv, file_type='STATEMENT')
                load_statement_file(statement_file)
                messages.success(request, "Statement file uploaded and loaded successfully.")
                
        elif action == 'run_reconciliation':
            run = ReconciliationRun.objects.create()
            process_global_reconciliation.delay(run.id)
            messages.info(request, f"Global Reconciliation Run #{run.id} started in the background.")
            return redirect('run_details', run_id=run.id)
            
    return render(request, 'reconciliation/dashboard.html', {'runs': runs})

def run_details(request, run_id):
    run = get_object_or_404(ReconciliationRun, id=run_id)
    results = run.results.all().select_related('ledger_record', 'statement_record')
    
    exact_matches = results.filter(match_type='EXACT')
    manual_matches = results.filter(match_type='MANUAL')
    unmatched_ledger = results.filter(match_type='UNMATCHED_LEDGER')
    unmatched_statement = results.filter(match_type='UNMATCHED_STATEMENT')
    
    context = {
        'run': run,
        'results': results,
        'exact_matches': exact_matches,
        'fuzzy_matches': results.filter(match_type='FUZZY'),
        'manual_matches': manual_matches,
        'unmatched_ledger': unmatched_ledger,
        'unmatched_statement': unmatched_statement,
        'ignored_matches': results.filter(match_type='IGNORED'),
        'matched_count': exact_matches.count() + manual_matches.count(),
        'unmatched_count': unmatched_ledger.count() + unmatched_statement.count(),
    }
    return render(request, 'reconciliation/run_details.html', context)

# API Views using DRF
class ReconciliationViewSet(viewsets.ViewSet):
    
    @action(detail=True, methods=['post'])
    def manual_match(self, request, pk=None):
        run = get_object_or_404(ReconciliationRun, pk=pk)
        serializer = ManualMatchSerializer(data=request.data)
        
        if serializer.is_valid():
            ledger_id = serializer.validated_data['ledger_id']
            statement_id = serializer.validated_data['statement_id']
            
            # Find the unmatched records
            ledger_result = get_object_or_404(MatchResult, run=run, match_type='UNMATCHED_LEDGER', ledger_record_id=ledger_id)
            statement_result = get_object_or_404(MatchResult, run=run, match_type='UNMATCHED_STATEMENT', statement_record_id=statement_id)
            
            # Create a new manual match
            MatchResult.objects.create(
                run=run,
                match_type='MANUAL',
                ledger_record=ledger_result.ledger_record,
                statement_record=statement_result.statement_record,
                resolved_by_human=True
            )
            
            # Delete the unmatched records
            ledger_result.delete()
            statement_result.delete()
            
            return Response({'status': 'Matched successfully'})
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def accept_unmatched(self, request, pk=None):
        run = get_object_or_404(ReconciliationRun, pk=pk)
        serializer = AcceptUnmatchedSerializer(data=request.data)
        
        if serializer.is_valid():
            ledger_id = serializer.validated_data.get('ledger_id')
            statement_id = serializer.validated_data.get('statement_id')
            
            if ledger_id:
                ledger_result = get_object_or_404(MatchResult, run=run, match_type='UNMATCHED_LEDGER', ledger_record_id=ledger_id)
                ledger_result.resolved_by_human = True
                ledger_result.save()
                
            if statement_id:
                statement_result = get_object_or_404(MatchResult, run=run, match_type='UNMATCHED_STATEMENT', statement_record_id=statement_id)
                statement_result.resolved_by_human = True
                statement_result.save()
                
            return Response({'status': 'Accepted as unmatched successfully'})
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def suggest_match(self, request, pk=None):
        run = get_object_or_404(ReconciliationRun, pk=pk)
        ledger_id = request.query_params.get('ledger_id')
        statement_id = request.query_params.get('statement_id')
        
        target = None
        candidates = []
        is_ledger = False
        
        if ledger_id:
            target = get_object_or_404(LedgerRecord, pk=ledger_id)
            candidates = StatementRecord.objects.filter(matchresult__run=run, matchresult__match_type='UNMATCHED_STATEMENT', matchresult__resolved_by_human=False)
            is_ledger = True
        elif statement_id:
            target = get_object_or_404(StatementRecord, pk=statement_id)
            candidates = LedgerRecord.objects.filter(matchresult__run=run, matchresult__match_type='UNMATCHED_LEDGER', matchresult__resolved_by_human=False)
        else:
            return Response({"error": "Provide ledger_id or statement_id"}, status=status.HTTP_400_BAD_REQUEST)
            
        best_match = None
        highest_score = 0
        
        for cand in candidates:
            score = 100
            
            if target.instrument != cand.instrument:
                score -= 20
            if target.side != cand.side:
                score -= 20
                
            amount_diff = abs(target.amount - cand.amount)
            max_amt = max(target.amount, cand.amount)
            if max_amt > 0:
                percent_diff = amount_diff / max_amt
                score -= float(percent_diff) * 40 # Up to 40 point penalty
                
            time_diff = abs((target.executed_at - cand.executed_at).total_seconds())
            days_diff = time_diff / (24 * 3600)
            score -= float(days_diff) * 10 # 10 points per day diff
            
            score = max(0, min(100, score))
            
            if score > highest_score:
                highest_score = score
                best_match = cand
                
        response_data = {
            "target": {
                "id": target.id,
                "transaction_id": target.transaction_id,
                "instrument": target.instrument,
                "side": target.side,
                "amount": str(target.amount),
                "executed_at": target.executed_at.strftime('%Y-%m-%d %H:%M:%S'),
                "type": "Ledger" if is_ledger else "Statement"
            },
            "suggestion": None,
            "score": round(highest_score, 1)
        }
        
        if best_match:
            response_data["suggestion"] = {
                "id": best_match.id,
                "transaction_id": best_match.transaction_id,
                "instrument": best_match.instrument,
                "side": best_match.side,
                "amount": str(best_match.amount),
                "executed_at": best_match.executed_at.strftime('%Y-%m-%d %H:%M:%S'),
                "type": "Statement" if is_ledger else "Ledger"
            }
            
        return Response(response_data)
