"""Private, deterministic content-based recommendations using stored embeddings."""

from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone
from pgvector.django import CosineDistance

from authentication.permissions import is_signed_in
from events.models import EventType, UserEvent
from order.models import Order, Reservation, ReservationState

from . import embeddings
from .embedding_config import resolve
from .embeddings import normalized_vector
from .models import Book, BookEmbedding

DEFAULT_LIMIT = 10
MAX_LIMIT = 20
HISTORY_LIMIT = 200
HISTORY_DAYS = 90
SEARCH_LIMIT = 3
SEARCH_WEIGHT = 1
# A stronger action replaces weaker/repeated actions on the same book.
EVENT_WEIGHTS = {
    EventType.BOOK_VIEW: 1,
    EventType.BOOK_CLICK: 2,
    EventType.BORROW_INTENT: 3,
    EventType.ORDER_CREATED: 4,
    EventType.ORDER_RETURNED: 4,
}


def _profile(user, now):
    """At most 200 recent own events, including three distinct text searches."""
    events = (
        UserEvent.objects.filter(
            Q(event_type__in=EVENT_WEIGHTS, book_id__isnull=False)
            | Q(event_type=EventType.SEARCH, source="server"),
            user_id=user.pk,
            occurred_at__gte=now - timedelta(days=HISTORY_DAYS),
            occurred_at__lte=now,
        )
        .order_by("-occurred_at", "-id")
        .values_list("book_id", "event_type", "properties")[:HISTORY_LIMIT]
    )
    weights = {}
    queries = {}
    for book_id, event_type, properties in events:
        if event_type == EventType.SEARCH:
            query = properties.get("query") if isinstance(properties, dict) else None
            if isinstance(query, str) and query.strip() and len(queries) < SEARCH_LIMIT:
                query = query.strip()[:200]
                queries.setdefault(query.casefold(), query)
        else:
            weights[book_id] = max(weights.get(book_id, 0), EVENT_WEIGHTS[event_type])
    spec = resolve()
    vectors = BookEmbedding.objects.filter(
        book_id__in=weights, model=spec.repository, model_revision=spec.tag
    ).order_by("book_id")
    total = [0.0] * spec.dimensions
    seeds = []
    for embedding in vectors.only("book_id", "vector"):
        try:
            vector = normalized_vector(embedding.vector)
        except ValueError:
            continue
        seeds.append(embedding.book_id)
        for i, value in enumerate(vector):
            total[i] += weights[embedding.book_id] * value
    if queries:
        # Reuse the existing process-local model, without storing a second profile
        # or caching private query text. Model failure preserves book signals.
        try:
            model = embeddings.load_embedding_model()
        except Exception:
            model = None
        if model is not None:
            for query in queries.values():
                try:
                    vector = normalized_vector(
                        next(
                            iter(model.embed([spec.query_prefix + query], batch_size=1))
                        )
                    )
                except Exception:
                    continue
                for i, value in enumerate(vector):
                    total[i] += SEARCH_WEIGHT * value
    try:
        return normalized_vector(total), seeds
    except ValueError:
        return None, seeds


def recommend_books(user, limit=DEFAULT_LIMIT):
    """Return up to ``limit`` available, not-currently-held books for this account.

    A weighted centroid ranks unseen compatible books by cosine similarity. Missing
    vectors are filled from a stable alphabetical list. No additional model,
    training, cross-reader popularity, persisted profile or availability cache is needed.
    Only text-search signals need inference through the existing shared encoder.
    """
    if not is_signed_in(user):
        raise PermissionDenied("Sign in to request recommendations.")
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= MAX_LIMIT
    ):
        raise ValueError(f"limit must be an integer from 1 to {MAX_LIMIT}.")
    now = timezone.now()
    books = (
        Book.objects.with_availability(now)
        .filter(count__gt=F("active_order_count") + F("active_reservation_count"))
        .exclude(
            pk__in=Order.objects.filter(user=user, end_at__isnull=True).values(
                "book_id"
            )
        )
        .exclude(
            pk__in=Reservation.objects.filter(
                user=user, state=ReservationState.ACTIVE, expires_at__gt=now
            ).values("book_id")
        )
        .prefetch_related("authors")
    )
    profile, seeds = _profile(user, now)
    results = []
    if profile is not None:
        spec = resolve()
        books = books.exclude(pk__in=seeds)
        results = list(
            books.filter(
                embedding__model=spec.repository, embedding__model_revision=spec.tag
            )
            .alias(distance=CosineDistance("embedding__vector", profile))
            .order_by("distance", "id")[:limit]
        )
    if len(results) < limit:
        results += list(
            books.exclude(pk__in=[book.pk for book in results]).order_by(
                Lower("name"), "id"
            )[: limit - len(results)]
        )
    return results
