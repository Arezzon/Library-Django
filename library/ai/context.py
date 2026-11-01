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
