from django.urls import path
from . import views

urlpatterns = [
    path('', views.book_list, name='book_list'),
    path('create/', views.book_create, name='book_create'),
    path('update/<int:book_id>/', views.book_update, name='book_update'),
    path('<int:book_id>/', views.book_detail, name='book_detail'),
    path('user/<int:user_id>/', views.books_by_user, name='books_by_user'),
]
