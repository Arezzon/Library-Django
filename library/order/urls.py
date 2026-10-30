from django.urls import path

from . import views

urlpatterns = [
    path("all/", views.order_all, name="order_all"),
    path("my/", views.order_my, name="order_my"),
    path("create/<int:book_id>/", views.order_create, name="order_create"),
    path("update/<int:order_id>/", views.order_update, name="order_update"),
    path("close/<int:order_id>/", views.order_close, name="order_close"),
    path("lend/", views.order_lend, name="order_lend"),
    path("reserve/<int:book_id>/", views.reserve, name="reserve"),
    path("reservations/", views.reservation_my, name="reservation_my"),
    path("reservations/desk/", views.reservation_desk, name="reservation_desk"),
    path(
        "reservations/<int:reservation_id>/issue/",
        views.reservation_issue,
        name="reservation_issue",
    ),
    path(
        "reservations/<int:reservation_id>/cancel/",
        views.reservation_cancel,
        name="reservation_cancel",
    ),
    path(
        "reservations/<int:reservation_id>/notice/dismiss/",
        views.reservation_notice_dismiss,
        name="reservation_notice_dismiss",
    ),
]
