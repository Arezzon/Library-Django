from datetime import UTC, timedelta

from django.db import DataError, models, router, transaction
from django.db.models import F, Q
from django.db.models.lookups import Exact
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from audit.services import record
from authentication.models import CustomUser
from book.models import Book


class BookUnavailableError(ValueError):
    """An active order cannot consume a copy that is already on loan."""


def as_text(moment):
    """A date and time as audit entries store it: ISO 8601 in UTC, as the database
    keeps it, whatever zone the value arrived in."""
    if isinstance(moment, str):
        moment = parse_datetime(moment)
    return moment.astimezone(UTC).isoformat() if moment else None


AUDITED_LOAN_FIELDS = {"end_at", "book", "book_id", "user", "user_id"}


class OrderQuerySet(models.QuerySet):
    # Refused before bulk_update opens a transaction, so the caller's stays usable.
    def bulk_update(self, objs, fields, batch_size=None):
        if AUDITED_LOAN_FIELDS & set(fields):
            raise ValueError(
                "Loan update bypasses the copy check and the audit trail; use save()."
            )
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def update(self, **kwargs):
        if AUDITED_LOAN_FIELDS & set(kwargs):
            raise ValueError(
                "Loan update bypasses the copy check and the audit trail; use save()."
            )
        return super().update(**kwargs)

    def bulk_create(self, *args, **kwargs):
        raise ValueError(
            "Loan bulk_create bypasses the copy check and the audit trail; "
            "use create() or save()."
        )


