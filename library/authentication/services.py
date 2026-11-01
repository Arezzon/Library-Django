"""One rule for changing an account's role and status (FR-002, FR-063, research R3, R26).

The web profile page, the API and the admin site apply account changes through
``update_account``, so the rule has a single implementation. A change that touches a
field the actor may not change is refused whole: nothing is saved, not even the names
sent with it.
"""

from django.core.exceptions import PermissionDenied

from .models import ROLE_CHOICES, ROLE_LIBRARIAN, ROLE_VISITOR

# Only a librarian may change these on any account, their own included.
LIBRARIAN_ONLY_FIELDS = frozenset({"email", "password"})

# The roles the web, the API and the admin site assign. The operator grants the
# administrator role on the server (R26).
ASSIGNABLE_ROLES = (ROLE_VISITOR, ROLE_LIBRARIAN)
ASSIGNABLE_ROLE_CHOICES = [
    (role, label) for role, label in ROLE_CHOICES if role in ASSIGNABLE_ROLES
]


def _administrator(user):
    # ``user`` may be None: an account that does not exist yet.
    return bool(getattr(user, "is_administrator", False))


def may_change_account(actor, account):
    """Only administrators change an administrator's account: a librarian who could
    set its email or password could act as an administrator (FR-063)."""
    return _administrator(actor) or not _administrator(account)


def may_change_role(actor, account):
    """Only an administrator grants or removes the librarian role, and an
    administrator's own role changes only on the server (FR-063, R26)."""
    return _administrator(actor) and not _administrator(account)


def may_change_status(actor, account):
    return bool(getattr(actor, "is_librarian", False)) and may_change_account(
        actor, account
    )


def check_changes(actor, account, fields):
    """Raise PermissionDenied if ``fields`` names one the actor may not change.

    A field counts when it is sent at all, whatever its value, so the web and the API
    can refuse a forbidden field before they validate anything. ``account`` is None
    for an account that does not exist yet.
    """
    fields = set(fields)
    if not may_change_account(actor, account):
        raise PermissionDenied("Only an administrator may change this account.")
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
    if "role" in changes and changes["role"] not in ASSIGNABLE_ROLES:
        raise PermissionDenied("The operator grants the administrator role.")
    for field, value in changes.items():
        if field == "password":
            account.set_password(value)
        else:
            setattr(account, field, value)
    account.save()
    return account
