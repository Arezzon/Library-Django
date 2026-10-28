from django.db import models
from django.utils import timezone


class Action(models.TextChoices):
    ROLE_GRANTED = "role_granted", "Role granted"
    ROLE_REMOVED = "role_removed", "Role removed"
    ACCOUNT_ACTIVATED = "account_activated", "Account activated"
    ACCOUNT_DEACTIVATED = "account_deactivated", "Account deactivated"
    ACCOUNT_DELETED = "account_deleted", "Account deleted"
    LOAN_STARTED = "loan_started", "Loan started"
    LOAN_RETURNED = "loan_returned", "Loan returned"
    LOAN_REOPENED = "loan_reopened", "Loan reopened"
    LOAN_REASSIGNED = "loan_reassigned", "Loan reassigned"
    LOAN_DELETED = "loan_deleted", "Loan deleted"
    RESERVATION_CREATED = "reservation_created", "Reservation created"
    RESERVATION_ISSUED = "reservation_issued", "Reservation issued"
    RESERVATION_CANCELLED = "reservation_cancelled", "Reservation cancelled"
    RESERVATION_EXPIRED = "reservation_expired", "Reservation expired"
    BOOK_COPIES_CHANGED = "book_copies_changed", "Book copies changed"
    BOOK_DELETED = "book_deleted", "Book deleted"


class Target(models.TextChoices):
    ACCOUNT = "account", "Account"
    LOAN = "loan", "Loan"
    RESERVATION = "reservation", "Reservation"
    BOOK = "book", "Book"


class Channel(models.TextChoices):
    WEB = "web", "Web"
    API = "api", "API"
    ADMIN = "admin", "Admin site"
    COMMAND = "command", "Command"
    SYSTEM = "system", "System"


class AuditEntryQuerySet(models.QuerySet):
    # bulk_update refuses before it opens a transaction, so the caller's stays usable.
    def bulk_update(self, objs, fields, batch_size=None):
        raise ValueError("Audit entries cannot be changed.")

    def update(self, **kwargs):
        raise ValueError("Audit entries cannot be changed.")

    def delete(self):
        raise ValueError("Audit entries cannot be deleted.")


class AuditEntry(models.Model):
    """An unchangeable record of one critical change (data-model.md §5).

    Actor and target are ids and labels, not foreign keys, so an entry outlives the
    account or book it describes.
    """

    occurred_at = models.DateTimeField(default=timezone.now)
    actor_id = models.PositiveBigIntegerField(null=True, blank=True)
    actor_label = models.CharField(max_length=150)
    action = models.CharField(max_length=32, choices=Action.choices)
    target_type = models.CharField(max_length=16, choices=Target.choices)
    target_id = models.PositiveBigIntegerField()
    target_label = models.CharField(max_length=200)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    reason = models.CharField(max_length=500, blank=True)
    channel = models.CharField(max_length=8, choices=Channel.choices)
    request_id = models.CharField(max_length=64, blank=True)

    objects = AuditEntryQuerySet.as_manager()

    class Meta:
        ordering = ["-occurred_at", "-id"]
        verbose_name_plural = "audit entries"
        indexes = [
            models.Index(fields=["target_type", "target_id"], name="audit_target_idx"),
            models.Index(fields=["occurred_at"], name="audit_occurred_idx"),
            models.Index(fields=["actor_id", "occurred_at"], name="audit_actor_idx"),
        ]

    def __str__(self):
        return f"{self.get_action_display()}: {self.target_label}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Audit entries cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Audit entries cannot be deleted.")
