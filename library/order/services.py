"""Reserving, lending, issuing and cancelling: one implementation of the rules for
every channel (FR-011, FR-012, FR-015 to FR-018, research R13).

Each operation runs in one transaction. Issuing and cancelling lock the reservation's
row first; reserving, lending and issuing lock the reader's account row and then the
book row, so simultaneous requests from one reader, for one book or on one reservation
are checked one after another. The rules run in R13's order, the first that fails is
reported, and a refusal changes nothing.
"""

from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
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
REASON_LENGTH = 500
REASON_RULE = "Give a reason of 1 to 500 characters. The reader will see it."
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
    "reservation_expired": (
        None,
        "This reservation expired at {deadline}. You can lend the book directly only "
        "if a copy is available.",
    ),
    "already_issued": (None, "This reservation was already issued as loan #{loan}."),
    "not_active": (
        "This reservation is no longer active.",
        "This reservation is {state}; nothing was changed.",
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


def check(
    reader, book, now, *, reserving, librarian=False, availability=True, own_loan=None
):
    """The first of R13's rules that refuses, or None. ``own_loan`` is the loan of the
    reservation being issued, which does not count as the book already on loan."""
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
    on_loan = Order.objects.filter(user=reader, book=book, end_at__isnull=True)
    if on_loan.exclude(pk=own_loan).exists():
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


def eligibility(reader, book, now):
    """Why ``reader`` may not reserve ``book`` now, or None: the same rules without
    locks, for pages to show (FR-020)."""
    return check(reader, book, now, reserving=True)


def lock(reader_id, book_id):
    """The reader's account row, then the book row (R13)."""
    reader = CustomUser.objects.select_for_update().get(pk=reader_id)
    book = Book.objects.select_for_update().get(pk=book_id)
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
        reader, book = lock(reader.pk, book.pk)
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


def start_loan(reader, book, due, held, now):
    """Start the loan, issuing ``held``, the reservation whose copy it takes, if there
    is one. The caller holds the locks."""
    if held is not None:
        # Issued first, so the copy it held is free for the loan's own check.
        held.change_state(ReservationState.ISSUED, now)
        held.save(update_fields=["state"])
    loan = Order(user=reader, book=book, plated_end_at=due)
    try:
        loan.save()
    except BookUnavailableError:
        raise refusal("no_copy_available", librarian=True, book=book.name) from None
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


def lend(actor, reader, book, days=None, *, due=None, now=None):
    """Lend ``book`` to ``reader`` until ``due``, or for ``days`` days, or raise
    ReservationRefused. Only librarians lend (FR-015, FR-016).

    If the reader holds an active reservation of the book, it is issued, and the copy
    it held becomes the lent one (R13)."""
    if not is_librarian(actor):
        raise PermissionDenied("Only librarians lend books.")
    now = now or timezone.now()
    with transaction.atomic():
        # The reservation's row first, in issue()'s order, so a loan and an issue of
        # the same reservation wait for each other instead of deadlocking (R13).
        held = (
            active_reservations(reader, now)
            .filter(book=book)
            .select_for_update()
            .first()
        )
        reader, book = lock(reader.pk, book.pk)
        expire_due(now, reader=reader, book=book)
        refused = check(
            reader,
            book,
            now,
            reserving=False,
            librarian=True,
            availability=held is None,
        )
        if refused is not None:
            raise refused
        return start_loan(reader, book, due or now + timedelta(days=days), held, now)


def issue(actor, reservation, days, *, now=None):
    """Issue ``reservation`` as a loan of ``days`` days in one step, or raise
    ReservationRefused (FR-015). A repeated request finds it issued and starts no
    second loan."""
    if not is_librarian(actor):
        raise PermissionDenied("Only librarians issue reservations.")
    with transaction.atomic():
        # The reservation's row, then the reader's, then the book's (R13).
        reservation = Reservation.objects.select_for_update().get(pk=reservation.pk)
        reader, book = lock(reservation.user_id, reservation.book_id)
        # Read once the rows are held, so the deadline is checked as the issue commits.
        now = now or timezone.now()
        refused = check(
            reader,
            book,
            now,
            reserving=False,
            librarian=True,
            availability=False,
            own_loan=reservation.loan_id,
        )
        if refused is not None:
            raise refused
        state = reservation.effective_state(now)
        if state == ReservationState.EXPIRED:
            raise refusal(
                "reservation_expired",
                librarian=True,
                deadline=local(reservation.expires_at),
            )
        if state == ReservationState.ISSUED and reservation.loan_id is not None:
            raise refusal(
                "already_issued",
                librarian=True,
                loan=reservation.loan_id,
                context={"loan": reservation.loan_id},
            )
        if state != ReservationState.ACTIVE:
            raise refusal("not_active", librarian=True, state=state)
        return start_loan(reader, book, now + timedelta(days=days), reservation, now)


def cancel(actor, reservation, reason="", *, now=None):
    """Cancel ``reservation``, or raise ReservationRefused if it is no longer active.

    Its reader cancels without a reason; a librarian cancelling someone else's gives
    one of 1 to 500 characters, which the reader will see (FR-017, FR-018). Nobody
    else may cancel it."""
    own = actor.pk == reservation.user_id
    librarian = is_librarian(actor)
    if not (own or librarian):
        raise PermissionDenied("Only the reader or a librarian may cancel this.")
    reason = reason.strip()
    if len(reason) > REASON_LENGTH or not (own or reason):
        raise ValidationError({"reason": REASON_RULE})
    with transaction.atomic():
        reservation = Reservation.objects.select_for_update().get(pk=reservation.pk)
        now = now or timezone.now()
        state = reservation.effective_state(now)
        if state != ReservationState.ACTIVE:
            raise refusal("not_active", librarian=librarian, state=state)
        reservation.change_state(ReservationState.CANCELLED, now)
        reservation.cancelled_by = actor
        reservation.cancelled_at = now
        reservation.cancel_reason = reason
        reservation.save(
            update_fields=["state", "cancelled_by", "cancelled_at", "cancel_reason"]
        )
        record(
            "reservation_cancelled",
            "reservation",
            reservation.pk,
            reservation.audit_label(),
            {"state": ReservationState.ACTIVE},
            {"state": ReservationState.CANCELLED},
            reason=reason,
            occurred_at=now,
        )
    return reservation
