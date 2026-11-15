"""Search-to-click attribution without trusting another reader's event UUID."""

import uuid
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from book.models import Book
from book.testing import FakeEncoderMixin

from .models import EventType, UserEvent
from .tasks import persist_event
from .tests import account


class SearchClickTests(FakeEncoderMixin, TestCase):
    def setUp(self):
        self.reader = account("search-click@example.com")
        self.other = account("other-search-click@example.com")
        self.book = Book.objects.create(name="Clickable book", count=2)
        self.client = APIClient()
        self.client.force_login(self.reader)
        self.identity = str(uuid.uuid4())
        self.data = {
            "event_id": str(uuid.uuid4()),
            "event_type": "book_click",
            "book_id": self.book.pk,
            "path": "/book/",
        }

    def search(self):
        response = self.client.get(
            "/book/", {"q": "poetry", "search_id": self.identity}
        )
        self.assertEqual(response.status_code, 200)
        return response

    def click(self, **extra):
        return self.client.post(
            "/api/v1/events/", {**self.data, **extra}, format="json"
        )

    def test_click_resolves_the_search_and_retry_is_idempotent(self):
        with (
            patch("events.searches.publish_event", side_effect=persist_event.run),
            patch("events.api_views.publish_event", side_effect=persist_event.run),
        ):
            self.search()
            response = self.click(search_id=self.identity)
            self.assertEqual(response.status_code, 202)
            self.assertEqual(self.click(search_id=self.identity).status_code, 202)
        click = UserEvent.objects.get(event_type=EventType.BOOK_CLICK)
        search = UserEvent.objects.get(pk=click.properties["search_id"])
        self.assertEqual(search.event_type, EventType.SEARCH)
        self.assertEqual(search.user, click.user)
        self.assertEqual(search.properties["query"], "poetry")
        self.assertEqual(click.book_id, self.book.pk)
        self.assertEqual(set(click.properties), {"search_id"})
        self.assertEqual(str(click.pk), response.json()["event_id"])

    def test_click_may_be_persisted_before_the_search_worker(self):
        with patch("events.searches.publish_event") as publish:
            self.search()
        payload = publish.call_args.args[0]
        with patch("events.api_views.publish_event", side_effect=persist_event.run):
            self.assertEqual(self.click(search_id=self.identity).status_code, 202)
        click = UserEvent.objects.get(event_type=EventType.BOOK_CLICK)
        self.assertFalse(
            UserEvent.objects.filter(pk=click.properties["search_id"]).exists()
        )
        persist_event.run(payload)
        self.assertEqual(
            str(UserEvent.objects.get(event_type=EventType.SEARCH).pk),
            click.properties["search_id"],
        )

    def test_click_without_search_and_borrow_intent_keep_empty_properties(self):
        with patch("events.api_views.publish_event", side_effect=persist_event.run):
            for event_type in ("book_click", "borrow_intent"):
                response = self.click(event_id=str(uuid.uuid4()), event_type=event_type)
                self.assertEqual(response.status_code, 202)
                self.assertEqual(
                    UserEvent.objects.get(pk=response.json()["event_id"]).properties, {}
                )

    def test_bad_uuid_null_unknown_fields_and_wrong_event_are_rejected(self):
        with patch("events.api_views.publish_event") as publish:
            for search_id in ("invalid", "", None, [], {}, True, 1):
                with self.subTest(search_id=search_id):
                    self.assertEqual(self.click(search_id=search_id).status_code, 400)
            for extra in (
                {"search_id": self.identity, "event_type": "borrow_intent"},
                {"search_id": self.identity, "user_id": self.other.pk},
                {"search_id": self.identity, "properties": {"query": "private"}},
                {"search_id": self.identity, "query": "private"},
            ):
                with self.subTest(extra=extra):
                    self.assertEqual(self.click(**extra).status_code, 400)
            publish.assert_not_called()

    def test_shared_action_uuid_is_scoped_to_the_authenticated_reader(self):
        searches = []
        with (
            patch("events.searches.publish_event", side_effect=persist_event.run),
            patch("events.api_views.publish_event", side_effect=persist_event.run),
        ):
            for reader in (self.reader, self.other):
                self.client.force_login(reader)
                self.search()
                response = self.click(search_id=self.identity)
                self.assertEqual(response.status_code, 202)
                click = UserEvent.objects.get(pk=response.json()["event_id"])
                search = UserEvent.objects.get(pk=click.properties["search_id"])
                self.assertEqual(search.user, reader)
                searches.append(search.pk)
        self.assertNotEqual(*searches)

    def test_sending_another_readers_stored_id_cannot_reference_their_event(self):
        with patch("events.searches.publish_event", side_effect=persist_event.run):
            self.search()
        foreign = UserEvent.objects.get(event_type=EventType.SEARCH)
        self.client.force_login(self.other)
        with patch("events.api_views.publish_event", side_effect=persist_event.run):
            response = self.click(search_id=str(foreign.pk))
        self.assertEqual(response.status_code, 202)
        click = UserEvent.objects.get(pk=response.json()["event_id"])
        self.assertNotEqual(click.properties["search_id"], str(foreign.pk))
        self.assertFalse(
            UserEvent.objects.filter(
                pk=click.properties["search_id"], user=self.reader
            ).exists()
        )
