"""Book.create with and without authors (KAN-77)."""

from django.test import TestCase

from author.models import Author

from .models import Book, BookEmbedding
from .testing import FakeEncoderMixin


class BookCreateTests(FakeEncoderMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.first = Author.create("Ivan", "Franko", "Yakovych")
        cls.second = Author.create("Lesia", "Ukrainka", "Petrivna")

    def assert_saved(self, book, authors):
        self.assertIsNotNone(book.pk)
        stored = Book.objects.get(pk=book.pk)
        self.assertEqual(
            set(stored.authors.values_list("pk", flat=True)),
            {author.pk for author in authors},
        )
        self.assertTrue(BookEmbedding.objects.filter(book=stored).exists())

    def test_without_authors(self):
        self.assert_saved(Book.create("No authors", "Description"), [])

    def test_with_empty_authors(self):
        self.assert_saved(Book.create("Empty authors", "Description", authors=[]), [])

    def test_with_one_author(self):
        book = Book.create("One author", "Description", authors=[self.first])
        self.assert_saved(book, [self.first])

    def test_with_several_authors(self):
        authors = [self.first, self.second]
        book = Book.create("Two authors", "Description", authors=authors)
        self.assert_saved(book, authors)

    def test_failed_author_link_rolls_back_the_book(self):
        unsaved = Author(name="Unsaved", surname="Author", patronymic="")
        with self.assertRaises(ValueError):
            Book.create("Rolled back", "Description", authors=[self.first, unsaved])
        self.assertFalse(Book.objects.filter(name="Rolled back").exists())
        self.assertFalse(
            BookEmbedding.objects.filter(book__name="Rolled back").exists()
        )

    def test_too_long_name_creates_nothing(self):
        name = "x" * (Book.NAME_MAX_LEN + 1)
        self.assertIsNone(Book.create(name, "Description", authors=[self.first]))
        self.assertFalse(Book.objects.filter(name=name).exists())
