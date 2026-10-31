from django.contrib import messages
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from authentication.decorators import signin_required

from .preferences import preference_books, set_preferences

ACTIONS = {
    "like": {"liked": True},
    "unlike": {"liked": False},
    "favorite": {"favorite": True},
    "unfavorite": {"favorite": False},
}


@signin_required
@never_cache
def my_preferences(request):
    if set(request.GET) - {"kind"}:
        return HttpResponseBadRequest("Only kind is accepted.")
    kind = request.GET.get("kind", "all")
    try:
        books = preference_books(request.user, kind)
    except ValueError as error:
        return HttpResponseBadRequest(str(error))
    return render(request, "book/book_preferences.html", {"books": books, "kind": kind})


@signin_required
@require_POST
def preference_update(request, book_id):
    if set(request.POST) - {"action", "csrfmiddlewaretoken"} or request.GET:
        return HttpResponseBadRequest("Only the preference action is accepted.")
    action = request.POST.get("action")
    if action not in ACTIONS:
        return HttpResponseBadRequest("Unknown preference action.")
    set_preferences(request.user, book_id, **ACTIONS[action])
    messages.success(request, "Your book preferences have been updated.")
    return redirect("book_detail", book_id=book_id)
