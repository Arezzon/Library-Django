"""Who may call each API operation (specs/003-priority-tech-debt/contracts/access-control.md).

The tables below are copied from that contract, so a change to who may call an operation
changes this file, the schema's audience labels and the README's API table together.
"""

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import URLResolver, get_resolver
from django.urls import path as django_path
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework.views import APIView

from author.models import Author
from book.models import Book
from book.testing import FakeEncoderMixin
from order.models import Order, Reservation

from .models import ROLE_LIBRARIAN, CustomUser

AUDIENCES = {
    "anonymous",
    "signed-in",
    "signed-in-read",
    "self-or-librarian",
    "librarian",
}

DUE = (timezone.now() + timedelta(days=14)).isoformat()
NAMES = {"first_name": "Renamed", "middle_name": "M", "last_name": "Reader"}
NEW_USER = {
    "first_name": "New",
    "middle_name": "M",
    "last_name": "Account",
    "email": "new-account@example.com",
    "password": "new-account-pass-1",
}
AUTHOR = {"name": "Taras", "surname": "Shevchenko"}
LOAN = {"book": "{book}", "plated_end_at": DUE}
LOAN_FOR_READER = {"user": "{reader}", **LOAN}
LOAN_FOR_OTHER = {"user": "{other}", **LOAN}
LOAN_FOR_LIBRARIAN = {"user": "{librarian}", **LOAN}
WHOLE_LOAN = {**LOAN_FOR_READER, "end_at": None}
REASON = {"reason": "Copy damaged"}
EVENT = {"event_type": "book_click", "book_id": "{book}", "path": "/book/"}

