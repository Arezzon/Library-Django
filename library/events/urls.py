from django.urls import path

from .views import activity_log, forecast, overview

urlpatterns = [
    path("", overview, name="events_dashboard"),
    path("activity/", activity_log, name="events_activity"),
    path("forecast/", forecast, name="events_forecast"),
]
