from functools import wraps
from django.shortcuts import redirect
from .models import ROLE_LIBRARIAN


def librarian_required(view_func):
    """
    Decorator that ensures the user is authenticated and has the ROLE_LIBRARIAN role.
    If not authenticated, redirects to 'login'.
    If authenticated but not a librarian, redirects to 'home'.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if getattr(request.user, 'role', None) != ROLE_LIBRARIAN:
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def librarian_or_owner_required(user_id_param='user_id'):
    """
    Decorator that allows access only to librarians or the owner of the resource (matching `user_id_param`).
    If not authenticated, redirects to 'login'.
    If neither librarian nor the owner, redirects to 'home'.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            user_id = kwargs.get(user_id_param)
            is_librarian = getattr(request.user, 'role', None) == ROLE_LIBRARIAN
            is_owner = str(request.user.id) == str(user_id) if user_id is not None else False

            if not (is_librarian or is_owner):
                return redirect('home')
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def role_required(*allowed_roles):
    """
    Decorator that checks if the authenticated user has one of the allowed roles.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if getattr(request.user, 'role', None) not in allowed_roles:
                return redirect('home')
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
