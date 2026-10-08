from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import IntegrityError, InterfaceError, OperationalError
from django.utils.dateparse import parse_datetime
from .models import UserEvent


@shared_task(
    acks_late=True, reject_on_worker_lost=True, ignore_result=True,
    autoretry_for=(OperationalError, InterfaceError, IntegrityError),
    retry_backoff=True, retry_backoff_max=60, retry_jitter=True,
    retry_kwargs={'max_retries': None},
)
def persist_event(payload):
    """Idempotent insert: broker redelivery and client retries cannot double count."""
    user_id = payload['user_id']
    if not get_user_model().objects.filter(pk=user_id).exists():
        user_id = None
    UserEvent.objects.get_or_create(id=payload['id'], defaults={
        'user_id': user_id,
        'event_type': payload['event_type'],
        'source': payload['source'],
        'book_id': payload['book_id'],
        'path': payload['path'],
        'properties': payload['properties'],
        'occurred_at': parse_datetime(payload['occurred_at']),
    })
