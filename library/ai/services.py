"""Read-only, deterministic catalog assistant. No model inference or workflow calls."""

from django.core.exceptions import PermissionDenied
from django.db import DatabaseError
from django.utils import timezone

from authentication.permissions import is_signed_in
from book.catalog_data import lookup_catalog

MAX_QUERY_LENGTH = 256
INTENTS = ("auto", "title", "author", "availability")
PREFIXES = {
    "книга": "title",
    "назва": "title",
    "book": "title",
    "title": "title",
    "автор": "author",
    "author": "author",
    "наявність": "availability",
    "доступність": "availability",
    "availability": "availability",
}
AVAILABILITY_NOTICE = (
    "Наявність наведено на момент перевірки, це не гарантія отримання книги. "
    "Під час бронювання фонд перевіряється повторно."
)
HELP = (
    "Уточніть назву або автора. Приклади: «книга: Kobzar», "
    "«автор: Taras Shevchenko», «наявність: Kobzar»."
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


def catalog_assistant(user, query="", intent="auto"):
    """Only active signed-in accounts can read the same catalog as normal readers.

    Accept literal title fragments, explicit intent or documented UA/EN prefixes.
    Do not interpret arbitrary conversation, retain chat history or mutate stock.
    """
    if not is_signed_in(user) or user.pk is None:
        raise PermissionDenied("Sign in to use the catalog assistant.")
    if (
        not isinstance(query, str)
        or len(query) > MAX_QUERY_LENGTH
        or intent not in INTENTS
    ):
        raise ValueError("Invalid assistant parameters.")
    query = " ".join(query.split())
    if intent == "auto":
        prefix, separator, rest = query.partition(":")
        if separator:
            intent = PREFIXES.get(prefix.casefold())
            if intent is None:
                return _response("clarification_required", "auto", HELP)
            query = rest.strip()
        else:
            intent = "title"
    if len(query) < 2:
        return _response("clarification_required", intent, HELP)
    now = timezone.now()
    try:
        books, authors, truncated = lookup_catalog(
            user, query, by_author=intent == "author", now=now
        )
    except DatabaseError:
        return _response(
            "source_unavailable",
            intent,
            "Каталог тимчасово недоступний. Не можу підтвердити книги, авторів чи наявність. Спробуйте пізніше.",
        )
    if not books and not authors:
        return _response(
            "not_found",
            intent,
            "У каталозі немає підтверджених збігів. " + HELP,
            checked_at=now.isoformat(),
        )
    ambiguous = truncated or (
        len(authors) > 1 if intent == "author" else len(books) > 1
    )
    lines = []
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
        "clarification_required" if ambiguous else "found",
        intent,
        "\n".join(lines),
        books=books,
        authors=authors,
        checked_at=now.isoformat(),
        truncated=truncated,
    )
