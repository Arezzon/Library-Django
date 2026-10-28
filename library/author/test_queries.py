"""Each author list loads in a fixed number of queries (research R8, FR-047)."""

from django.test import TestCase
from django.urls import reverse

from authentication.models import ROLE_LIBRARIAN, CustomUser
from book.models import Book
from book.testing import FakeEncoderMixin
from library.testing import assert_same_query_count

from .models import Author


class AuthorListQueryTests(FakeEncoderMixin, TestCase):
    """Each author is linked to 3 books."""

    @classmethod
    def setUpTestData(cls):
        cls.librarian = CustomUser.objects.create_user(
            email="queries-librarian@example.com",
            password="queries-password",
            first_name="Query",
            middle_name="",
            last_name="Librarian",
            role=ROLE_LIBRARIAN,
            is_active=True,
        )
        cls.books = [Book.objects.create(name="Shelf book", count=1) for _ in range(3)]

    def setUp(self):
        self.client.force_login(self.librarian)

    def add_authors(self, count):
        for _ in range(count):
            author = Author.objects.create(name="Counted", surname="Author")
            author.books.add(*self.books)

    def test_the_author_list(self):
        response = assert_same_query_count(
            self, self.client, reverse("author_list"), self.add_authors
        )
        self.assertEqual(len(response.context["authors"]), 50)

    def test_the_api_author_list(self):
        response = assert_same_query_count(
            self, self.client, "/api/v1/author/", self.add_authors
        )
        self.assertEqual(len(response.json()), 50)
        self.assertEqual(len(response.json()[0]["books"]), 3)
