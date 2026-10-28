"""Reserving and lending: one implementation of the rules for every channel (FR-011,
FR-012, research R13).

Each operation runs in one transaction and locks the reader's account row, then the
book row, so simultaneous requests from one reader, or for one book, are checked one
after another. The rules run in R13's order, the first that fails is reported, and a
refusal changes nothing.
"""

from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Case, F, Q, Value, When
from django.utils import dateformat, timezone

from audit.context import audit_context
from audit.services import record
from authentication.models import CustomUser
from authentication.permissions import is_librarian
from book.models import Book

from .models import (
    BookUnavailableError,
    Order,
    Reservation,
    ReservationState,
    as_text,
)

RESERVATION_LIMIT = 3
DATE = "j M Y"
DATE_AND_TIME = "j M Y, H:i T"

# Each code's message for the reader, then for a librarian acting for a reader
# (contracts/reservations-api.md).
MESSAGES = {
    "overdue_loan": (
        "“{book}” was due on {due}. Return it before reserving or borrowing another "
        "book.",
        "{reader} has an overdue loan: “{book}”, due {due}. It must be returned first.",
    ),
    "already_on_loan": (
        "You already have “{book}” on loan.",
        "{reader} already has “{book}” on loan.",
    ),
    "already_reserved": (
        "You already reserved “{book}”. Collect it from a librarian before "
        "{deadline}.",
        None,
    ),
    "reservation_limit": (
        "You already have 3 active reservations, the most allowed. Collect or cancel "
        "one to reserve another book.",
        None,
    ),
    "no_copy_available": (
        "No copy of “{book}” is available right now. Try again later or choose "
        "another book.",
        "No copy of “{book}” is available. A reservation may be holding the last one.",
    ),
}


class ReservationRefused(Exception):
    """A rule refused the request, and nothing changed (FR-020). ``context`` holds
    the details that the API adds to its 409 body."""

    def __init__(self, code, message, **context):
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = context


def local(moment, pattern=DATE_AND_TIME):
    """A time as pages show it: the library's local time, with its zone (R16)."""
    return dateformat.format(timezone.localtime(moment), pattern)


def refusal(code, *, librarian=False, context=None, **values):
    reader_text, librarian_text = MESSAGES[code]
    text = librarian_text if librarian and librarian_text else reader_text
    return ReservationRefused(code, text.format(**values), **(context or {}))


def active_reservations(reader, now):
    """The reader's reservations that still hold a copy at ``now`` (FR-013)."""
    return Reservation.objects.filter(
        user=reader, state=ReservationState.ACTIVE, expires_at__gt=now
    )


def check(reader, book, now, *, reserving, librarian=False, availability=True):
    """The first of R13's rules that refuses, or None."""
    name = f"{reader.first_name} {reader.last_name}"
    overdue = (
        Order.objects.filter(user=reader, end_at__isnull=True, plated_end_at__lt=now)
        .select_related("book")
        .order_by("plated_end_at")
        .first()
    )
    if overdue is not None:
        return refusal(
            "overdue_loan",
            librarian=librarian,
            book=overdue.book.name,
            due=local(overdue.plated_end_at, DATE),
            reader=name,
            context={
                "book": overdue.book_id,
                "due": timezone.localtime(overdue.plated_end_at).isoformat(),
            },
        )
    if Order.objects.filter(user=reader, book=book, end_at__isnull=True).exists():
        return refusal(
            "already_on_loan", librarian=librarian, book=book.name, reader=name
        )
    if reserving:
        held = active_reservations(reader, now).filter(book=book).first()
        if held is not None:
            return refusal(
                "already_reserved", book=book.name, deadline=local(held.expires_at)
            )
        if active_reservations(reader, now).count() >= RESERVATION_LIMIT:
            return refusal("reservation_limit")
    if availability:
        available = Book.objects.with_availability(now).get(pk=book.pk)
        if available.available_count <= 0:
            return refusal("no_copy_available", librarian=librarian, book=book.name)
    return None


def listed(reservations, now):
    """Active reservations first, by deadline, then the rest, newest first."""
    holding = Q(state=ReservationState.ACTIVE, expires_at__gt=now)
    return reservations.annotate(
        holding=Case(When(holding, then=Value(0)), default=Value(1)),
        deadline=Case(When(holding, then=F("expires_at")), default=None),
    ).order_by("holding", "deadline", "-created_at")


