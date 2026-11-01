"""Short-lived, account-bound catalog references; never retain question text."""

from django.utils import timezone

KEY = "catalog_assistant_context"
TTL_SECONDS = 600
MAX_BOOKS = 10


def read_context(session, user):
    value = session.get(KEY)
    if not isinstance(value, dict) or value.get("owner") != user.pk:
        return ()
    when = value.get("time")
    ids = value.get("books")
    if (
        type(when) not in (int, float)
        or not 0 <= timezone.now().timestamp() - when <= TTL_SECONDS
        or not isinstance(ids, list)
        or not 1 <= len(ids) <= MAX_BOOKS
        or any(type(pk) is not int or pk <= 0 for pk in ids)
    ):
        return ()
    return tuple(ids)


def remember_result(session, user, result):
    if result["books"]:
        session[KEY] = {
            "owner": user.pk,
            "time": timezone.now().timestamp(),
            "books": [book["id"] for book in result["books"][:MAX_BOOKS]],
        }
    else:
        session.pop(KEY, None)


RESULT_KEY = "catalog_assistant_result"


def clear_context(session):
    session.pop(KEY, None)
    session.pop(RESULT_KEY, None)


def remember_page_result(session, user, result, *, available_only=False):
    """Persist references for a safe GET, never the submitted form or answer."""
    session[RESULT_KEY] = {
        "owner": user.pk,
        "time": timezone.now().timestamp(),
        "books": [book["id"] for book in result["books"][:MAX_BOOKS]],
        "authors": [author["id"] for author in result["authors"][:MAX_BOOKS]],
        "status": result["status"],
        "intent": result["intent"],
        "truncated": bool(result["truncated"]),
        "available_only": bool(available_only),
    }


def read_page_result(session, user):
    value = session.get(RESULT_KEY)
    if not isinstance(value, dict) or value.get("owner") != user.pk:
        return None
    when = value.get("time")
    if (
        type(when) not in (int, float)
        or not 0 <= timezone.now().timestamp() - when <= TTL_SECONDS
    ):
        return None
    for field in ("books", "authors"):
        ids = value.get(field)
        if (
            not isinstance(ids, list)
            or len(ids) > MAX_BOOKS
            or any(type(pk) is not int or pk <= 0 for pk in ids)
        ):
            return None
    if (
        value.get("status") not in ("found", "not_found", "clarification_required")
        or value.get("intent")
        not in ("auto", "title", "author", "availability", "topic")
        or type(value.get("truncated")) is not bool
        or type(value.get("available_only")) is not bool
    ):
        return None
    return value
