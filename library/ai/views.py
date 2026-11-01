"""Server-rendered reader flow; private questions travel in CSRF-protected POSTs."""

import logging

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from authentication.decorators import signin_required
from authentication.permissions import is_signed_in

from .forms import AssistantQuestionForm
from .services import catalog_assistant

logger = logging.getLogger("ai")


@signin_required
@never_cache
@require_http_methods(["GET", "POST"])
def assistant_page(request):
    if not is_signed_in(request.user):
        raise PermissionDenied
    if request.GET:
        return redirect("assistant-page")
    form = AssistantQuestionForm(request.POST if request.method == "POST" else None)
    result = None
    status = 200
    if request.method == "POST":
        if set(request.POST) - {"q", "intent", "csrfmiddlewaretoken"} or any(
            len(request.POST.getlist(key)) != 1 for key in request.POST
        ):
            form.add_error(None, "Send one question and one search type.")
        if form.is_valid():
            result = catalog_assistant(
                request.user, form.cleaned_data["q"], form.cleaned_data["intent"]
            )
            status = 503 if result["status"] == "source_unavailable" else 200
            if status == 503:
                # The shared notices join catalog tables too. Do not requery a
                # failed source while rendering the assistant outage response.
                request.reservation_notices = []
            # Fixed status vocabulary only: never log question, result, user or form.
            logger.info("Catalog assistant response: status=%s", result["status"])
        else:
            status = 400
            form.fields["q"].widget.attrs["aria-invalid"] = "true"
            logger.info("Catalog assistant response: status=invalid_request")
    response = render(
        request, "ai/assistant.html", {"form": form, "result": result}, status=status
    )
    response["Referrer-Policy"] = "same-origin"
    if status == 503:
        response["Retry-After"] = "5"
    return response
