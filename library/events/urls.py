from django.urls import path

from .views import activity_log, overview

urlpatterns = [
    path("", overview, name="events_dashboard"),
    path("activity/", activity_log, name="events_activity"),
]
