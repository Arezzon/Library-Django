from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from authentication.decorators import signin_required

from .rating_forms import BookRatingForm
from .ratings import require_rating_account, set_rating
from .views import book_detail


@signin_required
@never_cache
@require_POST
def rating_update(request, book_id):
    require_rating_account(request.user)
    form = BookRatingForm(request.POST)
    action = request.POST.get("action")
    if (
        request.GET
        or set(request.POST) - {"value", "action", "csrfmiddlewaretoken"}
        or any(len(request.POST.getlist(key)) != 1 for key in request.POST)
    ):
        form.add_error(None, "Only your rating action and value are accepted.")
    elif action == "remove" and "value" not in request.POST:
        set_rating(request.user, book_id, None)
        messages.success(request, "Your rating has been removed.")
        return redirect(
            reverse("book_detail", kwargs={"book_id": book_id}) + "#book-rating"
        )
    elif action != "set":
        form.add_error(None, "Choose Save rating or Remove rating.")
    elif form.is_valid():
        set_rating(request.user, book_id, form.cleaned_data["value"])
        messages.success(request, "Your rating has been saved.")
        return redirect(
            reverse("book_detail", kwargs={"book_id": book_id}) + "#book-rating"
        )
    form.fields["value"].widget.attrs["aria-invalid"] = "true"
    return book_detail(request, book_id, rating_form=form, status=400)
