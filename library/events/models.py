import uuid
from django.conf import settings
from django.db import models


class EventType(models.TextChoices):
    BOOK_VIEW = 'book_view', 'Book viewed'
    SEARCH = 'search', 'Catalog searched'
    BOOK_CLICK = 'book_click', 'Book clicked'
    BORROW_INTENT = 'borrow_intent', 'Borrow button clicked'
    ORDER_CREATED = 'order_created', 'Book borrowed'
    ORDER_RETURNED = 'order_returned', 'Book returned'
    ORDER_REOPENED = 'order_reopened', 'Order reopened'
    ORDER_REASSIGNED = 'order_reassigned', 'Order reassigned'
    LOGIN = 'login', 'Signed in'
    LOGOUT = 'logout', 'Signed out'


class UserEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             on_delete=models.SET_NULL, related_name='events')
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    source = models.CharField(max_length=8, choices=[('server', 'Server'), ('client', 'Client')])
    # Retain the resource identifier even if a catalog entry is deleted.
    book_id = models.PositiveBigIntegerField(null=True, blank=True)
    path = models.CharField(max_length=200, blank=True)
    properties = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-occurred_at', '-id']
        indexes = [
            models.Index(fields=['occurred_at'], name='event_occurred_idx'),
            models.Index(fields=['user', 'event_type', 'occurred_at'], name='event_user_type_time_idx'),
            models.Index(fields=['book_id', 'event_type'], name='event_book_type_idx'),
        ]
