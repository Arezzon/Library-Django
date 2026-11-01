"""Read-only catalog facts for consumers, independent of the AI app and workflows."""

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils import timezone

from authentication.permissions import is_signed_in
from author.models import Author

from .models import Book

RESULT_LIMIT = 10


def _author_record(author):
    return {
        "id": author.pk,
        "name": " ".join(
            filter(None, (author.name, author.patronymic, author.surname))
        ),
        "url": reverse("author-detail", kwargs={"pk": author.pk}),
        "books_url": reverse("book_list") + f"?author_id={author.pk}",
    }


def _book_record(book):
    return {
        "id": book.pk,
        "title": book.name,
        "url": reverse("book_detail", kwargs={"book_id": book.pk}),
        "authors": [
            _author_record(author)
            for author in sorted(book.authors.all(), key=lambda a: a.pk)
        ],
        "available_count": book.available_count,
        "total_count": book.count,
    }


def lookup_catalog(user, query, *, by_author=False, now=None):
    """Evaluate all lazy queries here so source failures never leak partial facts."""
    if not is_signed_in(user) or user.pk is None:
        raise PermissionDenied("Sign in to read catalog facts.")
    now = now or timezone.now()
    books = Book.objects.with_availability(now).prefetch_related("authors")
    authors = []
    author_truncated = False
    if by_author:
        matches = Author.objects.all()
        for token in query.split():
            matches = matches.filter(
                Q(name__icontains=token)
                | Q(surname__icontains=token)
                | Q(patronymic__icontains=token)
            )
        matches = matches.order_by(Lower("surname"), Lower("name"), "pk")
        rows = list(matches[: RESULT_LIMIT + 1])
        authors = [_author_record(author) for author in rows[:RESULT_LIMIT]]
        author_truncated = len(rows) > RESULT_LIMIT
        books = books.filter(authors__in=matches.values("pk")).distinct()
    else:
        books = books.filter(name__icontains=query)
    rows = list(books.order_by(Lower("name"), "pk")[: RESULT_LIMIT + 1])
    return (
        [_book_record(book) for book in rows[:RESULT_LIMIT]],
        authors,
        author_truncated or len(rows) > RESULT_LIMIT,
    )
