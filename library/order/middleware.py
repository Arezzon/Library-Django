"""The reader's notices of reservations the library cancelled (FR-017, research R15)."""

from django.utils.functional import SimpleLazyObject

from .models import Reservation, ReservationState


def unseen_cancellations(user):
    """The reservations of ``user`` that someone else cancelled and that they have
    not dismissed, the newest first."""
    return list(
        Reservation.objects.filter(
            user=user,
            state=ReservationState.CANCELLED,
            cancellation_seen_at__isnull=True,
        )
        .exclude(cancelled_by=user)
        .select_related("book")
        .order_by("-cancelled_at")
    )


class ReservationNoticeMiddleware:
    """Sets ``request.reservation_notices`` for signed-in accounts. It is read only
    when a page shows it, and showing a notice writes nothing: the reader's Dismiss
    POST hides it (Principle II)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        request.reservation_notices = SimpleLazyObject(
            lambda: unseen_cancellations(user) if user.is_authenticated else []
        )
        return self.get_response(request)
