from django.shortcuts import render

from authentication.decorators import librarian_required

from .analytics import build_analytics_context
from .forecast_page import forecast_page_context
from .overview_page import overview_page_context


@librarian_required
def overview(request):
    context = overview_page_context(request.GET.get("period", ""))
    return render(request, "events/overview.html", context)


@librarian_required
def forecast(request):
    return render(request, "events/forecast.html", forecast_page_context())


@librarian_required
def activity_log(request):
    return render(request, "events/dashboard.html", build_analytics_context(request))