class Order(models.Model):
    """
    This class represents an Order. \n
    Attributes:
    -----------
    param book: foreign key Book
    type book: ForeignKey
    param user: foreign key CustomUser
    type user: ForeignKey
    param created_at: Describes the date when the order was created. Can't be changed.
    type created_at: int (timestamp)
    param end_at: Describes the actual return date of the book. (`None` if not returned)
    type end_at: int (timestamp)
    param plated_end_at: Describes the planned return period of the book (2 weeks from the moment of creation).
    type plated_end_at: int (timestamp)
    """

    # A book with loans cannot be deleted in any channel (FR-024).
    book = models.ForeignKey(Book, on_delete=models.PROTECT, default=None)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, default=None)
    created_at = models.DateTimeField(auto_now_add=True)
    end_at = models.DateTimeField(default=None, null=True, blank=True)
    plated_end_at = models.DateTimeField(default=None)
    objects = OrderQuerySet.as_manager()

    def __str__(self):
        return f"Order #{self.id} ({self.user.email} - {self.book.name})"

    def __repr__(self):
        """
        This magic method is redefined to show class and id of Book object.
        :return: class, id
        """
        return f"{self.__class__.__name__}(id={self.id})"

    def save(
        self, force_insert=False, force_update=False, using=None, update_fields=None
    ):
        """Serialize issuance, reopening and book reassignment on the Book row.

        Availability is derived from active orders; creating an order consumes
        a copy without changing Book.count or a separate stock counter.
        Use save/create for these operations, not bulk_create/QuerySet.update.
        """
        if update_fields is not None:
            update_fields = frozenset(update_fields)
            if not update_fields:
                return
        database = using or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=database):
            previous = None
            if self.pk is not None:
                previous = (
                    type(self)
                    .objects.using(database)
                    .select_for_update()
                    .filter(pk=self.pk)
                    .values("book_id", "user_id", "end_at", "plated_end_at")
                    .first()
                )
            book_id, user_id, end_at = self.book_id, self.user_id, self.end_at
            if previous is not None and update_fields is not None:
                if not {"book", "book_id"} & update_fields:
                    book_id = previous["book_id"]
                if not {"user", "user_id"} & update_fields:
                    user_id = previous["user_id"]
                if "end_at" not in update_fields:
                    end_at = previous["end_at"]
            consumes_copy = end_at is None and (
                previous is None
                or previous["end_at"] is not None
                or previous["book_id"] != book_id
            )
            if consumes_copy:
                # Keep the locking query free of joins/aggregations. Recount
                # after acquiring the lock, using a fresh, unannotated Book.
                book = Book.objects.using(database).select_for_update().get(pk=book_id)
                if book.available_count <= 0:
                    raise BookUnavailableError(
                        "No copies of this book are currently available."
                    )
            result = super().save(
                force_insert=force_insert,
                force_update=force_update,
                using=database,
                update_fields=update_fields,
            )
            self._audit_changes(previous, book_id, user_id, end_at)
            return result

    def audit_label(self):
        user = self.user
        return f"Loan #{self.pk}: {self.book.name} ({user.first_name} {user.last_name} #{user.pk})"

    def _audit_changes(self, previous, book_id, user_id, end_at):
        """Record the change in the save's transaction (FR-037, FR-040)."""
        label = self.audit_label()
        if previous is None:
            after = {
                "book": book_id,
                "user": user_id,
                "due": as_text(self.plated_end_at),
            }
            record("loan_started", "loan", self.pk, label, {}, after)
            return
        if previous["end_at"] is None and end_at is not None:
            after = {"end_at": as_text(end_at)}
            record("loan_returned", "loan", self.pk, label, {"end_at": None}, after)
        elif previous["end_at"] is not None and end_at is None:
            before = {"end_at": as_text(previous["end_at"])}
            record("loan_reopened", "loan", self.pk, label, before, {"end_at": None})
        moved = {
            field: (previous[f"{field}_id"], value)
            for field, value in (("book", book_id), ("user", user_id))
            if previous[f"{field}_id"] != value
        }
        if moved:
            before = {field: old for field, (old, _new) in moved.items()}
            after = {field: new for field, (_old, new) in moved.items()}
            record("loan_reassigned", "loan", self.pk, label, before, after)

    def to_dict(self):
        """
        :return: order id, book id, user id, order created_at, order end_at, order plated_end_at
        :Example:
        | {
        |   'id': 8,
        |   'book': 8,
        |   'user': 8',
        |   'created_at': 1509393504,
        |   'end_at': 1509393504,
        |   'plated_end_at': 1509402866,
        | }
        """
        pass

    @staticmethod
    def create(user, book, plated_end_at):
        try:
            order = Order(user=user, book=book, plated_end_at=plated_end_at)
            order.save()
            return order
        except ValueError:
            return None
        except DataError:
            return None

    @staticmethod
    def get_by_id(order_id):
        try:
            return Order.objects.get(pk=order_id)
        except Exception:
            return None

    def update(self, plated_end_at=None, end_at=None):
        if plated_end_at is not None:
            self.plated_end_at = plated_end_at
        if end_at is not None:
            self.end_at = end_at
        self.save()

    @staticmethod
    def get_all():
        return list(Order.objects.all())

    @staticmethod
    def get_not_returned_books():
        return Order.objects.filter(end_at=None).values()

    @staticmethod
    def delete_by_id(order_id):
        try:
            a = Order.objects.get(pk=order_id)
        except Exception:
            return False
        else:
            a.delete()
            return True


@receiver(post_delete, sender=Order, dispatch_uid="order.loan_deleted")
def record_loan_deletion(sender, instance, **kwargs):
    """Also covers loans deleted along with their account."""
    before = {
        "book": instance.book_id,
        "user": instance.user_id,
        "end_at": as_text(instance.end_at),
    }
    record("loan_deleted", "loan", instance.pk, instance.audit_label(), before, {})


RESERVATION_HOURS = 48


class ReservationState(models.TextChoices):
    ACTIVE = "active", "Active"
    ISSUED = "issued", "Issued"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"


class ReservationStateError(ValueError):
    """A reservation cannot make this change of state (FR-014)."""


# A reservation changes these one at a time, through change_state() and save().
GUARDED_RESERVATION_FIELDS = {
    "state",
    "loan",
    "loan_id",
    "cancelled_by",
    "cancelled_by_id",
    "cancelled_at",
    "cancel_reason",
    "cancellation_seen_at",
}


