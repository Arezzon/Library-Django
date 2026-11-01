"""Private, durable preference state; independent of the analytics queue."""

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404

from authentication.permissions import is_signed_in

from .models import Book, BookLike, FavoriteBook

PREFERENCE_LIMIT = 200


def _require_account(user):
    if not is_signed_in(user) or user.pk is None:
        raise PermissionDenied("Sign in to access your book preferences.")


def with_preferences(books, user):
    _require_account(user)
    return books.annotate(
        liked=Exists(BookLike.objects.filter(user_id=user.pk, book_id=OuterRef("pk"))),
        favorite=Exists(
            FavoriteBook.objects.filter(user_id=user.pk, book_id=OuterRef("pk"))
        ),
    )


def preference_state(user, book_id):
    book = get_object_or_404(with_preferences(Book.objects.all(), user), pk=book_id)
    return {"book_id": book.pk, "liked": book.liked, "favorite": book.favorite}


@transaction.atomic
def set_preferences(user, book_id, *, liked=None, favorite=None):
    """Set explicit desired states, never toggle. User then book locks serialize
    concurrent updates/reset and book/account deletion; unique keys are a backstop.
    """
    _require_account(user)
    if any(
        value is not None and not isinstance(value, bool) for value in (liked, favorite)
    ):
        raise ValueError("Preference states must be booleans.")
    account = (
        get_user_model()
        .objects.select_for_update()
        .filter(pk=user.pk, is_active=True)
        .first()
    )
    if account is None:
        raise PermissionDenied("This account is not active.")
    book = get_object_or_404(Book.objects.select_for_update(), pk=book_id)
    for model, desired in ((BookLike, liked), (FavoriteBook, favorite)):
        if desired is True:
            model.objects.get_or_create(user=account, book=book)
        elif desired is False:
            model.objects.filter(user=account, book=book).delete()
    return preference_state(account, book.pk)


def preference_books(user, kind="all"):
    if kind not in ("all", "likes", "favorites"):
        raise ValueError("kind must be all, likes or favorites.")
    books = with_preferences(
        Book.objects.with_availability().prefetch_related("authors"), user
    )
    condition = Q(liked=True) | Q(favorite=True)
    if kind == "likes":
        condition = Q(liked=True)
    elif kind == "favorites":
        condition = Q(favorite=True)
    return books.filter(condition).order_by(Lower("name"), "id")


@dataclass(frozen=True)
class BookPreferenceSignal:
    book_id: int
    liked: bool
    favorite: bool


def read_book_preferences(user):
    """At most 200 recent rows per source for ranking, no user IDs or timestamps.
    Listing the reader's saved books is separate and is not truncated by this cap.
    """
    _require_account(user)
    likes = set(
        BookLike.objects.filter(user_id=user.pk).values_list("book_id", flat=True)[
            :PREFERENCE_LIMIT
        ]
    )
    favorites = set(
        FavoriteBook.objects.filter(user_id=user.pk).values_list("book_id", flat=True)[
            :PREFERENCE_LIMIT
        ]
    )
    return tuple(
        BookPreferenceSignal(pk, pk in likes, pk in favorites)
        for pk in sorted(likes | favorites)
    )
