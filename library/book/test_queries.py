"""Each book list loads in a fixed number of queries (research R8, FR-047)."""

from datetime import timedelta

from django.http import HttpResponse
from django.test import TestCase, override_settings
from django.urls import path, reverse
from django.utils import timezone

from authentication.models import CustomUser
from author.models import Author
from library.testing import assert_same_query_count
from order.models import Order

from .models import Book
from .search import RESULT_LIMIT
from .testing import FakeEncoderMixin


def loan_counts(request):
    """One query per book: the pattern the helper exists to catch."""
    books = Book.objects.order_by("id")
    return HttpResponse(" ".join(str(book.order_set.count()) for book in books))


def book_names(request):
    return HttpResponse(" ".join(Book.objects.values_list("name", flat=True)))


urlpatterns = [path("loan-counts/", loan_counts), path("book-names/", book_names)]


def add_books(count):
    for _ in range(count):
        Book.objects.create(name="Counted book", count=1)


@override_settings(ROOT_URLCONF=__name__)
class QueryCountHelperTests(FakeEncoderMixin, TestCase):
    def test_a_list_that_queries_once_per_row_fails(self):
        with self.assertRaises(AssertionError):
            assert_same_query_count(self, self.client, "/loan-counts/", add_books)

    def test_a_list_with_a_fixed_number_of_queries_passes(self):
        assert_same_query_count(self, self.client, "/book-names/", add_books)


class BookListQueryTests(FakeEncoderMixin, TestCase):
    """Each book has an author and a copy on loan, so every column is filled."""

    @classmethod
    def setUpTestData(cls):
        cls.reader = CustomUser.objects.create_user(
            email="queries-reader@example.com",
            password="queries-password",
            first_name="Query",
            middle_name="",
            last_name="Reader",
            is_active=True,
        )
        cls.author = Author.objects.create(name="Lina", surname="Kostenko")

    def setUp(self):
        self.client.force_login(self.reader)

    def add_books(self, count):
        for _ in range(count):
            book = Book.objects.create(name="Catalog book", count=2)
            book.authors.add(self.author)
            Order.objects.create(
                user=self.reader,
                book=book,
                plated_end_at=timezone.now() + timedelta(days=14),
            )

    def test_the_book_list(self):
        response = assert_same_query_count(
            self, self.client, reverse("book_list"), self.add_books
        )
        self.assertEqual(len(response.context["books"]), 50)

    def test_the_book_list_filtered_by_author(self):
        url = f"{reverse('book_list')}?author_id={self.author.pk}"
        response = assert_same_query_count(self, self.client, url, self.add_books)
        self.assertEqual(len(response.context["books"]), 50)

    def test_the_api_book_list(self):
        response = assert_same_query_count(
            self, self.client, "/api/v1/book/", self.add_books
        )
        self.assertEqual(len(response.json()), 50)

    def test_the_api_search(self):
        response = assert_same_query_count(
            self, self.client, "/api/v1/books/search/?q=catalog", self.add_books
        )
        self.assertEqual(len(response.json()), RESULT_LIMIT)
