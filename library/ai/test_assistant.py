"""Grounded catalog facts, read-only isolation and current availability."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.db import OperationalError, connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import CustomUser
from author.models import Author
from book.catalog_data import RESULT_LIMIT, lookup_catalog
from book.models import Book, BookEmbedding
from book.testing import FakeEncoderMixin
from order.models import Order, Reservation

from .services import AVAILABILITY_NOTICE, catalog_assistant


class CatalogAssistantTests(FakeEncoderMixin, TestCase):
    def setUp(self):
        self.reader = self.account("reader")
        self.other = self.account("private-borrower")
        self.book = Book.objects.create(name="Kobzar", count=2)
        self.author = Author.objects.create(name="Taras", surname="Shevchenko")
        self.author.books.add(self.book)
        self.client = APIClient()
        self.client.force_login(self.reader)
        self.url = "/api/v1/assistant/"

    def account(self, name):
        return CustomUser.objects.create_user(
            email=f"assistant-{name}@example.com",
            password="test-password",
            first_name=name,
            last_name="Reader",
            middle_name="",
            is_active=True,
        )

    def ask(self, query="", intent="auto"):
        return catalog_assistant(self.reader, query, intent)

    def test_title_and_availability_answers_cite_real_records(self):
        for query, intent in (
            ("книга: kobzar", "auto"),
            ("TITLE: Kobzar", "auto"),
            ("Kobzar", "title"),
            ("наявність: Kobzar", "auto"),
            ("Kobzar", "availability"),
        ):
            with self.subTest(query=query, intent=intent):
                data = self.ask(query, intent)
                self.assertEqual(data["status"], "found")
                book = data["books"][0]
                self.assertEqual(book["id"], self.book.pk)
                self.assertEqual(book["title"], self.book.name)
                self.assertEqual(book["available_count"], 2)
                self.assertEqual(book["total_count"], 2)
                self.assertEqual(resolve(book["url"]).kwargs["book_id"], self.book.pk)
                author = book["authors"][0]
                self.assertEqual(author["id"], self.author.pk)
                self.assertIn(author["name"], data["answer"])
                self.assertIn(book["url"], data["answer"])
                self.assertIn(AVAILABILITY_NOTICE, data["answer"])
                self.assertIsNotNone(data["checked_at"])

    def test_ukrainian_titles_and_missing_author_stay_grounded(self):
        book = Book.objects.create(name="Лісова пісня", count=0)
        data = self.ask("ЛІСОВА", "availability")
        self.assertEqual(data["status"], "found")
        self.assertEqual(data["books"][0]["id"], book.pk)
        self.assertEqual(data["books"][0]["authors"], [])
        self.assertEqual(data["books"][0]["available_count"], 0)
        self.assertIn("Автор у каталозі не вказаний", data["answer"])

    def test_author_full_name_uses_tokens_in_any_order_and_returns_links(self):
        for query in ("автор: Taras Shevchenko", "author: shevchenko taras"):
            data = self.ask(query)
            self.assertEqual(data["status"], "found")
            self.assertEqual([a["id"] for a in data["authors"]], [self.author.pk])
            self.assertEqual([b["id"] for b in data["books"]], [self.book.pk])
            self.assertEqual(
                int(resolve(data["authors"][0]["url"]).kwargs["pk"]), self.author.pk
            )
            self.assertIn(
                f"author_id={self.author.pk}", data["authors"][0]["books_url"]
            )
            self.assertIn(data["authors"][0]["url"], data["answer"])

    def test_author_without_books_is_confirmed_without_inventing_books(self):
        self.author.books.clear()
        data = self.ask("Shevchenko", "author")
        self.assertEqual(data["status"], "found")
        self.assertEqual(data["books"], [])
        self.assertEqual(len(data["authors"]), 1)
        self.assertIn("Пов’язаних книг", data["answer"])

    def test_missing_title_and_author_have_no_fabricated_records(self):
        for intent in ("title", "author", "availability"):
            data = self.ask("Unknown imaginary book", intent)
            self.assertEqual(data["status"], "not_found")
            self.assertEqual(data["books"], [])
            self.assertEqual(data["authors"], [])
            self.assertIn("немає підтверджених збігів", data["answer"])

    def test_empty_short_or_unsupported_intent_requests_clarification_without_queries(
        self,
    ):
        for query in ("", "   ", "x", "автор:", "бронювання: Kobzar"):
            with self.subTest(query=query), self.assertNumQueries(0):
                data = self.ask(query)
                self.assertEqual(data["status"], "clarification_required")
                self.assertEqual(data["books"], [])
                self.assertIsNone(data["checked_at"])

    def test_multiple_matches_are_stable_bounded_and_prompt_refinement(self):
        for index in range(RESULT_LIMIT + 2):
            Book.objects.create(name=f"Kobzar {index:02d}", count=1)
        data = self.ask("Kobzar")
        self.assertEqual(data["status"], "clarification_required")
        self.assertTrue(data["truncated"])
        self.assertEqual(len(data["books"]), RESULT_LIMIT)
        self.assertEqual(data, {**self.ask("Kobzar"), "checked_at": data["checked_at"]})
        self.assertIn("Уточніть", data["answer"])

    def test_same_name_authors_are_not_conflated(self):
        other = Author.objects.create(name="Another", surname="Shevchenko")
        other.books.add(self.book)
        data = self.ask("Shevchenko", "author")
        self.assertEqual(data["status"], "clarification_required")
        self.assertEqual(len(data["authors"]), 2)
        self.assertEqual(len(data["books"]), 1)
        self.assertEqual(len(data["books"][0]["authors"]), 2)
        self.assertEqual(data["books"][0]["available_count"], 2)

    def test_availability_changes_with_loans_returns_holds_and_expiry(self):
        due = timezone.now() + timedelta(days=7)
        loan = Order.objects.create(user=self.other, book=self.book, plated_end_at=due)
        self.assertEqual(self.ask("Kobzar")["books"][0]["available_count"], 1)
        hold = Reservation.objects.create(user=self.reader, book=self.book)
        data = self.ask("Kobzar")
        self.assertEqual(data["books"][0]["available_count"], 0)
        self.assertNotIn(self.other.email, str(data))
        self.assertNotIn(self.other.first_name, str(data))
        loan.end_at = timezone.now()
        loan.save(update_fields=["end_at"])
        self.assertEqual(self.ask("Kobzar")["books"][0]["available_count"], 1)
        with patch("ai.services.timezone.now", return_value=hold.expires_at):
            self.assertEqual(self.ask("Kobzar")["books"][0]["available_count"], 2)
        self.book.count = 0
        self.book.save(update_fields=["count"])
        self.assertEqual(self.ask("Kobzar")["books"][0]["available_count"], 0)

    def test_failed_source_clears_facts_and_never_exposes_exception_text(self):
        with patch(
            "ai.services.lookup_catalog",
            side_effect=OperationalError("private-host password=secret"),
        ):
            response = self.client.get(self.url, {"q": "Kobzar"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Retry-After"], "5")
        data = response.json()
        self.assertEqual(data["status"], "source_unavailable")
        self.assertEqual(data["books"], [])
        self.assertEqual(data["authors"], [])
        self.assertIsNone(data["checked_at"])
        self.assertNotIn("private-host", str(data))
        self.assertNotIn("secret", str(data))
        self.assertIn("Не можу підтвердити", data["answer"])

    def test_lazy_prefetch_failure_does_not_publish_partial_facts(self):
        with patch(
            "book.catalog_data._book_record",
            side_effect=OperationalError("source failed"),
        ):
            data = self.ask("Kobzar")
        self.assertEqual(data["status"], "source_unavailable")
        self.assertEqual(data["books"], [])

    def test_no_inference_embeddings_or_business_writes_are_needed(self):
        BookEmbedding.objects.all().delete()
        with (
            patch(
                "book.embeddings.load_embedding_model",
                side_effect=AssertionError("inference forbidden"),
            ),
            CaptureQueriesContext(connection) as queries,
        ):
            self.assertEqual(self.ask("Kobzar")["status"], "found")
        self.assertTrue(all(q["sql"].lstrip().startswith("SELECT") for q in queries))
        self.assertEqual(len(queries), 2)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Reservation.objects.exists())

    def test_queries_do_not_grow_per_book_and_special_characters_are_literal(self):
        for index in range(5):
            book = Book.objects.create(name=f"Kobzar-{index}", count=1)
            self.author.books.add(book)
        with self.assertNumQueries(2):
            self.ask("Kobzar")
        with self.assertNumQueries(3):
            self.ask("Taras Shevchenko", "author")
        for query in ("%_", "'; DROP TABLE book_book; --", "<script>"):
            self.assertEqual(self.ask(query)["status"], "not_found")
        self.assertTrue(Book.objects.filter(pk=self.book.pk).exists())

    def test_api_validates_parameters_and_only_accepts_read_operations(self):
        for params in (
            {"q": "x" * 257},
            {"intent": "reserve"},
            {"user_id": self.other.pk},
            {"q": ["Kobzar", "another"]},
        ):
            self.assertEqual(self.client.get(self.url, params).status_code, 400)
        for method in (self.client.post, self.client.patch, self.client.delete):
            self.assertEqual(method(self.url, {"q": "Kobzar"}).status_code, 405)
        response = self.client.get(self.url, {"q": "Kobzar"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(
            self.client.get(self.url).json()["status"], "clarification_required"
        )

    def test_authentication_is_checked_in_api_and_service(self):
        with self.assertRaises(PermissionDenied), self.assertNumQueries(0):
            lookup_catalog(AnonymousUser(), "Kobzar")
        self.client.logout()
        self.assertEqual(self.client.get(self.url, {"q": "Kobzar"}).status_code, 401)
        for user in (AnonymousUser(), self.reader):
            if user == self.reader:
                user.is_active = False
            with self.assertRaises(PermissionDenied):
                catalog_assistant(user, "Kobzar")
        self.client.force_authenticate(self.reader)
        self.assertEqual(self.client.get(self.url, {"q": "Kobzar"}).status_code, 403)

    def test_service_validation_does_not_hit_catalog(self):
        for query, intent in (
            (None, "auto"),
            ("x" * 257, "auto"),
            ("Kobzar", "reserve"),
        ):
            with self.assertRaises(ValueError), self.assertNumQueries(0):
                self.ask(query, intent)
