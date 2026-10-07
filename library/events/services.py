import logging
import uuid
from contextvars import ContextVar
from django.db import transaction
from django.utils import timezone
from kombu.exceptions import OperationalError
from redis.exceptions import RedisError
from .tasks import persist_event

logger = logging.getLogger(__name__)
current_request = ContextVar('tracking_request', default=None)


class EventQueueUnavailable(Exception):
    pass


def make_payload(request, event_type, *, source='server', user=None,
                 book_id=None, properties=None, event_id=None, path=None):
    actor = user if user is not None else request.user
    # Bind a client UUID to its authenticated user, avoiding cross-user collisions.
    identity = uuid.uuid5(uuid.NAMESPACE_URL, f'library-event:{actor.pk}:{event_id}') if event_id else uuid.uuid4()
    return {
        'id': str(identity), 'user_id': actor.pk, 'event_type': str(event_type),
        'source': source, 'book_id': book_id,
        'path': (path if path is not None else request.path)[:200],
        'properties': properties or {}, 'occurred_at': timezone.now().isoformat(),
    }


def publish_event(payload):
    try:
        persist_event.apply_async(args=[payload], queue='events', retry=False)
    except (OperationalError, RedisError, OSError) as error:
        raise EventQueueUnavailable('Event queue is temporarily unavailable.') from error


def capture(request, event_type, *, using='default', **kwargs):
    """Only publish committed actions; analytics failures never undo business work."""
    actor = kwargs.get('user') or getattr(request, 'user', None)
    if not actor or not actor.is_authenticated:
        return
    payload = make_payload(request, event_type, **kwargs)

    def publish():
        try:
            publish_event(payload)
        except EventQueueUnavailable:
            logger.exception('Could not enqueue server event %s', payload['event_type'])

    transaction.on_commit(publish, using=using)
