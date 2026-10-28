"""Who may call each API operation (Principle II, FR-003).

Every API view names one of these classes in its own ``permission_classes``. The
project default, ``DenyAll``, refuses every caller, so a view that forgets to declare
its audience fails closed instead of opening up. Each class carries the label and the
plain-language description that the API schema shows for its operations.
"""

from django.contrib.auth import get_user_model
from rest_framework import authentication, permissions


class SessionAuthentication(authentication.SessionAuthentication):
    """DRF's session sign-in, with a challenge so that a caller who is not signed in
    gets 401 and a signed-in caller without the role gets 403."""

    def authenticate_header(self, request):
        return "Session"


def is_signed_in(user):
    return bool(user and user.is_authenticated and user.is_active)


def is_librarian(user):
    return is_signed_in(user) and getattr(user, "is_librarian", False)


class DenyAll(permissions.BasePermission):
    """The default for a view that declares no audience: nobody."""

    audience = "nobody"
    audience_description = "Nobody: the operation declares no audience."

    def has_permission(self, request, view):
        return False


class IsSignedIn(permissions.BasePermission):
    audience = "signed-in"
    audience_description = "Any signed-in account."

    def has_permission(self, request, view):
        return is_signed_in(request.user)


class ReadOnlyOrLibrarian(permissions.BasePermission):
    audience = "signed-in-read"
    audience_description = "Signed-in accounts may read; only librarians may change."

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return is_signed_in(request.user)
        return is_librarian(request.user)


class IsSelfOrLibrarian(permissions.BasePermission):
    """The account itself, or a librarian. Views using it also limit a reader's
    queryset to their own records, so another reader's record answers 404."""

    audience = "self-or-librarian"
    audience_description = "The account the record belongs to, or a librarian."

    def has_permission(self, request, view):
        return is_signed_in(request.user)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if is_librarian(user):
            return True
        # request.user is a lazy wrapper, so compare with the model, not its type.
        if isinstance(obj, get_user_model()):
            owner = obj.pk
        else:
            owner = getattr(obj, "user_id", None)
        return owner == user.pk


class IsLibrarian(permissions.BasePermission):
    audience = "librarian"
    audience_description = "Librarians only."

    def has_permission(self, request, view):
        return is_librarian(request.user)