# (method, path, body, anonymous, reader, librarian): contracts/access-control.md,
# "API operations". {reader} is the signed-in reader; {other} is another reader.
OPERATIONS = [
    ("get", "/api/v1/", None, 200, 200, 200),
    ("get", "/api/v1/version/", None, 200, 200, 200),
    ("get", "/api/schema/", None, 200, 200, 200),
    ("get", "/api/docs/", None, 200, 200, 200),
    ("get", "/api/redoc/", None, 200, 200, 200),
    ("get", "/api/v1/books/search/?q=topic", None, 401, 200, 200),
    ("get", "/api/v1/book/", None, 401, 200, 200),
    ("get", "/api/v1/book/{book}/", None, 401, 200, 200),
    ("post", "/api/v1/book/", {"name": "New book", "count": 1}, 401, 403, 201),
    ("put", "/api/v1/book/{book}/", {"name": "Renamed", "count": 5}, 401, 403, 200),
    ("patch", "/api/v1/book/{book}/", {"count": 6}, 401, 403, 200),
    ("delete", "/api/v1/book/{free_book}/", None, 401, 403, 204),
    ("get", "/api/v1/author/", None, 401, 200, 200),
    ("get", "/api/v1/author/{author}/", None, 401, 200, 200),
    ("post", "/api/v1/author/", AUTHOR, 401, 403, 201),
    ("put", "/api/v1/author/{author}/", AUTHOR, 401, 403, 200),
    ("patch", "/api/v1/author/{author}/", {"name": "Lesya"}, 401, 403, 200),
    ("delete", "/api/v1/author/{author}/", None, 401, 403, 204),
    ("get", "/api/v1/user/", None, 401, 403, 200),
    ("post", "/api/v1/user/", NEW_USER, 401, 403, 201),
    ("get", "/api/v1/user/{reader}/", None, 401, 200, 200),
    ("get", "/api/v1/user/{other}/", None, 401, 404, 200),
    ("get", "/api/v1/user/999999/", None, 401, 404, 404),
    ("put", "/api/v1/user/{reader}/", NAMES, 401, 200, 200),
    ("patch", "/api/v1/user/{reader}/", NAMES, 401, 200, 200),
    ("put", "/api/v1/user/{other}/", NAMES, 401, 404, 200),
    ("patch", "/api/v1/user/{other}/", NAMES, 401, 404, 200),
    ("patch", "/api/v1/user/{reader}/", {"role": ROLE_LIBRARIAN}, 401, 403, 200),
    ("delete", "/api/v1/user/{other}/", None, 401, 403, 204),
    ("get", "/api/v1/order/", None, 401, 200, 200),
    ("get", "/api/v1/order/{own_loan}/", None, 401, 200, 200),
    ("get", "/api/v1/order/{other_loan}/", None, 401, 404, 200),
    # Only librarians start a loan; the fixture readers' loans are overdue, so the
    # rules refuse a loan to them after the access check (409).
    ("post", "/api/v1/order/", LOAN_FOR_READER, 401, 403, 409),
    ("post", "/api/v1/order/", LOAN_FOR_OTHER, 401, 403, 409),
    ("post", "/api/v1/order/", LOAN_FOR_LIBRARIAN, 401, 403, 201),
    ("put", "/api/v1/order/{own_loan}/", WHOLE_LOAN, 401, 403, 200),
    ("patch", "/api/v1/order/{own_loan}/", {"plated_end_at": DUE}, 401, 403, 200),
    ("delete", "/api/v1/order/{own_loan}/", None, 401, 403, 204),
    ("get", "/api/v1/user/{reader}/order/", None, 401, 200, 200),
    ("get", "/api/v1/user/{other}/order/", None, 401, 404, 200),
    ("post", "/api/v1/user/{reader}/order/", LOAN, 401, 403, 409),
    ("post", "/api/v1/user/{other}/order/", LOAN, 401, 404, 409),
    ("post", "/api/v1/user/{librarian}/order/", LOAN, 401, 404, 201),
    ("get", "/api/v1/user/{reader}/order/{own_loan}/", None, 401, 200, 200),
    ("get", "/api/v1/user/{other}/order/{other_loan}/", None, 401, 404, 200),
    ("put", "/api/v1/user/{reader}/order/{own_loan}/", WHOLE_LOAN, 401, 403, 200),
    ("patch", "/api/v1/user/{reader}/order/{own_loan}/", LOAN, 401, 403, 200),
    ("delete", "/api/v1/user/{reader}/order/{own_loan}/", None, 401, 403, 204),
    # Changing a loan is refused for readers whoever's account the route names.
    (
        "patch",
        "/api/v1/user/{other}/order/{other_loan}/",
        {"plated_end_at": DUE},
        401,
        403,
        200,
    ),
    ("post", "/api/v1/events/", EVENT, 401, 202, 202),
    ("get", "/api/v1/reservation/", None, 401, 200, 200),
    ("get", "/api/v1/reservation/{own_reservation}/", None, 401, 200, 200),
    ("get", "/api/v1/reservation/{other_reservation}/", None, 401, 404, 200),
    # The reader may reserve, but their loan is overdue, so the rules refuse it.
    ("post", "/api/v1/reservation/", {"book": "{free_book}"}, 401, 409, 201),
    ("post", "/api/v1/reservation/{own_reservation}/cancel/", REASON, 401, 200, 200),
    ("post", "/api/v1/reservation/{other_reservation}/cancel/", REASON, 401, 404, 200),
    # A librarian cancelling someone else's reservation gives a reason.
    ("post", "/api/v1/reservation/{own_reservation}/cancel/", None, 401, 200, 400),
    # The reservation's reader has an overdue loan, so the rules refuse to issue it.
    ("post", "/api/v1/reservation/{own_reservation}/issue/", None, 401, 403, 409),
]

