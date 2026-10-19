from datetime import timedelta
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from authentication.models import ROLE_LIBRARIAN, CustomUser
from order.models import Order

from .embeddings import DIMENSIONS
from .models import Book


class BookDeletionViewTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        patcher = patch("book.embeddings.load_embedding_model")
        model_loader = patcher.start()
        cls.addClassCleanup(patcher.stop)
        model_loader.return_value.embed.side_effect = lambda texts, **kwargs: [
            [1.0] * DIMENSIONS for _ in texts
        ]

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
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.client.force_login(self.reader)
        response = self.client.post(self.delete_url(self.book))
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
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
                self.assertTrue(
                    any(
                        "borrowing history" in str(message)
                        for message in get_messages(response.wsgi_request)
                    )
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
