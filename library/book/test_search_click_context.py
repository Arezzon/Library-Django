"""Result links refer to this completed search, never the next form submission."""

import uuid
from html.parser import HTMLParser
from unittest.mock import patch

from django.test import TestCase

from author.models import Author
from book.models import Book
from book.testing import FakeEncoderMixin
from events.services import EventQueueUnavailable
from events.tests import account


class ClickLinks(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.links = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("data-track-event") == "book_click":
            self.links.append(attrs)


class SearchClickContextTests(FakeEncoderMixin, TestCase):
    def setUp(self):
        self.reader = account("click-context@example.com")
        self.client.force_login(self.reader)
        self.book = Book.objects.create(name="Result", count=2)
        self.author = Author.objects.create(name="Taras", surname="Shevchenko")
        self.book.authors.add(self.author)
        self.identity = str(uuid.uuid4())

    def links(self, response):
        return ClickLinks(response.content.decode()).links

    def test_all_desktop_and_mobile_actions_use_the_current_not_next_search(self):
        for filters in ({"q": "poetry"}, {"author_id": self.author.pk}):
            with self.subTest(filters=filters), patch("events.searches.publish_event"):
                page = self.client.get(
                    "/book/", {**filters, "search_id": self.identity}
                )
            self.assertEqual(page.status_code, 200)
            self.assertEqual(page.context["current_search_id"], self.identity)
            self.assertNotEqual(page.context["search_id"], self.identity)
            links = self.links(page)
            self.assertEqual(len(links), 4)
            self.assertEqual(
                {link["data-search-id"] for link in links}, {self.identity}
            )

    def test_catalog_without_search_keeps_clicks_unattributed(self):
        with patch("events.searches.publish_event") as publish:
            page = self.client.get("/book/")
        self.assertIsNone(page.context["current_search_id"])
        self.assertTrue(self.links(page))
        self.assertTrue(all("data-search-id" not in link for link in self.links(page)))
        publish.assert_not_called()

    def test_failed_publication_has_no_search_link_and_retains_retry_id(self):
        with patch("events.searches.publish_event", side_effect=EventQueueUnavailable):
            page = self.client.get(
                "/book/", {"q": "poetry", "search_id": self.identity}
            )
        self.assertEqual(page.status_code, 503)
        self.assertEqual(page.context["search_id"], self.identity)
        self.assertIsNone(page.context["current_search_id"])
        self.assertTrue(all("data-search-id" not in link for link in self.links(page)))
