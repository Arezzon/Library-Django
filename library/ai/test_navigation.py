"""Real CSRF enforcement and GET-only result navigation, with no private form storage."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.db import OperationalError
from django.test import Client, RequestFactory, TestCase
from django.utils import timezone

from authentication.models import CustomUser
from author.models import Author
from book.models import Book
from book.testing import FakeEncoderMixin

from .context import MAX_BOOKS, RESULT_KEY
from .services import catalog_page_result
from .views import assistant_result


class AssistantNavigationTests(FakeEncoderMixin, TestCase):
    def setUp(self):
        self.reader = CustomUser.objects.create_user(
            email="assistant-navigation@example.com",
            password="test-password",
            first_name="Reader",
            last_name="Test",
            middle_name="",
            is_active=True,
        )
        self.book = Book.objects.create(name="Kobzar", count=1)
        author = Author.objects.create(name="Taras", surname="Shevchenko")
        self.book.authors.add(author)
        self.browser = Client(enforce_csrf_checks=True)
        self.browser.force_login(self.reader)
        self.browser.get("/assistant/")

    def submit(self, question):
        return self.browser.post(
            "/assistant/",
            {
                "q": question,
                "csrfmiddlewaretoken": self.browser.cookies["csrftoken"].value,
            },
        )

    def test_success_redirects_to_get_and_back_refresh_does_not_replay_post(self):
        response = self.submit("знайди твори Шевченка")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response["Location"], "/assistant/result/#assistant-result")
        with patch(
            "ai.views.catalog_assistant", side_effect=AssertionError("do not replay")
        ):
            page = self.browser.get("/assistant/result/")
            self.assertContains(page, self.book.name)
            self.browser.get(f"/book/{self.book.pk}/")
            self.assertContains(self.browser.get("/assistant/result/"), self.book.name)
        self.book.count = 0
        self.book.save(update_fields=["count"])
        page = self.browser.get("/assistant/result/")
        self.assertEqual(page.context["result"]["books"][0]["available_count"], 0)
        self.assertIn("no-store", page["Cache-Control"])
        self.assertEqual(self.submit("Is Kobzar available?").status_code, 303)
        self.assertEqual(
            self.browser.post("/assistant/", {"q": "Kobzar"}).status_code, 403
        )

    def test_result_state_is_minimized_bound_and_expires(self):
        self.submit("Find books by Shevchenko")
        state = self.browser.session[RESULT_KEY]
        self.assertEqual(
            set(state),
            {
                "owner",
                "time",
                "books",
                "authors",
                "status",
                "intent",
                "truncated",
                "available_only",
            },
        )
        self.assertNotIn("Shevchenko", str(state))
        with patch(
            "ai.context.timezone.now",
            return_value=timezone.now() + timedelta(minutes=11),
        ):
            self.assertRedirects(self.browser.get("/assistant/result/"), "/assistant/")
        self.assertNotIn(RESULT_KEY, self.browser.session)
        self.submit("Kobzar")
        session = self.browser.session
        session[RESULT_KEY] = {**session[RESULT_KEY], "owner": self.reader.pk + 1}
        session.save()
        self.assertRedirects(self.browser.get("/assistant/result/"), "/assistant/")
        self.assertEqual(self.browser.post("/assistant/result/").status_code, 403)

    def test_empty_missing_and_author_only_results_survive_redirect(self):
        for question, expected in (
            ("", "clarification_required"),
            ("Find unknown-title-98765", "not_found"),
        ):
            self.assertEqual(self.submit(question).status_code, 303)
            page = self.browser.get("/assistant/result/")
            self.assertEqual(page.context["result"]["status"], expected)
        self.book.authors.clear()
        self.submit("Find books by Shevchenko")
        page = self.browser.get("/assistant/result/")
        self.assertEqual(len(page.context["result"]["authors"]), 1)
        self.assertEqual(page.context["result"]["books"], [])

    def test_deleted_books_and_model_free_topic_refresh(self):
        self.submit("Kobzar")
        session = self.browser.session
        session[RESULT_KEY] = {**session[RESULT_KEY], "intent": "topic"}
        session.save()
        with patch(
            "book.embeddings.load_embedding_model",
            side_effect=AssertionError("no inference on GET"),
        ):
            self.assertContains(self.browser.get("/assistant/result/"), self.book.name)
        self.book.delete()
        self.assertEqual(
            self.browser.get("/assistant/result/").context["result"]["status"],
            "not_found",
        )

    def test_malformed_saved_ids_and_metadata_return_to_a_clean_form(self):
        self.submit("Kobzar")
        original = self.browser.session[RESULT_KEY]
        invalid_fields = {
            "books": [
                None,
                "1",
                [0],
                [-1],
                [True],
                ["1"],
                [self.book.pk] * (MAX_BOOKS + 1),
            ],
            "authors": [None, [False], ["1"], [0], [1] * (MAX_BOOKS + 1)],
            "status": [None, "source_unavailable", "unexpected"],
            "intent": [None, "reserve", "unexpected"],
            "truncated": [None, 0, "false"],
            "available_only": [None, 1, "true"],
        }
        for field, values in invalid_fields.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    session = self.browser.session
                    session[RESULT_KEY] = {**original, field: value}
                    session.save()
                    with patch(
                        "ai.views.catalog_page_result",
                        side_effect=AssertionError(
                            "invalid state must not reach the catalog"
                        ),
                    ):
                        self.assertRedirects(
                            self.browser.get("/assistant/result/"), "/assistant/"
                        )
                    self.assertNotIn(RESULT_KEY, self.browser.session)

    def test_result_service_denies_anonymous_inactive_and_unsaved_accounts(self):
        unsaved = CustomUser(email="unsaved@example.com", is_active=True)
        self.reader.is_active = False
        for account in (AnonymousUser(), self.reader, unsaved):
            with self.subTest(account=type(account).__name__), self.assertNumQueries(0):
                with self.assertRaises(PermissionDenied):
                    catalog_page_result(account, {})

    def test_result_view_rejects_inactive_account_before_catalog_or_session_access(
        self,
    ):
        request = RequestFactory().get("/assistant/result/")
        self.reader.is_active = False
        request.user = self.reader
        with self.assertNumQueries(0), self.assertRaises(PermissionDenied):
            assistant_result(request)
        self.browser.logout()
        self.assertEqual(self.browser.get("/assistant/result/").status_code, 302)

    def test_query_selectors_are_redirected_before_result_hydration(self):
        self.submit("Kobzar")
        with patch(
            "ai.views.catalog_page_result",
            side_effect=AssertionError("selectors must not reach the catalog"),
        ):
            response = self.browser.get(
                "/assistant/result/?user_id=999&q=private-marker"
            )
        self.assertRedirects(response, "/assistant/")
        self.assertNotIn(RESULT_KEY, self.browser.session)

    def test_catalog_failure_on_result_get_is_safe_and_retryable(self):
        self.submit("Kobzar")
        with patch(
            "ai.services.lookup_catalog",
            side_effect=OperationalError("private-host password=do-not-disclose"),
        ):
            response = self.browser.get("/assistant/result/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Retry-After"], "5")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response.context["result"]["status"], "source_unavailable")
        self.assertEqual(response.context["result"]["books"], [])
        self.assertEqual(response.context["result"]["authors"], [])
        self.assertIsNone(response.context["result"]["checked_at"])
        self.assertContains(response, 'role="alert"', status_code=503)
        self.assertNotContains(response, "private-host", status_code=503)
        self.assertNotContains(response, "do-not-disclose", status_code=503)
        self.assertContains(self.browser.get("/assistant/result/"), self.book.name)
