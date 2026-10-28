"""Each loan list loads in a fixed number of queries (research R8, FR-047)."""

from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from authentication.models import ROLE_LIBRARIAN, CustomUser
from book.models import Book
from book.testing import FakeEncoderMixin
from library.testing import assert_same_query_count

from .models import Order


def account(email, role=CustomUser.ROLE_VISITOR):
    return CustomUser.objects.create_user(
        email=email,
        password="queries-password",
        first_name="Query",
        middle_name="",
        last_name="Account",
        role=role,
        is_active=True,
    )


class LoanListQueryTests(FakeEncoderMixin, TestCase):
    """Every loan is the reader's and still open, so it shows in every list."""

    @classmethod
    def setUpTestData(cls):
        cls.reader = account("queries-reader@example.com")
        cls.librarian = account("queries-librarian@example.com", ROLE_LIBRARIAN)
        cls.book = Book.objects.create(name="Popular book", count=100)

    def signed_in(self, user):
        client = Client()
        client.force_login(user)
        return client

    def add_loans(self, count):
        for _ in range(count):
            Order.objects.create(
                user=self.reader,
                book=self.book,
                plated_end_at=timezone.now() + timedelta(days=14),
            )

    def test_all_loans(self):
        response = assert_same_query_count(
            self, self.signed_in(self.librarian), reverse("order_all"), self.add_loans
        )
        self.assertEqual(len(response.context["orders"]), 50)

    def test_my_loans(self):
        response = assert_same_query_count(
            self, self.signed_in(self.reader), reverse("order_my"), self.add_loans
        )
        self.assertEqual(len(response.context["orders"]), 50)

    def test_a_readers_books(self):
        url = reverse("books_by_user", args=[self.reader.pk])
        response = assert_same_query_count(
            self, self.signed_in(self.librarian), url, self.add_loans
        )
        self.assertEqual(len(response.context["active_orders"]), 50)

    def test_the_api_loan_list(self):
        response = assert_same_query_count(
            self, self.signed_in(self.librarian), "/api/v1/order/", self.add_loans
        )
        self.assertEqual(len(response.json()), 50)

    def test_the_api_list_of_one_users_loans(self):
        url = f"/api/v1/user/{self.reader.pk}/order/"
        response = assert_same_query_count(
            self, self.signed_in(self.reader), url, self.add_loans
        )
        self.assertEqual(len(response.json()), 50)
