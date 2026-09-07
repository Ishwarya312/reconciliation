from django.db import models

class DataFile(models.Model):
    FILE_TYPES = [
        ('LEDGER', 'Ledger'),
        ('STATEMENT', 'Statement'),
    ]
    
    file = models.FileField(upload_to='uploads/')
    file_type = models.CharField(max_length=20, choices=FILE_TYPES)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.file_type} - {self.uploaded_at}"

class BaseTransaction(models.Model):
    """Abstract base model for normalized transactions"""
    transaction_id = models.CharField(max_length=100, help_text="Original identifier (trade_id or reference)")
    instrument = models.CharField(max_length=50, help_text="Normalized symbol/instrument")
    side = models.CharField(max_length=10, help_text="Normalized side (BUY or SELL)")
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    price = models.DecimalField(max_digits=20, decimal_places=8)
    amount = models.DecimalField(max_digits=20, decimal_places=8, help_text="Total/Gross amount")
    executed_at = models.DateTimeField()
    status = models.CharField(max_length=20, help_text="Original status")
    
    # Track which file this came from
    source_file = models.ForeignKey(DataFile, on_delete=models.CASCADE)

    class Meta:
        abstract = True

class LedgerRecord(BaseTransaction):
    def __str__(self):
        return f"Ledger {self.transaction_id} ({self.instrument})"

class StatementRecord(BaseTransaction):
    def __str__(self):
        return f"Statement {self.transaction_id} ({self.instrument})"

class ReconciliationRun(models.Model):
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    ledger_file = models.ForeignKey(DataFile, on_delete=models.CASCADE, related_name='ledger_runs')
    statement_file = models.ForeignKey(DataFile, on_delete=models.CASCADE, related_name='statement_runs')
    
    def __str__(self):
        return f"Run {self.id} at {self.started_at}"

class MatchResult(models.Model):
    MATCH_TYPES = [
        ('EXACT', 'Exact Match'),
        ('FUZZY', 'Fuzzy Match (Drift)'),
        ('UNMATCHED_LEDGER', 'Unmatched (Ledger Only)'),
        ('UNMATCHED_STATEMENT', 'Unmatched (Statement Only)'),
        ('MANUAL', 'Manually Matched'),
        ('IGNORED', 'Ignored (Cancelled)')
    ]
    
    run = models.ForeignKey(ReconciliationRun, on_delete=models.CASCADE, related_name='results')
    match_type = models.CharField(max_length=25, choices=MATCH_TYPES)
    
    ledger_record = models.ForeignKey(LedgerRecord, on_delete=models.SET_NULL, null=True, blank=True)
    statement_record = models.ForeignKey(StatementRecord, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Discrepancies calculated during match
    amount_discrepancy = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    time_discrepancy_seconds = models.IntegerField(default=0)
    
    # When a human resolves a match manually, we want to flag it so it carries over
    resolved_by_human = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.match_type} - L:{self.ledger_record_id} S:{self.statement_record_id}"
