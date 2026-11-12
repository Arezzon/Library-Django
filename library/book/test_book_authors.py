"""Book.remove_authors removes only the authors it is given (KAN-78)."""

from django.test import TestCase

from author.models import Author

from .models import Book
from .testing import FakeEncoderMixin


class BookAuthorRemovalTests(FakeEncoderMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.first = Author.create("Ivan", "Franko", "Yakovych")
        cls.second = Author.create("Lesia", "Ukrainka", "Petrivna")
        cls.third = Author.create("Taras", "Shevchenko", "Hryhorovych")

    def book(self, *authors):
        return Book.create("Kobzar", "Description", authors=list(authors))

    def assert_authors(self, book, authors):
        # Read from the database, not from the object in memory.
        stored = Book.objects.get(pk=book.pk)
        self.assertEqual(
            set(stored.authors.values_list("pk", flat=True)),
            {author.pk for author in authors},
        )

    def test_removes_only_the_given_author(self):
        book = self.book(self.first, self.second)
        book.remove_authors([self.first])
        self.assert_authors(book, [self.second])

    def test_empty_list_changes_nothing(self):
        book = self.book(self.first)
        book.remove_authors([])
        self.assert_authors(book, [self.first])

    def test_none_changes_nothing(self):
        book = self.book(self.first)
        book.remove_authors(None)
        self.assert_authors(book, [self.first])

    def test_removing_twice_keeps_the_others(self):
        book = self.book(self.first, self.second)
        book.remove_authors([self.first])
        book.remove_authors([self.first])
        self.assert_authors(book, [self.second])

    def test_an_author_the_book_lacks_changes_nothing(self):
        book = self.book(self.first)
        book.remove_authors([self.third])
        self.assert_authors(book, [self.first])

    def test_removes_several_authors(self):
        book = self.book(self.first, self.second, self.third)
        book.remove_authors([self.first, self.third])
        self.assert_authors(book, [self.second])

    def test_author_records_are_kept(self):
        book = self.book(self.first, self.second)
        other = Book.create("Zakhar Berkut", "Description", authors=[self.first])
        book.remove_authors([self.first, self.second])
        self.assert_authors(book, [])
        self.assert_authors(other, [self.first])
        self.assertEqual(
            set(Author.objects.values_list("pk", flat=True)),
            {self.first.pk, self.second.pk, self.third.pk},
        )