class ReservationQuerySet(models.QuerySet):
    # Refused before bulk_update opens a transaction, so the caller's stays usable.
    def bulk_update(self, objs, fields, batch_size=None):
        if GUARDED_RESERVATION_FIELDS & set(fields):
            raise ValueError(
                "Reservation update bypasses its state rules; "
                "use change_state() and save()."
            )
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def update(self, **kwargs):
        if GUARDED_RESERVATION_FIELDS & set(kwargs):
            raise ValueError(
                "Reservation update bypasses its state rules; "
                "use change_state() and save()."
            )
        return super().update(**kwargs)

    def bulk_create(self, *args, **kwargs):
        raise ValueError(
            "Reservation bulk_create bypasses its rules; "
            "create one reservation at a time."
        )


class Reservation(models.Model):
    """A reader's 48-hour hold on one unit of a book's stock, not on a particular copy
    (FR-008, ADR 0001)."""

    # Deleting the account deletes its reservations; their audit entries remain.
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="reservations",
        verbose_name="reader",
    )
    # A book with reservations cannot be deleted in any channel (FR-024).
    book = models.ForeignKey(
        Book, on_delete=models.PROTECT, related_name="reservations"
    )
    state = models.CharField(
        max_length=16,
        choices=ReservationState.choices,
        default=ReservationState.ACTIVE,
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    expires_at = models.DateTimeField()
    # The loan the reservation became when it was issued.
    loan = models.OneToOneField(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservation",
    )
    cancelled_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=500, blank=True)
    # When the reader dismissed the library's cancellation notice.
    cancellation_seen_at = models.DateTimeField(null=True, blank=True)
    objects = ReservationQuerySet.as_manager()

    class Meta:
        constraints = [
            # Elapsed time, not created_at + interval: the database adds the 2 days
            # that 48 hours is sent as in the session's time zone, so a restore into
            # a server set to a zone with summer time would refuse valid rows.
            models.CheckConstraint(
                condition=Exact(
                    F("expires_at") - F("created_at"),
                    timedelta(hours=RESERVATION_HOURS),
                ),
                name="reservation_lasts_48_hours",
            ),
            # A backstop: the reservation service checks first.
            models.UniqueConstraint(
                fields=["user", "book"],
                condition=Q(state=ReservationState.ACTIVE),
                name="one_active_reservation_per_reader_and_book",
            ),
            models.CheckConstraint(
                condition=~Q(state=ReservationState.CANCELLED)
                | Q(cancelled_at__isnull=False),
                name="cancelled_reservation_has_time",
            ),
        ]
        indexes = [
            # Availability, the reader's limit and list, and the desk list and expiry.
            models.Index(
                fields=["book", "state", "expires_at"], name="reservation_book_idx"
            ),
            models.Index(fields=["user", "state"], name="reservation_user_idx"),
            models.Index(fields=["state", "expires_at"], name="reservation_state_idx"),
        ]

    def __str__(self):
        return f"Reservation #{self.pk} ({self.user.email} - {self.book.name})"

    def save(self, *args, **kwargs):
        if self._state.adding:
            # Set once; the database refuses any other deadline (FR-010).
            self.expires_at = self.created_at + timedelta(hours=RESERVATION_HOURS)
        super().save(*args, **kwargs)

    def audit_label(self):
        user = self.user
        return (
            f"Reservation #{self.pk}: {self.book.name} "
            f"({user.first_name} {user.last_name} #{user.pk})"
        )

    def effective_state(self, now):
        """The state every check and page uses: an active reservation is expired from
        its deadline on, whether or not its expiry has been recorded (FR-013)."""
        if self.state == ReservationState.ACTIVE and self.expires_at <= now:
            return ReservationState.EXPIRED
        return self.state

    def change_state(self, state, now):
        """Move to ``state`` if FR-014 allows it. Before the deadline, an active
        reservation is issued or cancelled; from the deadline on, it can only expire.
        Issued, cancelled and expired are final. Any other change raises, and nothing
        changes."""
        if self.state != ReservationState.ACTIVE:
            allowed = ()
        elif self.effective_state(now) == ReservationState.ACTIVE:
            allowed = (ReservationState.ISSUED, ReservationState.CANCELLED)
        else:
            allowed = (ReservationState.EXPIRED,)
        if state not in allowed:
            raise ReservationStateError(
                f"A reservation that is {self.effective_state(now)} cannot become "
                f"{state}."
            )
        self.state = state
