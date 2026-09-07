from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import DataFile, ReconciliationRun, MatchResult
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
