"""The analytics dashboard loads in a fixed number of queries (research R8, FR-047)."""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from authentication.models import ROLE_LIBRARIAN, CustomUser
from book.models import Book
from book.testing import FakeEncoderMixin
from library.testing import assert_same_query_count

from .models import EventType, UserEvent


class DashboardQueryTests(FakeEncoderMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.librarian = CustomUser.objects.create_user(
            email="queries-librarian@example.com",
            password="queries-password",
            first_name="Query",
            middle_name="",
            last_name="Librarian",
            role=ROLE_LIBRARIAN,
            is_active=True,
        )
        cls.book = Book.objects.create(name="Viewed book")

    def setUp(self):
        self.client.force_login(self.librarian)

    def add_events(self, count):
        for _ in range(count):
            UserEvent.objects.create(
                user=self.librarian,
                event_type=EventType.BOOK_VIEW,
                source="server",
                book_id=self.book.pk,
                occurred_at=timezone.now(),
            )

    def test_the_dashboard(self):
        response = assert_same_query_count(
            self, self.client, reverse("events_dashboard"), self.add_events
        )
        self.assertEqual(response.context["page_obj"].paginator.count, 50)
