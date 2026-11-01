"""Read-only catalog facts for consumers, independent of the AI app and workflows."""

from django.core.exceptions import PermissionDenied
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils import timezone

from authentication.permissions import is_signed_in
from author.models import Author

from .catalog_matching import folded_field, tokens
from .models import Book
from .search import search_books

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


def lookup_catalog(
    user,
    query,
    *,
    by_author=False,
    author_ids=None,
    now=None,
    flexible=False,
    available_only=False,
    book_ids=None,
    topic=False,
):
    """Evaluate all lazy queries here so source failures never leak partial facts."""
    if not is_signed_in(user) or user.pk is None:
        raise PermissionDenied("Sign in to read catalog facts.")
    now = now or timezone.now()
    books = Book.objects.with_availability(now).prefetch_related("authors")
    if available_only:
        books = books.filter(
            count__gt=F("active_order_count") + F("active_reservation_count")
        )
    if book_ids is not None:
        books = books.filter(pk__in=book_ids)
    authors = []
    author_truncated = False
    if by_author:
        matches = Author.objects.all()
        if author_ids is not None:
            matches = matches.filter(pk__in=author_ids)
        elif flexible:
            matches = matches.alias(
                folded_name=folded_field("name"),
                folded_surname=folded_field("surname"),
                folded_patronymic=folded_field("patronymic"),
            )
            words = tokens(query)
            if not words:
                matches = matches.none()
            for token in words:
                matches = matches.filter(
                    Q(folded_name__startswith=token)
                    | Q(folded_surname__startswith=token)
                    | Q(folded_patronymic__startswith=token)
                )
        else:
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
    elif topic:
        # Reuse the existing CPU encoder and pgvector; the catalog stays in SQL.
        # A similarity gate avoids presenting every nearest neighbor as relevant.
        candidates = list(search_books(books, query))
        if candidates:
            threshold = max(0.45, candidates[0].similarity - 0.08)
            candidates = [book for book in candidates if book.similarity >= threshold][
                :5
            ]
        return [_book_record(book) for book in candidates], [], False
    elif flexible:
        words = tokens(query)
        books = books.alias(folded_title=folded_field("name"))
        if not words:
            books = books.none()
        for token in words:
            books = books.filter(folded_title__contains=token)
    elif query:
        books = books.filter(name__icontains=query)
    rows = list(books.order_by(Lower("name"), "pk")[: RESULT_LIMIT + 1])
    return (
        [_book_record(book) for book in rows[:RESULT_LIMIT]],
        authors,
        author_truncated or len(rows) > RESULT_LIMIT,
    )
