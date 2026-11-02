"""Ukrainian control set, private POST flow, access, CSRF and read-only results."""

import io
import json
import logging
from pathlib import Path
from unittest.mock import patch

from django.db import OperationalError
from django.test import Client, TestCase

from authentication.models import CustomUser
from author.models import Author
from book.models import Book
from book.testing import FakeEncoderMixin
from order.models import Order, Reservation


class AssistantInterfaceTests(FakeEncoderMixin, TestCase):
    def setUp(self):
        self.reader = CustomUser.objects.create_user(
            email="assistant-ui@example.com",
            password="test-password",
            first_name="Reader",
            middle_name="",
            last_name="Test",
            is_active=True,
        )
        self.book = Book.objects.create(name="Кобзар", count=1)
        author = Author.objects.create(name="Тарас", surname="Шевченко")
        author.books.add(self.book)
        Book.objects.create(name="Лісова пісня", count=1)
        Book.objects.create(name="Лісова казка", count=1)
        self.client.force_login(self.reader)

    def ask(self, q, **kwargs):
        return self.client.post("/assistant/", {"q": q, "intent": "auto"}, **kwargs)

    def test_ukrainian_control_questions(self):
        cases = json.loads(
            (Path(__file__).parent / "control/questions_uk.json").read_text(
                encoding="utf-8"
            )
        )
        for case in cases:
            with self.subTest(question=case["question"]):
                response = self.ask(case["question"])
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["result"]["status"], case["status"])
                if "title" in case:
                    self.assertContains(response, case["title"])
                if case["status"] == "not_found":
                    self.assertEqual(response.context["result"]["books"], [])
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Reservation.objects.exists())

    def test_sources_and_accessibility_semantics(self):
        response = self.ask("книга: Кобзар")
        self.assertContains(response, f'href="/book/{self.book.pk}/"')
        for fragment in (
            'method="post"',
            'for="id_q"',
            'for="id_intent"',
            'aria-describedby="question-help question-errors"',
            'role="status"',
            'tabindex="-1"',
            'href="#id_q"',
        ):
            self.assertContains(response, fragment)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["Referrer-Policy"], "same-origin")

    def test_the_page_does_not_show_when_the_answer_was_checked(self):
        """The page once showed that time as a bare UTC timestamp (TD-30, FR-044).
        Only the API gives it now, with its offset, for programs."""
        response = self.ask("книга: Кобзар")
        checked_at = response.context["result"]["checked_at"]
        self.assertIsNotNone(checked_at)
        self.assertNotContains(response, checked_at)

    def test_form_validation_and_selectors(self):
        for data in (
            {"q": "x" * 257, "intent": "auto"},
            {"q": "Кобзар", "intent": "reserve"},
            {"q": "Кобзар", "intent": "auto", "user_id": 2},
            {"q": ["Кобзар", "інше"], "intent": "auto"},
        ):
            response = self.client.post("/assistant/", data)
            self.assertEqual(response.status_code, 400)
            self.assertContains(response, 'role="alert"', status_code=400)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Reservation.objects.exists())
        self.assertRedirects(self.client.get("/assistant/?q=private"), "/assistant/")

    def test_source_failure_is_clear_safe_and_retryable(self):
        with (
            patch(
                "ai.services.lookup_catalog",
                side_effect=OperationalError("private database details"),
            ),
            patch(
                "order.middleware.unseen_cancellations",
                side_effect=OperationalError("notices unavailable"),
            ),
        ):
            response = self.ask("книга: Кобзар")
        self.assertContains(
            response, "The catalog is temporarily unavailable", status_code=503
        )
        self.assertContains(response, 'role="alert"', status_code=503)
        self.assertContains(response, "try again", status_code=503)
        self.assertNotContains(response, "private database details", status_code=503)
        self.assertEqual(response["Retry-After"], "5")
        self.assertEqual(response.context["result"]["books"], [])

    def test_questions_are_not_logged_for_success_invalid_or_source_failure(self):
        handler = logging.getLogger("ai").handlers[0]
        stream = io.StringIO()
        marker = "private-question-784603"
        with patch.object(handler, "stream", stream):
            self.ask(marker)
            self.ask(marker * 30)
            with patch(
                "ai.services.lookup_catalog", side_effect=OperationalError(marker)
            ):
                self.ask(marker)
        output = stream.getvalue()
        self.assertNotIn(marker, output)
        self.assertNotIn(self.reader.email, output)
        for status in ("not_found", "invalid_request", "source_unavailable"):
            self.assertIn("status=" + status, output)

    def test_permissions_and_csrf(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.reader)
        self.assertEqual(
            browser.post("/assistant/", {"q": "Кобзар", "intent": "title"}).status_code,
            403,
        )
        self.client.logout()
        self.assertEqual(self.client.get("/assistant/").status_code, 302)
        self.assertEqual(self.ask("Кобзар").status_code, 302)
        self.reader.is_active = False
        self.reader.save(update_fields=["is_active"])
        self.client.force_login(self.reader)
        self.assertNotEqual(self.client.get("/assistant/").status_code, 200)

    def test_html_is_escaped_and_initial_page_has_no_previous_question(self):
        book = Book.objects.create(name='<script>alert("x")</script>', count=1)
        response = self.client.post("/assistant/", {"q": book.name, "intent": "title"})
        self.assertNotContains(response, book.name)
        self.assertContains(response, "&lt;script&gt;")
        response = self.client.get("/assistant/")
        self.assertIsNone(response.context["result"])
        self.assertNotContains(response, "alert(&quot;x&quot;)")
