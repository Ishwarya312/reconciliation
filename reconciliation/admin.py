from django.contrib import admin
from .models import DataFile, LedgerRecord, StatementRecord, ReconciliationRun, MatchResult

@admin.register(DataFile)
class DataFileAdmin(admin.ModelAdmin):
    list_display = ('id', 'file_type', 'uploaded_at', 'processed')
    
@admin.register(LedgerRecord)
class LedgerRecordAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'instrument', 'side', 'amount', 'status', 'source_file')
    list_filter = ('source_file',)
    search_fields = ('transaction_id', 'instrument')

@admin.register(StatementRecord)
class StatementRecordAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'instrument', 'side', 'amount', 'status', 'source_file')
    list_filter = ('source_file',)
    search_fields = ('transaction_id', 'instrument')

@admin.register(ReconciliationRun)
class ReconciliationRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'started_at', 'completed_at')

@admin.register(MatchResult)
class MatchResultAdmin(admin.ModelAdmin):
    list_display = ('id', 'match_type', 'ledger_record', 'statement_record', 'resolved_by_human')
    list_filter = ('match_type', 'resolved_by_human')
