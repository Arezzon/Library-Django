"""Who may open each web route (specs/003-priority-tech-debt/contracts/access-control.md).

The table below is copied from the contract's "Web routes", so every protected route is
checked with at least one permitted and one refused caller (FR-049).
"""

from datetime import timedelta

from django.db import transaction
from django.test import Client, TestCase
from django.utils import timezone

from author.models import Author
from book.models import Book
from book.testing import FakeEncoderMixin
from order.models import Order

from .models import ROLE_LIBRARIAN, CustomUser

PAGE = 200
FORBIDDEN = 403
SIGN_IN = "sign in"  # /authentication/login/?next=<the route>
LOGIN = "/authentication/login/"
HOME = "/"
ADMIN_SIGN_IN = "/admin/login/?next=/admin/"

# (method, route, anonymous, reader, librarian): an expected status, or where the
# caller is redirected. {reader} is the signed-in reader; {other} is another reader.
ROUTES = [
    ("get", "/authentication/login/", PAGE, HOME, HOME),
    ("get", "/authentication/register/", PAGE, HOME, HOME),
    ("get", "/authentication/", LOGIN, HOME, HOME),
    ("get", "/", LOGIN, PAGE, PAGE),
    ("get", "/book/", SIGN_IN, PAGE, PAGE),
    ("get", "/book/{book}/", SIGN_IN, PAGE, PAGE),
    ("get", "/book/create/", SIGN_IN, FORBIDDEN, PAGE),
    ("get", "/book/update/{book}/", SIGN_IN, FORBIDDEN, PAGE),
    ("get", "/book/user/{reader}/", SIGN_IN, FORBIDDEN, PAGE),
    ("post", "/book/delete/{free_book}/", SIGN_IN, FORBIDDEN, "/book/"),
    # A book with borrowing history is refused, back on its edit page.
    ("post", "/book/delete/{book}/", SIGN_IN, FORBIDDEN, "/book/update/{book}/"),
    ("get", "/author/", SIGN_IN, FORBIDDEN, PAGE),
    ("get", "/author/create/", SIGN_IN, FORBIDDEN, PAGE),
    ("get", "/author/update/{author}/", SIGN_IN, FORBIDDEN, PAGE),
    ("post", "/author/delete/{author}/", SIGN_IN, FORBIDDEN, "/author/"),
    ("get", "/order/my/", SIGN_IN, PAGE, PAGE),
    ("get", "/order/create/{free_book}/", SIGN_IN, PAGE, PAGE),
    ("get", "/order/reservations/", SIGN_IN, PAGE, PAGE),
    (
        "post",
        "/order/reserve/{free_book}/",
        SIGN_IN,
        "/order/reservations/",
        "/order/reservations/",
    ),
    ("get", "/order/all/", SIGN_IN, FORBIDDEN, PAGE),
    ("get", "/order/update/{loan}/", SIGN_IN, FORBIDDEN, PAGE),
    ("post", "/order/close/{loan}/", SIGN_IN, FORBIDDEN, "/order/all/"),
    ("get", "/authentication/users/", SIGN_IN, FORBIDDEN, PAGE),
    ("get", "/authentication/users/{reader}/", SIGN_IN, PAGE, PAGE),
    ("get", "/authentication/users/{other}/", SIGN_IN, FORBIDDEN, PAGE),
    ("get", "/authentication/users/{reader}/update/", SIGN_IN, PAGE, PAGE),
    ("get", "/authentication/users/{other}/update/", SIGN_IN, FORBIDDEN, PAGE),
    ("get", "/events/", SIGN_IN, FORBIDDEN, PAGE),
    ("get", "/admin/", ADMIN_SIGN_IN, ADMIN_SIGN_IN, PAGE),
]


def account(email, role=CustomUser.ROLE_VISITOR):
    return CustomUser.objects.create_user(
        email=email,
        password="routes-password",
        first_name="Route",
        middle_name="",
        last_name="Test",
        role=role,
        is_active=True,
    )


class WebRouteAccessTests(FakeEncoderMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reader = account("routes-reader@example.com")
        cls.other = account("routes-other@example.com")
        cls.librarian = account("routes-librarian@example.com", ROLE_LIBRARIAN)
        cls.book = Book.objects.create(name="Borrowed book", count=2)
        cls.free_book = Book.objects.create(name="Never borrowed", count=1)
        cls.author = Author.objects.create(name="Lina", surname="Kostenko")
        cls.loan = Order.objects.create(
            user=cls.reader,
            book=cls.book,
            plated_end_at=timezone.now() + timedelta(days=14),
        )

    def ids(self):
        return {
            "reader": self.reader.pk,
            "other": self.other.pk,
            "book": self.book.pk,
            "free_book": self.free_book.pk,
            "author": self.author.pk,
            "loan": self.loan.pk,
        }

    def signed_in(self, user=None):
        client = Client()
        if user is not None:
            client.force_login(user)
        return client

    def call(self, client, method, route):
        """Send one request and roll back whatever it changed."""
        with transaction.atomic():
            response = getattr(client, method)(route)
            transaction.set_rollback(True)
        return response

    def test_each_route_answers_each_caller_as_the_contract_says(self):
        callers = {
            "anonymous": self.signed_in(),
            "reader": self.signed_in(self.reader),
            "librarian": self.signed_in(self.librarian),
        }
        for method, route, *expected in ROUTES:
            route = route.format(**self.ids())
            for (caller, client), outcome in zip(
                callers.items(), expected, strict=True
            ):
                with self.subTest(caller=caller, method=method.upper(), route=route):
                    response = self.call(client, method, route)
                    if outcome in (PAGE, FORBIDDEN):
                        self.assertEqual(response.status_code, outcome)
                    else:
                        target = (
                            f"{LOGIN}?next={route}"
                            if outcome == SIGN_IN
                            else outcome.format(**self.ids())
                        )
                        self.assertRedirects(
                            response, target, fetch_redirect_response=False
                        )

    def test_every_protected_route_has_a_permitted_and_a_refused_caller(self):
        refusals = {SIGN_IN, LOGIN, FORBIDDEN, ADMIN_SIGN_IN}
        for _method, route, *expected in ROUTES:
            if route in ("/authentication/login/", "/authentication/register/"):
                continue  # open to everyone; signed-in callers are sent home
            with self.subTest(route=route):
                self.assertTrue(refusals & set(expected), f"{route} refuses nobody")
                self.assertTrue(set(expected) - refusals, f"{route} permits nobody")

    def test_signing_out_ends_the_session_and_returns_to_sign_in(self):
        self.assertRedirects(
            self.signed_in().get("/authentication/logout/"),
            LOGIN,
            fetch_redirect_response=False,
        )
        for user in (self.reader, self.librarian):
            with self.subTest(user=user.email):
                client = self.signed_in(user)
                self.assertRedirects(
                    client.get("/authentication/logout/"),
                    LOGIN,
                    fetch_redirect_response=False,
                )
                self.assertRedirects(
                    client.get("/"), LOGIN, fetch_redirect_response=False
                )
