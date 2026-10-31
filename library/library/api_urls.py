from django.urls import include, path
from rest_framework.permissions import AllowAny
from rest_framework.routers import APIRootView, DefaultRouter

from authentication.api_views import CustomUserViewSet
from author.api_views import AuthorViewSet
from book.api_views import BookRecommendationsView, BookSearchView, BookViewSet
from events.api_views import ClientEventView
from order.api_views import OrderViewSet, ReservationViewSet, UserOrderViewSet

from .api_views import VersionView


class IndexView(APIRootView):
    """The index of the API's resources, which anyone may read (FR-003)."""

    permission_classes = [AllowAny]


class Router(DefaultRouter):
    APIRootView = IndexView


router = Router()
router.register(r"user", CustomUserViewSet, basename="user")
router.register(r"author", AuthorViewSet, basename="author")
router.register(r"book", BookViewSet, basename="book")
router.register(r"order", OrderViewSet, basename="order")
router.register(r"reservation", ReservationViewSet, basename="reservation")

urlpatterns = [
    path(
        "books/recommendations/",
        BookRecommendationsView.as_view(),
        name="book-recommendations",
    ),
    path("books/search/", BookSearchView.as_view(), name="book-search"),
    path("events/", ClientEventView.as_view(), name="client-event"),
    path("version/", VersionView.as_view(), name="version"),
    path("", include(router.urls)),
    # /api/v1/user/{user_id}/order/{id}?
    path(
        "user/<int:user_id>/order/",
        UserOrderViewSet.as_view({"get": "list", "post": "create"}),
        name="user-order-list",
    ),
    path(
        "user/<int:user_id>/order/<int:pk>/",
        UserOrderViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="user-order-detail",
    ),
]
