"""One durable effect per search identity, through the existing event worker."""

import uuid

from django.core.exceptions import PermissionDenied

from authentication.permissions import is_signed_in

from .models import EventType
from .services import make_payload, publish_event


def search_identity(raw=None):
    return uuid.uuid4() if raw is None else uuid.UUID(str(raw))


def record_search(request, identity, query, author_id=None):
    if not is_signed_in(request.user):
        raise PermissionDenied("Sign in to save search history.")
    payload = make_payload(
        request,
        EventType.SEARCH,
        properties={"query": query.strip()[:200], "author_id": author_id},
    )
    # Separate from click identities; the same client UUID cannot collide across
    # users or event families. The worker's unique event ID handles redelivery.
    payload["id"] = str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"library-search:{request.user.pk}:{identity}")
    )
    publish_event(payload)