# A sample of operations with the audience the contract gives them.
SCHEMA_AUDIENCES = {
    ("/api/v1/version/", "get"): "anonymous",
    ("/api/v1/books/search/", "get"): "signed-in",
    ("/api/v1/events/", "post"): "signed-in",
    ("/api/v1/book/", "get"): "signed-in-read",
    ("/api/v1/book/{id}/", "delete"): "signed-in-read",
    ("/api/v1/author/", "post"): "signed-in-read",
    ("/api/v1/user/", "get"): "librarian",
    ("/api/v1/user/", "post"): "librarian",
    ("/api/v1/user/{id}/", "get"): "self-or-librarian",
    ("/api/v1/user/{id}/", "patch"): "self-or-librarian",
    ("/api/v1/user/{id}/", "delete"): "librarian",
    ("/api/v1/order/", "get"): "signed-in",
    ("/api/v1/order/{id}/", "get"): "signed-in",
    ("/api/v1/order/", "post"): "librarian",
    ("/api/v1/order/{id}/", "put"): "librarian",
    ("/api/v1/user/{user_id}/order/", "post"): "librarian",
    ("/api/v1/user/{user_id}/order/{id}/", "get"): "self-or-librarian",
    ("/api/v1/user/{user_id}/order/{id}/", "delete"): "librarian",
    ("/api/v1/reservation/", "get"): "signed-in",
    ("/api/v1/reservation/", "post"): "signed-in",
    ("/api/v1/reservation/{id}/", "get"): "signed-in",
    ("/api/v1/reservation/{id}/cancel/", "post"): "signed-in",
    ("/api/v1/reservation/{id}/issue/", "post"): "librarian",
}


def account(email, role=0):
    return CustomUser.objects.create_user(
        email=email,
        password="access-password",
        first_name="Access",
        middle_name="",
        last_name="Test",
        role=role,
        is_active=True,
    )


def api_routes():
    """(route, view class) for every URL pattern under /api/v1/."""
    found = []

    def walk(patterns, prefix):
        for pattern in patterns:
            route = prefix + str(pattern.pattern)
            if isinstance(pattern, URLResolver):
                walk(pattern.url_patterns, route)
            elif route.startswith("api/v1/"):
                found.append((route, pattern.callback.cls))

    walk(get_resolver().url_patterns, "")
    return found


class UndeclaredView(APIView):
    """An API view that forgets to declare its audience."""

    def get(self, request):
        return Response({"record": "private"})


urlpatterns = [django_path("undeclared/", UndeclaredView.as_view())]


