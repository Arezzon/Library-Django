"""Search identity, producer failures and worker idempotency."""

import uuid
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import CustomUser
from book.models import Book
from book.testing import FakeEncoderMixin

from .models import EventType, UserEvent
from .services import EventQueueUnavailable
from .tasks import persist_event


class SearchPersistenceTests(FakeEncoderMixin, TestCase):
    def setUp(self):
        self.reader = self.account("one")
        self.other = self.account("two")
        self.book = Book.objects.create(name="Test book", count=1)
        self.client = APIClient()
        self.client.force_login(self.reader)
        self.identity = str(uuid.uuid4())

    def account(self, name):
        return CustomUser.objects.create_user(
            email=f"search-{name}@example.com",
            password="test-password",
            first_name=name,
            last_name="Reader",
            middle_name="",
            is_active=True,
        )

    def test_web_and_api_publish_one_event_each_without_middleware_duplicate(self):
        for url in ("/book/", "/api/v1/books/search/"):
            with (
                self.subTest(url=url),
                patch("events.services.persist_event.apply_async") as publish,
            ):
                response = self.client.get(
                    url,
                    {
                        "q": "poetry",
                        "search_id": self.identity,
                        "password": "never-store",
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(publish.call_count, 1)
                payload = publish.call_args.kwargs["args"][0]
                self.assertEqual(payload["event_type"], EventType.SEARCH)
                self.assertEqual(payload["source"], "server")
                self.assertEqual(
                    payload["properties"], {"query": "poetry", "author_id": None}
                )
                self.assertNotIn("never-store", str(payload))
                self.assertEqual(response["X-Search-Event-ID"], self.identity)
                if url == "/book/":
                    self.assertNotEqual(response.context["search_id"], self.identity)

    def test_retry_and_worker_redelivery_have_one_effect_bound_to_owner(self):
        with patch("events.searches.publish_event", side_effect=persist_event.run):
            for _ in range(2):
                self.client.get(
                    "/api/v1/books/search/", {"q": "poetry", "search_id": self.identity}
                )
            self.assertEqual(
                UserEvent.objects.filter(
                    user=self.reader, event_type=EventType.SEARCH
                ).count(),
                1,
            )
            self.client.get(
                "/api/v1/books/search/", {"q": "poetry", "search_id": str(uuid.uuid4())}
            )
            self.assertEqual(UserEvent.objects.filter(user=self.reader).count(), 2)
            self.client.force_login(self.other)
            self.client.get(
                "/api/v1/books/search/", {"q": "poetry", "search_id": self.identity}
            )
            self.assertEqual(UserEvent.objects.filter(user=self.other).count(), 1)

    def test_queue_outage_is_retryable_and_keeps_identity(self):
        for url in ("/book/", "/api/v1/books/search/"):
            with (
                self.subTest(url=url),
                patch(
                    "events.searches.publish_event", side_effect=EventQueueUnavailable
                ),
            ):
                response = self.client.get(
                    url, {"q": "poetry", "search_id": self.identity}
                )
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response["Retry-After"], "5")
                self.assertEqual(response["X-Search-Event-ID"], self.identity)
                if url == "/book/":
                    self.assertEqual(response.context["search_id"], self.identity)
        self.assertFalse(UserEvent.objects.exists())
        with patch("events.searches.publish_event", side_effect=persist_event.run):
            self.assertEqual(
                self.client.get(
                    "/api/v1/books/search/", {"q": "poetry", "search_id": self.identity}
                ).status_code,
                200,
            )
        self.assertEqual(UserEvent.objects.count(), 1)

    def test_invalid_or_failed_search_is_not_recorded(self):
        from book.embeddings import EmbeddingGenerationError

        with patch("events.searches.publish_event") as publish:
            for url in ("/book/", "/api/v1/books/search/"):
                self.assertEqual(
                    self.client.get(
                        url, {"q": "poetry", "search_id": "bad"}
                    ).status_code,
                    400,
                )
            self.assertEqual(
                self.client.get("/api/v1/books/search/", {"q": ""}).status_code, 400
            )
            with patch(
                "book.api_views.search_books",
                side_effect=EmbeddingGenerationError("unavailable"),
            ):
                self.assertEqual(
                    self.client.get(
                        "/api/v1/books/search/", {"q": "poetry"}
                    ).status_code,
                    503,
                )
            self.client.logout()
            self.assertEqual(
                self.client.get("/api/v1/books/search/", {"q": "poetry"}).status_code,
                401,
            )
            publish.assert_not_called()

    def test_search_text_is_minimized_and_available_only_to_own_profile(self):
        from book.recommendations import _profile

        with patch("events.searches.publish_event", side_effect=persist_event.run):
            self.client.get("/api/v1/books/search/", {"q": "poetry" * 50})
        event = UserEvent.objects.get()
        self.assertEqual(len(event.properties["query"]), 200)
        self.assertEqual(set(event.properties), {"query", "author_id"})
        self.assertIsNotNone(_profile(self.reader, timezone.now())[0])
        self.assertIsNone(_profile(self.other, timezone.now())[0])
