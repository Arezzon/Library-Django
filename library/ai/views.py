"""Server-rendered reader flow; private questions travel in CSRF-protected POSTs."""

import logging

from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from authentication.decorators import signin_required
from authentication.permissions import is_signed_in

from .context import (
    clear_context,
    read_context,
    read_page_result,
    remember_page_result,
    remember_result,
)
from .forms import AssistantQuestionForm
from .language import parse_query
from .services import catalog_assistant, catalog_page_result

logger = logging.getLogger("ai")


@signin_required
@never_cache
@require_http_methods(["GET", "POST"])
def assistant_page(request):
    if not is_signed_in(request.user):
        raise PermissionDenied
    if request.GET:
        return redirect("assistant-page")
    if request.method == "GET":
        clear_context(request.session)
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
                request.user,
                form.cleaned_data["q"],
                form.cleaned_data["intent"],
                context_book_ids=read_context(request.session, request.user),
            )
            remember_result(request.session, request.user, result)
            status = 503 if result["status"] == "source_unavailable" else 200
            if status != 503:
                remember_page_result(
                    request.session,
                    request.user,
                    result,
                    available_only=parse_query(
                        form.cleaned_data["q"], form.cleaned_data["intent"]
                    ).available_only,
                )
                logger.info("Catalog assistant response: status=%s", result["status"])
                return HttpResponseRedirect(
                    reverse("assistant-result") + "#assistant-result", status=303
                )
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
    return _render_assistant(request, form, result, status)


def _render_assistant(request, form, result, status):
    if status == 503:
        request.reservation_notices = []
    response = render(
        request, "ai/assistant.html", {"form": form, "result": result}, status=status
    )
    response["Referrer-Policy"] = "same-origin"
    if status == 503:
        response["Retry-After"] = "5"
    return response


@signin_required
@never_cache
@require_GET
def assistant_result(request):
    if not is_signed_in(request.user):
        raise PermissionDenied
    if request.GET:
        return redirect("assistant-page")
    state = read_page_result(request.session, request.user)
    if state is None:
        return redirect("assistant-page")
    result = catalog_page_result(request.user, state)
    status = 503 if result["status"] == "source_unavailable" else 200
    return _render_assistant(request, AssistantQuestionForm(), result, status)