def next_step(reservation, now):
    """What the reader does next, for My reservations (FR-019)."""
    state = reservation.effective_state(now)
    if state == ReservationState.ACTIVE:
        return f"Collect it from a librarian before {local(reservation.expires_at)}."
    if state == ReservationState.ISSUED:
        return "Collected. It is now on loan; see My orders."
    if state == ReservationState.EXPIRED:
        return "The 48 hours ended. Reserve it again if a copy is available."
    return "Cancelled."


def eligibility(reader, book, now, *, lending=False):
    """Why ``reader`` may not reserve, or borrow, ``book`` now, or None: the same
    rules without locks, for pages to show (FR-020)."""
    if lending:
        held = active_reservations(reader, now).filter(book=book).exists()
        return check(reader, book, now, reserving=False, availability=not held)
    return check(reader, book, now, reserving=True)


def lock(reader, book):
    """The reader's account row, then the book row (R13)."""
    reader = CustomUser.objects.select_for_update().get(pk=reader.pk)
    book = Book.objects.select_for_update().get(pk=book.pk)
    return reader, book


def expire_due(now, *, reader=None, book=None):
    """Record the expiry of active reservations whose deadline has passed, each with
    an entry made by the system (R11), and return how many. Rows that another
    transaction holds are left to it."""
    due = Reservation.objects.filter(state=ReservationState.ACTIVE, expires_at__lte=now)
    if reader is not None or book is not None:
        due = due.filter(Q(user=reader) | Q(book=book))
    expired = 0
    with transaction.atomic(), audit_context(channel="system"):
        rows = due.select_for_update(skip_locked=True, of=("self",)).select_related(
            "user", "book"
        )
        for reservation in rows:
            reservation.change_state(ReservationState.EXPIRED, now)
            reservation.save(update_fields=["state"])
            record(
                "reservation_expired",
                "reservation",
                reservation.pk,
                reservation.audit_label(),
                {"state": ReservationState.ACTIVE},
                {"state": ReservationState.EXPIRED},
                occurred_at=reservation.expires_at,
            )
            expired += 1
    return expired


def reserve(reader, book, *, now=None):
    """Reserve ``book`` for ``reader`` for 48 hours, or raise ReservationRefused."""
    now = now or timezone.now()
    with transaction.atomic():
        reader, book = lock(reader, book)
        expire_due(now, reader=reader, book=book)
        refused = check(reader, book, now, reserving=True)
        if refused is not None:
            raise refused
        reservation = Reservation.objects.create(user=reader, book=book, created_at=now)
        record(
            "reservation_created",
            "reservation",
            reservation.pk,
            reservation.audit_label(),
            {},
            {
                "book": book.pk,
                "user": reader.pk,
                "expires_at": as_text(reservation.expires_at),
            },
        )
    return reservation


def lend(actor, reader, book, days, *, now=None):
    """Lend ``book`` to ``reader`` for ``days`` days, or raise ReservationRefused.

    If the reader holds an active reservation of the book, it is issued, and the copy
    it held becomes the lent one (R13). Until issuing moves to librarians (KAN-57), a
    reader may lend only to themselves."""
    if not is_librarian(actor) and actor.pk != reader.pk:
        raise PermissionDenied("Readers may borrow only for themselves.")
    librarian = actor.pk != reader.pk
    now = now or timezone.now()
    with transaction.atomic():
        reader, book = lock(reader, book)
        expire_due(now, reader=reader, book=book)
        held = active_reservations(reader, now).filter(book=book).first()
        refused = check(
            reader,
            book,
            now,
            reserving=False,
            librarian=librarian,
            availability=held is None,
        )
        if refused is not None:
            raise refused
        if held is not None:
            # Issued first, so the copy it held is free for the loan's own check.
            held.change_state(ReservationState.ISSUED, now)
            held.save(update_fields=["state"])
        loan = Order(user=reader, book=book, plated_end_at=now + timedelta(days=days))
        try:
            loan.save()
        except BookUnavailableError:
            raise refusal(
                "no_copy_available", librarian=librarian, book=book.name
            ) from None
        if held is not None:
            held.loan = loan
            held.save(update_fields=["loan"])
            record(
                "reservation_issued",
                "reservation",
                held.pk,
                held.audit_label(),
                {"state": ReservationState.ACTIVE},
                {"state": ReservationState.ISSUED, "loan": loan.pk},
            )
    return loan
