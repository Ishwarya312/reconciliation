from rest_framework import serializers
from .models import DataFile, ReconciliationRun, MatchResult, LedgerRecord, StatementRecord

class DataFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataFile
        fields = '__all__'

class MatchResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = MatchResult
        fields = '__all__'

class ManualMatchSerializer(serializers.Serializer):
    ledger_id = serializers.IntegerField()
    statement_id = serializers.IntegerField()

class AcceptUnmatchedSerializer(serializers.Serializer):
    ledger_id = serializers.IntegerField(required=False, allow_null=True)
    statement_id = serializers.IntegerField(required=False, allow_null=True)
