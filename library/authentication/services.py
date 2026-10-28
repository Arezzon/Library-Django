"""One rule for changing an account's role and status (FR-002, research R3).

The web profile page and the API both apply account changes through
``update_account``, so the rule has a single implementation. A change that touches a
field the actor may not change is refused whole: nothing is saved, not even the names
sent with it.
"""

from django.core.exceptions import PermissionDenied

# Only a librarian may change these on any account, their own included.
LIBRARIAN_ONLY_FIELDS = frozenset({"email", "password"})


def may_change_role(actor, account):
    return bool(getattr(actor, "is_librarian", False))


def may_change_status(actor, account):
    return bool(getattr(actor, "is_librarian", False))


def check_changes(actor, account, fields):
    """Raise PermissionDenied if ``fields`` names one the actor may not change.

    A field counts when it is sent at all, whatever its value, so the web and the API
    can refuse a forbidden field before they validate anything.
    """
    fields = set(fields)
    if "role" in fields and not may_change_role(actor, account):
        raise PermissionDenied("You may not change the role of this account.")
    if "is_active" in fields and not may_change_status(actor, account):
        raise PermissionDenied("You may not change the status of this account.")
    if fields & LIBRARIAN_ONLY_FIELDS and not getattr(actor, "is_librarian", False):
        raise PermissionDenied("Only a librarian may change an email or password.")


def update_account(actor, account, changes):
    """Apply ``changes`` (field name to value) to ``account`` and save it, or refuse
    them all with PermissionDenied."""
    check_changes(actor, account, changes)
    for field, value in changes.items():
        if field == "password":
            account.set_password(value)
        else:
            setattr(account, field, value)
    account.save()
    return account
