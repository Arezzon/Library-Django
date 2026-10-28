from datetime import timedelta
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.db import transaction
from django.db.models import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from authentication.models import ROLE_LIBRARIAN, CustomUser
from order.models import Order, Reservation

from .embedding_config import resolve
from .models import Book
from .testing import FakeEncoderMixin

REFUSAL = "This book cannot be deleted because it has borrowing or reservation history."


class BookDeletionViewTests(TestCase):
    @classmethod
    def setUpClass(cls):
        patcher = patch("book.embeddings.load_embedding_model")
        model_loader = patcher.start()
        cls.addClassCleanup(patcher.stop)
        model_loader.return_value.embed.side_effect = lambda texts, **kwargs: [
            [1.0] * resolve().dimensions for _ in texts
        ]
        super().setUpClass()

    @classmethod
    def setUpTestData(cls):
        cls.librarian = CustomUser.objects.create_user(
            email="delete-librarian@example.com",
            password="test-password",
            first_name="Test",
            middle_name="",
            last_name="Librarian",
            role=ROLE_LIBRARIAN,
            is_active=True,
        )
        cls.reader = CustomUser.objects.create_user(
            email="delete-reader@example.com",
            password="test-password",
            first_name="Test",
            middle_name="",
            last_name="Reader",
            is_active=True,
        )
        cls.book = Book.objects.create(name="Book without orders", count=1)

    def delete_url(self, book):
        return reverse("book_delete", args=[book.pk])

    def test_edit_page_has_separate_confirmed_delete_form(self):
        self.client.force_login(self.librarian)
        response = self.client.get(reverse("book_update", args=[self.book.pk]))
        self.assertContains(response, f'action="{self.delete_url(self.book)}"')
        self.assertContains(response, "Delete Book")
        self.assertContains(response, "return confirm(")

    def test_librarian_can_delete_book_without_orders(self):
        self.client.force_login(self.librarian)
        response = self.client.post(self.delete_url(self.book))
        self.assertRedirects(
            response, reverse("book_list"), fetch_redirect_response=False
        )
        self.assertFalse(Book.objects.filter(pk=self.book.pk).exists())
        self.assertTrue(
            any(
                "deleted successfully" in str(message)
                for message in get_messages(response.wsgi_request)
            )
        )

    def test_get_does_not_delete_book(self):
        self.client.force_login(self.librarian)
        response = self.client.get(self.delete_url(self.book))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Book.objects.filter(pk=self.book.pk).exists())

    def test_only_librarian_can_delete_book(self):
        response = self.client.post(self.delete_url(self.book))
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={self.delete_url(self.book)}",
            fetch_redirect_response=False,
        )
        self.client.force_login(self.reader)
        response = self.client.post(self.delete_url(self.book))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Book.objects.filter(pk=self.book.pk).exists())

    def test_books_with_active_or_returned_orders_keep_their_history(self):
        self.client.force_login(self.librarian)
        for end_at in (None, timezone.now()):
            with self.subTest(end_at=end_at):
                book = Book.objects.create(name="Borrowed book", count=1)
                order = Order.objects.create(
                    book=book,
                    user=self.reader,
                    plated_end_at=timezone.now() + timedelta(days=14),
                    end_at=end_at,
                )
                response = self.client.post(self.delete_url(book))
                self.assertRedirects(
                    response,
                    reverse("book_update", args=[book.pk]),
                    fetch_redirect_response=False,
                )
                self.assertTrue(Book.objects.filter(pk=book.pk).exists())
                self.assertTrue(Order.objects.filter(pk=order.pk).exists())
                self.assertIn(
                    REFUSAL,
                    [str(message) for message in get_messages(response.wsgi_request)],
                )

    def test_delete_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.librarian)
        response = client.post(self.delete_url(self.book))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Book.objects.filter(pk=self.book.pk).exists())

        client.get(reverse("book_update", args=[self.book.pk]))
        response = client.post(
            self.delete_url(self.book),
            {"csrfmiddlewaretoken": client.cookies["csrftoken"].value},
        )
        self.assertRedirects(
            response, reverse("book_list"), fetch_redirect_response=False
        )
        self.assertFalse(Book.objects.filter(pk=self.book.pk).exists())


class ProtectedHistoryTests(FakeEncoderMixin, TestCase):
    """A book with a loan or a reservation cannot be deleted in any channel (FR-024)."""

    @classmethod
    def setUpTestData(cls):
        cls.librarian = CustomUser.objects.create_user(
            email="history-librarian@example.com",
            password="test-password",
            first_name="Test",
            middle_name="",
            last_name="Librarian",
            role=ROLE_LIBRARIAN,
            is_active=True,
        )
        cls.reader = CustomUser.objects.create_user(
            email="history-reader@example.com",
            password="test-password",
            first_name="Test",
            middle_name="",
            last_name="Reader",
            is_active=True,
        )

    def histories(self):
        """A book with a loan, and a book with a reservation, each with its record."""
        loaned = Book.objects.create(name="Loaned book", count=1)
        loan = Order.objects.create(
            book=loaned,
            user=self.reader,
            plated_end_at=timezone.now() + timedelta(days=14),
        )
        reserved = Book.objects.create(name="Reserved book", count=1)
        reservation = Reservation.objects.create(book=reserved, user=self.reader)
        return [(loaned, loan), (reserved, reservation)]

    def assertKept(self, book, record):
        self.assertTrue(Book.objects.filter(pk=book.pk).exists())
        self.assertTrue(type(record).objects.filter(pk=record.pk, book=book).exists())

    def test_the_orm_refuses(self):
        for book, record in self.histories():
            with self.subTest(record=record):
                with self.assertRaises(ProtectedError), transaction.atomic():
                    book.delete()
                self.assertKept(book, record)

    def test_the_edit_page_shows_the_history_message(self):
        self.client.force_login(self.librarian)
        for book, record in self.histories():
            with self.subTest(record=record):
                response = self.client.post(
                    reverse("book_delete", args=[book.pk]), follow=True
                )
                self.assertEqual(
                    response.redirect_chain,
                    [(reverse("book_update", args=[book.pk]), 302)],
                )
                self.assertContains(response, REFUSAL)
                self.assertKept(book, record)

    def test_the_api_answers_409(self):
        self.client.force_login(self.librarian)
        for book, record in self.histories():
            with self.subTest(record=record):
                response = self.client.delete(f"/api/v1/book/{book.pk}/")
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json(), {"detail": REFUSAL})
                self.assertKept(book, record)

    def test_the_schema_documents_the_409(self):
        schema = self.client.get("/api/schema/?format=json").json()
        refusal = schema["paths"]["/api/v1/book/{id}/"]["delete"]["responses"]["409"]
        self.assertEqual(
            refusal["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/Refusal"},
        )

    def test_the_admin_site_shows_its_protected_objects_page(self):
        self.client.force_login(self.librarian)
        for book, record in self.histories():
            url = f"/admin/book/book/{book.pk}/delete/"
            bulk = {
                "action": "delete_selected",
                "_selected_action": [book.pk],
                "post": "yes",
            }
            attempts = [
                ("confirmation page", self.client.get, url, {}),
                ("confirmed deletion", self.client.post, url, {"post": "yes"}),
                ("bulk action", self.client.post, "/admin/book/book/", bulk),
            ]
            for attempt, send, path, data in attempts:
                with self.subTest(record=record, attempt=attempt):
                    response = send(path, data)
                    self.assertContains(response, "Cannot delete book")
                    self.assertContains(response, "protected related objects")
                    self.assertContains(response, str(record))
                    self.assertKept(book, record)
