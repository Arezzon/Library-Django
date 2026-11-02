"""Read-only UA/EN catalog assistant with optional CPU topic retrieval."""

from django.core.exceptions import PermissionDenied
from django.db import DatabaseError
from django.utils import timezone

from authentication.permissions import is_signed_in
from book.catalog_data import lookup_catalog
from book.embeddings import EmbeddingGenerationError

from .language import parse_query

MAX_QUERY_LENGTH = 256
INTENTS = ("auto", "title", "author", "availability")
AVAILABILITY_NOTICE = (
    "Наявність наведено на момент перевірки, це не гарантія отримання книги. "
    "Під час бронювання фонд перевіряється повторно."
)
HELP = (
    "Уточніть назву або автора. Приклади: «книга: Kobzar», "
    "«знайди твори Шевченка», «чи є 1984?», «порадь книги про програмування»."
)


def _response(
    status,
    intent,
    answer,
    *,
    books=None,
    authors=None,
    checked_at=None,
    truncated=False,
):
    return {
        "status": status,
        "intent": intent,
        "answer": answer,
        "books": books or [],
        "authors": authors or [],
        "checked_at": checked_at,
        "truncated": truncated,
        "availability_notice": AVAILABILITY_NOTICE,
    }


def catalog_assistant(user, query="", intent="auto", *, context_book_ids=()):
    """Resolve supported UA/EN questions to fresh catalog facts only.

    The trusted web flow may supply bounded IDs from its own short-lived session.
    Literal and author lookups need no inference; topic queries reuse CPU search.
    """
    if not is_signed_in(user) or user.pk is None:
        raise PermissionDenied("Sign in to use the catalog assistant.")
    if (
        not isinstance(query, str)
        or len(query) > MAX_QUERY_LENGTH
        or intent not in INTENTS
    ):
        raise ValueError("Invalid assistant parameters.")
    parsed = parse_query(query, intent)
    intent, query = parsed.intent, parsed.text
    if intent == "clarify" or (
        len(query) < 2 and not parsed.followup and not parsed.available_only
    ):
        return _response("clarification_required", "auto", HELP)
    if parsed.followup and (
        not context_book_ids or (parsed.single and len(context_book_ids) != 1)
    ):
        return _response("clarification_required", intent, HELP)
    now = timezone.now()
    try:
        options = {"by_author": intent == "author", "now": now}
        if parsed.available_only:
            options["available_only"] = True
        if parsed.followup:
            options["book_ids"] = context_book_ids[:10]
        if intent == "topic":
            options["topic"] = True
        books, authors, truncated = lookup_catalog(user, query, **options)
        if not books and not authors and query and intent != "topic":
            books, authors, truncated = lookup_catalog(
                user, query, flexible=True, **options
            )
        if not books and not authors and intent == "title" and not parsed.literal:
            books, authors, truncated = lookup_catalog(
                user,
                query,
                by_author=True,
                now=now,
                flexible=True,
                available_only=parsed.available_only,
            )
            if authors:
                intent = "author"

    except (DatabaseError, EmbeddingGenerationError):
        return _response(
            "source_unavailable",
            intent,
            "Каталог або пошук тимчасово недоступний. Не можу підтвердити книги, авторів чи наявність. Спробуйте пізніше.",
        )
    return _catalog_response(
        books, authors, truncated, intent, now, collection=parsed.available_only
    )


def _catalog_response(
    books, authors, truncated, intent, now, *, collection=False, status=None
):
    if not books and not authors:
        return _response(
            "not_found",
            intent,
            "У каталозі немає підтверджених збігів. " + HELP,
            checked_at=now.isoformat(),
        )
    ambiguous = truncated or (
        len(authors) > 1
        if intent == "author"
        else (len(books) > 1 and intent != "topic" and not collection)
    )
    lines = ["Схожі за темою книги каталогу:"] if intent == "topic" else []
    for author in authors:
        lines.append(
            f"Автор: {author['name']} ({author['url']}). Книги: {author['books_url']}."
        )
    for book in books:
        author_names = ", ".join(
            author["name"] for author in book["authors"] if author["name"]
        )
        byline = (
            f" Автори: {author_names}."
            if author_names
            else " Автор у каталозі не вказаний."
        )
        lines.append(
            f"«{book['title']}» ({book['url']}).{byline} Доступно: {book['available_count']} із {book['total_count']}."
        )
    if authors and not books:
        lines.append("Пов’язаних книг у каталозі не знайдено.")
    if ambiguous:
        lines.append(
            "Є кілька збігів або список скорочено. Уточніть повну назву чи ім’я автора або відкрийте потрібний запис."
        )
    lines.append(AVAILABILITY_NOTICE)
    return _response(
        status or ("clarification_required" if ambiguous else "found"),
        intent,
        "\n".join(lines),
        books=books,
        authors=authors,
        checked_at=now.isoformat(),
        truncated=truncated,
    )


def catalog_page_result(user, state):
    """Rehydrate confirmed references for GET/back/refresh without replaying a query."""
    if not is_signed_in(user) or user.pk is None:
        raise PermissionDenied("Sign in to use the catalog assistant.")
    if not state["books"] and not state["authors"]:
        return _response(
            state["status"],
            state["intent"],
            (
                HELP
                if state["status"] == "clarification_required"
                else "У каталозі немає підтверджених збігів. " + HELP
            ),
        )
    now = timezone.now()
    try:
        books, authors, _ = lookup_catalog(
            user,
            "",
            now=now,
            book_ids=state["books"],
            by_author=bool(state["authors"]),
            author_ids=state["authors"],
            available_only=state["available_only"],
        )
    except DatabaseError:
        return _response(
            "source_unavailable",
            state["intent"],
            "Каталог тимчасово недоступний. Не можу підтвердити книги, авторів чи наявність. Спробуйте пізніше.",
        )
    order = {pk: i for i, pk in enumerate(state["books"])}
    books.sort(key=lambda book: order[book["id"]])
    return _catalog_response(
        books,
        authors,
        state["truncated"],
        state["intent"],
        now,
        collection=state["available_only"],
        status=state["status"],
    )
