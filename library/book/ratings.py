"""Owned rating state stored directly in PostgreSQL, independent of event queues."""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404

from authentication.permissions import is_signed_in

from .models import Book, BookRating
from .rating_rules import validate_rating


def require_rating_account(user):
    if not is_signed_in(user) or user.pk is None:
        raise PermissionDenied("Sign in to access your ratings.")


def rating_state(user, book_id):
    require_rating_account(user)
    get_object_or_404(Book.objects.only("pk"), pk=book_id)
    value = (
        BookRating.objects.filter(user_id=user.pk, book_id=book_id)
        .values_list("value", flat=True)
        .first()
    )
    return {"book_id": book_id, "value": value}


@transaction.atomic
def set_rating(user, book_id, value):
    """Desired state, not a toggle. None deletes; identical retries preserve time.

    Account then book locks match the preference/loan lock ordering. Unique and
    range constraints also protect writes outside this service.
    """
    require_rating_account(user)
    if value is not None:
        validate_rating(value)
    account = (
        get_user_model()
        .objects.select_for_update()
        .filter(pk=user.pk, is_active=True)
        .first()
    )
    if account is None:
        raise PermissionDenied("This account is not active.")
    book = get_object_or_404(Book.objects.select_for_update(), pk=book_id)
    if value is None:
        BookRating.objects.filter(user=account, book=book).delete()
    else:
        rating, created = BookRating.objects.get_or_create(
            user=account, book=book, defaults={"value": value}
        )
        if not created and rating.value != value:
            rating.value = value
            rating.save(update_fields=["value", "updated_at"])
    return {"book_id": book.pk, "value": value}
