from django.shortcuts import render
from authentication.decorators import librarian_required
from .analytics import build_analytics_context


@librarian_required
def dashboard(request):
    return render(request, 'events/dashboard.html', build_analytics_context(request))
