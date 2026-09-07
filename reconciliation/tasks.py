from celery import shared_task
from .engine import run_reconciliation

@shared_task
def process_global_reconciliation(run_id: int):
    run_reconciliation(run_id)
