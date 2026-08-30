from django.urls import path, include
from rest_framework.routers import DefaultRouter

from authentication.api_views import CustomUserViewSet
from author.api_views import AuthorViewSet
from book.api_views import BookViewSet
from order.api_views import OrderViewSet, UserOrderViewSet

router = DefaultRouter()
router.register(r'user', CustomUserViewSet, basename='user')
router.register(r'author', AuthorViewSet, basename='author')
router.register(r'book', BookViewSet, basename='book')
router.register(r'order', OrderViewSet, basename='order')

urlpatterns = [
    path('', include(router.urls)),

    #/api/v1/user/{user_id}/order/{id}?
    path(
        'user/<int:user_id>/order/',
        UserOrderViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='user-order-list'
    ),
    path(
        'user/<int:user_id>/order/<int:pk>/',
        UserOrderViewSet.as_view({
            'get': 'retrieve',
            'put': 'update',
            'patch': 'partial_update',
            'delete': 'destroy'
        }),
        name='user-order-detail'
    ),
]
