from django.urls import path
from . import views

urlpatterns = [
    path('all/', views.order_all, name='order_all'),
    path('my/', views.order_my, name='order_my'),
    path('create/<int:book_id>/', views.order_create, name='order_create'),
    path('update/<int:order_id>/', views.order_update, name='order_update'),
    path('close/<int:order_id>/', views.order_close, name='order_close'),
]
