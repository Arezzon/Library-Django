from django.urls import path

from . import preference_views, views

urlpatterns = [
    path("preferences/", preference_views.my_preferences, name="my_book_preferences"),
    path(
        "<int:book_id>/preferences/",
        preference_views.preference_update,
        name="book_preference_update",
    ),
    path("", views.book_list, name="book_list"),
    path("create/", views.book_create, name="book_create"),
    path("update/<int:book_id>/", views.book_update, name="book_update"),
    path("delete/<int:book_id>/", views.book_delete, name="book_delete"),
    path("<int:book_id>/", views.book_detail, name="book_detail"),
    path("user/<int:user_id>/", views.books_by_user, name="books_by_user"),
]
