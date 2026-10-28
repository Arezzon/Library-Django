from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def _sign_in_first(request):
    """Send an anonymous caller to the sign-in page, which says why."""
    messages.info(request, "Sign in to continue.")
    return redirect_to_login(request.get_full_path(), "login")


def signin_required(view_func):
    """
    Decorator that ensures the user is signed in.
    If not, redirects to 'login' with the requested page as `next`.
    """

    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return _sign_in_first(request)
        return view_func(request, *args, **kwargs)

    return _wrapped_view


def librarian_required(view_func):
    """
    Decorator that ensures the user is signed in and is a librarian.
    If not signed in, redirects to 'login' with the requested page as `next`.
    If signed in but not a librarian, answers 403.
    """

    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return _sign_in_first(request)
        if not request.user.is_librarian:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return _wrapped_view


def librarian_or_owner_required(user_id_param="user_id"):
    """
    Decorator that allows access only to librarians or the owner of the resource (matching `user_id_param`).
    If not signed in, redirects to 'login' with the requested page as `next`.
    If neither librarian nor the owner, answers 403 before the record is looked up.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return _sign_in_first(request)

            user_id = kwargs.get(user_id_param)
            is_owner = (
                str(request.user.id) == str(user_id) if user_id is not None else False
            )

            if not (request.user.is_librarian or is_owner):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


def role_required(*allowed_roles):
    """
    Decorator that checks if the authenticated user has one of the allowed roles.
    If not signed in, redirects to 'login'; with another role, answers 403.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return _sign_in_first(request)
            if request.user.role not in allowed_roles:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator
