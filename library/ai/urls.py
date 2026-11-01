from django.urls import path

from .api_views import CatalogAssistantView

app_name = "ai"
urlpatterns = [path("", CatalogAssistantView.as_view(), name="catalog-assistant")]