@override_settings(ROOT_URLCONF=__name__)
class DenyByDefaultTests(TestCase):
    def test_a_view_without_an_audience_refuses_every_caller(self):
        response = APIClient().get("/undeclared/")
        self.assertEqual(response.status_code, 401)
        client = APIClient()
        client.force_login(account("undeclared-librarian@example.com", ROLE_LIBRARIAN))
        response = client.get("/undeclared/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(set(response.json()), {"detail"})


class DeclaredAudienceTests(TestCase):
    def test_every_api_view_declares_its_own_permission_classes(self):
        routes = api_routes()
        names = {view.__name__ for _, view in routes}
        for expected in (
            "CustomUserViewSet",
            "AuthorViewSet",
            "BookViewSet",
            "BookSearchView",
            "OrderViewSet",
            "UserOrderViewSet",
            "ClientEventView",
            "VersionView",
        ):
            self.assertIn(expected, names)
        self.assertIn("api/v1/", [route for route, _ in routes])  # the API index
        for route, view in routes:
            with self.subTest(route=route):
                # Inheriting DRF's default is not a declaration (Principle II).
                self.assertIn(
                    "permission_classes",
                    vars(view),
                    f"{view.__name__} at {route} does not declare permission_classes",
                )


@patch("events.services.persist_event.apply_async")
class OperationAccessTests(FakeEncoderMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reader = account("access-reader@example.com")
        cls.other = account("access-other@example.com")
        cls.librarian = account("access-librarian@example.com", ROLE_LIBRARIAN)
        cls.book = Book.objects.create(name="Access book", count=5)
        cls.free_book = Book.objects.create(name="Never borrowed", count=1)
        cls.author = Author.objects.create(name="Lina", surname="Kostenko")
        cls.own_loan = Order.objects.create(
            user=cls.reader, book=cls.book, plated_end_at=timezone.now()
        )
        cls.other_loan = Order.objects.create(
            user=cls.other, book=cls.book, plated_end_at=timezone.now()
        )
        cls.own_reservation = Reservation.objects.create(user=cls.reader, book=cls.book)
        cls.other_reservation = Reservation.objects.create(
            user=cls.other, book=cls.book
        )

    def ids(self):
        return {
            "reader": self.reader.pk,
            "other": self.other.pk,
            "librarian": self.librarian.pk,
            "book": self.book.pk,
            "free_book": self.free_book.pk,
            "author": self.author.pk,
            "own_loan": self.own_loan.pk,
            "other_loan": self.other_loan.pk,
            "own_reservation": self.own_reservation.pk,
            "other_reservation": self.other_reservation.pk,
        }

    def api(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_login(user)
        return client

    def call(self, client, method, path, body=None):
        """Send one request and roll back whatever it changed."""
        ids = self.ids()
        if body is not None:
            body = {
                key: value.format(**ids) if isinstance(value, str) else value
                for key, value in body.items()
            }
            if "event_type" in body:
                body["event_id"] = str(uuid.uuid4())
        with transaction.atomic():
            response = getattr(client, method)(path.format(**ids), body, format="json")
            transaction.set_rollback(True)
        return response

    def assertRefusedWithoutData(self, response):
        # FR-004: a refusal carries a message and no field of the record.
        self.assertEqual(set(response.json()), {"detail"})

    def test_each_operation_answers_each_caller_as_the_contract_says(self, _publish):
        callers = {
            "anonymous": self.api(),
            "reader": self.api(self.reader),
            "librarian": self.api(self.librarian),
        }
        for method, path, body, *expected in OPERATIONS:
            for (caller, client), status in zip(callers.items(), expected, strict=True):
                with self.subTest(caller=caller, method=method.upper(), path=path):
                    response = self.call(client, method, path, body)
                    self.assertEqual(
                        response.status_code, status, response.content[:300]
                    )
                    if status == 401:
                        self.assertEqual(response["WWW-Authenticate"], "Session")
                    if status in (401, 403, 404):
                        self.assertRefusedWithoutData(response)

    def test_readers_list_only_their_own_loans(self, _publish):
        own = self.api(self.reader).get("/api/v1/order/").json()
        self.assertEqual([loan["id"] for loan in own], [self.own_loan.pk])
        every = self.api(self.librarian).get("/api/v1/order/").json()
        self.assertCountEqual(
            [loan["id"] for loan in every], [self.own_loan.pk, self.other_loan.pk]
        )

    def test_reader_cannot_change_own_role_status_email_or_password(self, _publish):
        client = self.api(self.reader)
        before = CustomUser.objects.values().get(pk=self.reader.pk)
        for field, value in (
            ("role", ROLE_LIBRARIAN),
            ("is_active", False),
            ("email", "taken-over@example.com"),
            ("password", "chosen-by-the-reader-1"),
        ):
            with self.subTest(field=field):
                response = client.patch(
                    f"/api/v1/user/{self.reader.pk}/",
                    {"first_name": "Changed", field: value},
                    format="json",
                )
                self.assertEqual(response.status_code, 403)
                self.assertRefusedWithoutData(response)
                self.assertEqual(
                    CustomUser.objects.values().get(pk=self.reader.pk), before
                )

    def test_a_body_that_is_not_an_object_is_a_bad_request(self, _publish):
        for user, method, path in (
            (self.reader, "patch", f"/api/v1/user/{self.reader.pk}/"),
            (self.librarian, "patch", f"/api/v1/user/{self.reader.pk}/"),
            (self.librarian, "post", "/api/v1/order/"),
            (self.librarian, "post", f"/api/v1/user/{self.reader.pk}/order/"),
        ):
            for body in ([{"role": ROLE_LIBRARIAN}], 5):
                with self.subTest(user=user.email, method=method, body=body):
                    response = getattr(self.api(user), method)(
                        path, body, format="json"
                    )
                    self.assertEqual(response.status_code, 400)

    def test_librarian_sets_a_password_that_is_stored_hashed(self, _publish):
        response = self.api(self.librarian).patch(
            f"/api/v1/user/{self.reader.pk}/",
            {"password": "fresh-reader-pass-1"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("password", response.json())
        self.reader.refresh_from_db()
        self.assertNotEqual(self.reader.password, "fresh-reader-pass-1")
        self.assertTrue(self.reader.check_password("fresh-reader-pass-1"))

    def test_only_librarians_start_a_loan(self, _publish):
        client = self.api(self.reader)
        loan = {"book": self.book.pk, "plated_end_at": DUE}
        for path, body in (
            ("/api/v1/order/", {**loan, "user": self.reader.pk}),
            ("/api/v1/order/", {**loan, "user": self.other.pk}),
            (f"/api/v1/user/{self.reader.pk}/order/", loan),
        ):
            with self.subTest(path=path, body=body):
                response = client.post(path, body, format="json")
                self.assertEqual(response.status_code, 403)
                self.assertRefusedWithoutData(response)
        self.assertEqual(Order.objects.count(), 2)
        response = self.api(self.librarian).post(
            "/api/v1/order/", {**loan, "user": self.librarian.pk}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.json())
        self.assertEqual(Order.objects.filter(user=self.librarian).count(), 1)


class SchemaAudienceTests(TestCase):
    def schema(self):
        response = self.client.get("/api/schema/?format=json")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def operations(self):
        for path, item in self.schema()["paths"].items():
            for method, operation in item.items():
                if method in ("get", "post", "put", "patch", "delete"):
                    yield path, method, operation

    def test_every_operation_states_its_audience_and_refusals(self):
        operations = list(self.operations())
        self.assertGreater(len(operations), 20)
        for path, method, operation in operations:
            with self.subTest(path=path, method=method):
                audience = operation.get("x-audience")
                self.assertIn(audience, AUDIENCES)
                self.assertRegex(
                    operation.get("description", ""), r"Audience: [^\n]+\.$"
                )
                if audience != "anonymous":
                    self.assertIn("401", operation["responses"])
                    self.assertIn("403", operation["responses"])

    def test_operations_carry_the_audience_in_the_contract(self):
        audiences = {
            (path, method): operation.get("x-audience")
            for path, method, operation in self.operations()
        }
        for key, expected in SCHEMA_AUDIENCES.items():
            with self.subTest(operation=key):
                self.assertEqual(audiences.get(key), expected)

    def test_own_record_operations_document_not_found(self):
        responses = {
            (path, method): operation["responses"]
            for path, method, operation in self.operations()
        }
        for key in (
            ("/api/v1/user/{id}/", "get"),
            ("/api/v1/order/{id}/", "get"),
            ("/api/v1/user/{user_id}/order/", "get"),
        ):
            with self.subTest(operation=key):
                self.assertIn("404", responses[key])

    def test_protected_operations_document_session_sign_in(self):
        schema = self.schema()
        self.assertEqual(
            schema["components"]["securitySchemes"],
            {"cookieAuth": {"type": "apiKey", "in": "cookie", "name": "sessionid"}},
        )
        self.assertEqual(
            schema["paths"]["/api/v1/book/"]["get"]["security"], [{"cookieAuth": []}]
        )

    def test_refusals_document_the_detail_body(self):
        schema = self.schema()
        responses = schema["paths"]["/api/v1/user/{id}/"]["get"]["responses"]
        for status in ("401", "403", "404"):
            with self.subTest(status=status):
                body = responses[status]["content"]["application/json"]["schema"]
                if "$ref" in body:
                    body = schema["components"]["schemas"][body["$ref"].split("/")[-1]]
                self.assertEqual(body["properties"]["detail"]["type"], "string")
