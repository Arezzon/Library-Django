"""KAN-50 input contract: private history, current candidates and safe fallback.

This module selects data only: no embedding inference, ranking, writes or cache.
Use the session's account; the interface accepts no separate target account ID.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone

from authentication.permissions import is_signed_in
from events.models import EventType, UserEvent
from order.models import Order, Reservation, ReservationState

from .models import Book

HISTORY_DAYS = 90
HISTORY_LIMIT = 200
SEARCH_LIMIT = 3
SEARCH_TEXT_LIMIT = 200
EVENT_WEIGHTS = {
    EventType.BOOK_VIEW: 1,
    EventType.BOOK_CLICK: 2,
    EventType.BORROW_INTENT: 3,
    EventType.ORDER_CREATED: 4,
    EventType.ORDER_RETURNED: 4,
}
CLIENT_ACTIONS = (EventType.BOOK_CLICK, EventType.BORROW_INTENT)
LOAN_ACTIONS = (EventType.ORDER_CREATED, EventType.ORDER_RETURNED)


@dataclass(frozen=True)
class BookSignal:
    book_id: int
    event_type: str
    weight: int


@dataclass(frozen=True)
class RecommendationHistory:
    """V1 has recorded book actions and searches; no invented explicit feedback.

    Empty tuples mean no usable history. Favorites, likes and ratings require
    their own model adapters and semantics before they can extend this contract.
    """

    books: tuple[BookSignal, ...] = ()
    searches: tuple[str, ...] = ()


def _require_account(user):
    if not is_signed_in(user) or user.pk is None:
        raise PermissionDenied("Sign in to access recommendation data.")


def read_history(user, *, now=None):
    """Return the caller's minimized, bounded, deduplicated history snapshot.

    Keep the strongest action per existing book; ties keep the latest action.
    Searches retain the latest original text, deduplicated case-insensitively.
    No raw event payload, actor/reader IDs or another account's signals escape.
    """
    _require_account(user)
    now = now or timezone.now()
    book_action = Q(book_id__in=Book.objects.values("pk")) & (
        Q(source="server", event_type__in=EVENT_WEIGHTS)
        | Q(source="client", event_type__in=CLIENT_ACTIONS)
    )
    events = (
        UserEvent.objects.filter(
            book_action | Q(event_type=EventType.SEARCH, source="server"),
            user_id=user.pk,
            occurred_at__gte=now - timedelta(days=HISTORY_DAYS),
            occurred_at__lte=now,
        )
        .order_by("-occurred_at", "-id")
        .values_list("book_id", "event_type", "properties")[:HISTORY_LIMIT]
    )
    books, searches = {}, {}
    for book_id, kind, properties in events:
        if kind == EventType.SEARCH:
            query = properties.get("query") if isinstance(properties, dict) else None
            if (
                isinstance(query, str)
                and query.strip()
                and len(searches) < SEARCH_LIMIT
            ):
                query = query.strip()[:SEARCH_TEXT_LIMIT]
                searches.setdefault(query.casefold(), query)
        else:
            # A librarian may process a return for another reader. Do not turn
            # that other reader's loan into the librarian's personal interest.
            if (
                kind in LOAN_ACTIONS
                and isinstance(properties, dict)
                and "reader_id" in properties
                and properties["reader_id"] != user.pk
            ):
                continue
            signal = BookSignal(book_id, kind, EVENT_WEIGHTS[kind])
            previous = books.get(book_id)
            if previous is None or signal.weight > previous.weight:
                books[book_id] = signal
    return RecommendationHistory(
        tuple(books[key] for key in sorted(books)), tuple(searches.values())
    )


def available_candidates(user, *, now=None):
    """Public catalog data eligible for this reader at one instant.

    Count all active loans and unexpired holds, then exclude this account's own
    current loans and holds even when other copies remain. No personal events
    from any account are consulted for candidate eligibility.
    """
    _require_account(user)
    now = now or timezone.now()
    return (
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


def fallback_candidates(user, *, now=None, exclude_book_ids=()):
    """The same eligible books, ordered by case-insensitive title and then ID.

    Callers slice this queryset to their Top-N and may omit already returned or
    already-used profile books. Empty catalog/history/feedback needs no special
    model or popularity lookup and returns an empty queryset or a stable list.
    """
    return (
        available_candidates(user, now=now)
        .exclude(pk__in=exclude_book_ids)
        .order_by(Lower("name"), "id")
    )
