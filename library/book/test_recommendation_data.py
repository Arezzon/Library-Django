"""KAN-50: input minimization, ownership, missing data and current stock."""

from dataclasses import asdict
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import ROLE_LIBRARIAN, CustomUser
from events.models import EventType, UserEvent
from order.models import Order, Reservation
from order.services import cancel

from .models import Book, BookEmbedding
from .recommendation_data import (
    BookSignal,
    RecommendationHistory,
    available_candidates,
    fallback_candidates,
    read_history,
)
from .recommendations import recommend_books
from .testing import FakeEncoderMixin


class RecommendationDataTests(FakeEncoderMixin, TestCase):
    def setUp(self):
        self.reader = self.account("reader")
        self.other = self.account("other")
        self.staff = self.account("staff", ROLE_LIBRARIAN)
        self.first = Book.objects.create(name="Zebra", count=2)
        self.second = Book.objects.create(name="Beta", count=2)
        self.empty = Book.objects.create(name="Empty", count=0)
        self.now = timezone.now()

    def account(self, name, role=0):
        return CustomUser.objects.create_user(
            email=f"data-{name}@example.com",
            password="test-password",
            first_name=name,
            middle_name="",
            last_name="Reader",
            is_active=True,
            role=role,
        )

    def event(
        self,
        kind=EventType.BOOK_VIEW,
        *,
        book=None,
        user=None,
        properties=None,
        source="server",
        when=None,
    ):
        return UserEvent.objects.create(
            user=user or self.reader,
            book_id=book.pk if book else None,
            event_type=kind,
            source=source,
            occurred_at=when or self.now,
            properties={} if properties is None else properties,
        )

    def stock(self, book, count):
        book.count = count
        book.save(update_fields=["count"])

    def candidates(self, user=None, now=None):
        return list(available_candidates(user or self.reader, now=now or self.now))

    def test_history_is_an_empty_explicit_contract_without_signals_or_ratings(self):
        self.assertEqual(
            read_history(self.reader, now=self.now), RecommendationHistory()
        )
        self.assertEqual(
            asdict(read_history(self.reader)), {"books": (), "searches": ()}
        )

    def test_history_projects_only_minimal_owned_fields(self):
        self.event(
            EventType.ORDER_CREATED,
            book=self.first,
            properties={
                "reader_id": self.reader.pk,
                "issued_by": self.staff.pk,
                "internal_detail": "not part of the public data contract",
            },
        )
        self.event(
            EventType.SEARCH, properties={"query": "  physics  ", "author_id": 123}
        )
        history = read_history(self.reader, now=self.now)
        self.assertEqual(
            history.books, (BookSignal(self.first.pk, EventType.ORDER_CREATED, 4),)
        )
        self.assertEqual(history.searches, ("physics",))
        self.assertEqual(
            set(asdict(history)["books"][0]), {"book_id", "event_type", "weight"}
        )
        self.assertNotIn("issued_by", str(asdict(history)))
        self.assertNotIn("internal_detail", str(asdict(history)))

    def test_foreign_events_and_searches_do_not_enter_any_own_history(self):
        self.event(book=self.first)
        self.event(book=self.second, user=self.other)
        self.event(
            EventType.SEARCH,
            user=self.other,
            properties={"query": "private other query"},
        )
        mine = read_history(self.reader, now=self.now)
        self.assertEqual([s.book_id for s in mine.books], [self.first.pk])
        self.assertEqual(mine.searches, ())
        self.assertEqual(
            read_history(self.staff, now=self.now), RecommendationHistory()
        )

    def test_librarian_processing_another_readers_return_is_not_personal_interest(self):
        self.event(
            EventType.ORDER_RETURNED,
            user=self.staff,
            book=self.first,
            properties={"reader_id": self.reader.pk},
        )
        self.assertEqual(
            read_history(self.staff, now=self.now), RecommendationHistory()
        )
        self.assertEqual(
            read_history(self.reader, now=self.now), RecommendationHistory()
        )
        self.event(
            EventType.ORDER_CREATED,
            book=self.first,
            properties={"reader_id": self.reader.pk},
        )
        self.assertEqual(read_history(self.reader, now=self.now).books[0].weight, 4)

    def test_unauthorized_accounts_are_refused_before_queries(self):
        inactive = self.account("inactive")
        inactive.is_active = False
        unsaved = CustomUser(is_active=True)
        for user in (AnonymousUser(), inactive, unsaved):
            for function in (read_history, available_candidates, fallback_candidates):
                with self.subTest(user=type(user).__name__, function=function.__name__):
                    with self.assertNumQueries(0), self.assertRaises(PermissionDenied):
                        function(user)

    def test_repeats_keep_strongest_action_and_ties_keep_latest(self):
        self.event(
            EventType.ORDER_CREATED, book=self.first, when=self.now - timedelta(hours=2)
        )
        self.event(
            EventType.ORDER_RETURNED,
            book=self.first,
            when=self.now - timedelta(hours=1),
        )
        self.event(EventType.BOOK_VIEW, book=self.first)
        history = read_history(self.reader, now=self.now)
        self.assertEqual(
            history.books, (BookSignal(self.first.pk, EventType.ORDER_RETURNED, 4),)
        )

    def test_only_current_window_and_existing_book_events_are_selected(self):
        self.event(book=self.first, when=self.now - timedelta(days=90))
        self.event(book=self.second, when=self.now - timedelta(days=90, seconds=1))
        self.event(book=self.second, when=self.now + timedelta(seconds=1))
        event = self.event(book=self.second)
        event.book_id = 99999999
        event.save(update_fields=["book_id"])
        self.assertEqual(
            [s.book_id for s in read_history(self.reader, now=self.now).books],
            [self.first.pk],
        )

    def test_client_cannot_supply_stronger_server_loan_events(self):
        self.event(EventType.ORDER_CREATED, book=self.first, source="client")
        self.event(EventType.BOOK_VIEW, book=self.first, source="client")
        self.event(EventType.BOOK_CLICK, book=self.first, source="client")
        self.assertEqual(
            read_history(self.reader, now=self.now).books,
            (BookSignal(self.first.pk, EventType.BOOK_CLICK, 2),),
        )

    def test_recent_event_limit_applies_before_building_book_preferences(self):
        UserEvent.objects.bulk_create(
            [
                UserEvent(
                    user=self.reader,
                    book_id=self.first.pk,
                    event_type=EventType.BOOK_VIEW,
                    source="server",
                    occurred_at=self.now - timedelta(seconds=i),
                )
                for i in range(200)
            ]
        )
        self.event(
            EventType.ORDER_CREATED, book=self.second, when=self.now - timedelta(days=1)
        )
        self.assertEqual(
            read_history(self.reader, now=self.now).books,
            (BookSignal(self.first.pk, EventType.BOOK_VIEW, 1),),
        )

    def test_search_contract_is_bounded_deduplicated_and_trimmed(self):
        for i, text in enumerate(
            ("x" * 250, "X" * 250, "poetry", "history", "ignored")
        ):
            self.event(
                EventType.SEARCH,
                properties={"query": text},
                when=self.now - timedelta(seconds=i),
            )
        self.assertEqual(
            read_history(self.reader, now=self.now).searches,
            ("x" * 200, "poetry", "history"),
        )

    def test_malformed_empty_author_only_and_client_searches_are_ignored(self):
        for properties in (
            {},
            {"author_id": 1},
            {"query": None},
            {"query": 2},
            {"query": " "},
            ["bad"],
        ):
            self.event(EventType.SEARCH, properties=properties)
        self.event(EventType.SEARCH, source="client", properties={"query": "untrusted"})
        self.assertEqual(
            read_history(self.reader, now=self.now), RecommendationHistory()
        )

    def test_data_selection_is_one_history_query_and_never_runs_inference(self):
        self.event(book=self.first)
        self.event(EventType.SEARCH, properties={"query": "physics"})
        with patch("book.embeddings.load_embedding_model") as loader:
            with self.assertNumQueries(1):
                read_history(self.reader, now=self.now)
            self.candidates()
            list(fallback_candidates(self.reader, now=self.now))
        loader.assert_not_called()

    def test_candidates_count_loans_and_reservations_together(self):
        Order.objects.create(
            user=self.other,
            book=self.first,
            plated_end_at=self.now + timedelta(days=14),
        )
        Reservation.objects.create(
            user=self.staff, book=self.first, created_at=self.now
        )
        self.assertEqual([b.pk for b in self.candidates()], [self.second.pk])
        self.assertEqual(self.candidates()[0].available_count, 2)

    def test_return_cancellation_and_stock_changes_affect_next_candidates(self):
        self.stock(self.first, 1)
        loan = Order.objects.create(
            user=self.other,
            book=self.first,
            plated_end_at=self.now + timedelta(days=14),
        )
        self.assertNotIn(self.first, self.candidates())
        loan.end_at = self.now
        loan.save(update_fields=["end_at"])
        self.assertIn(self.first, self.candidates())
        hold = Reservation.objects.create(
            user=self.other, book=self.first, created_at=self.now
        )
        self.assertNotIn(self.first, self.candidates())
        cancel(self.other, hold, now=self.now)
        self.assertIn(self.first, self.candidates())
        self.stock(self.first, 0)
        self.assertNotIn(self.first, self.candidates())

    def test_exact_expiry_deadline_releases_copy_without_worker(self):
        self.stock(self.first, 1)
        Reservation.objects.create(
            user=self.other, book=self.first, created_at=self.now - timedelta(hours=48)
        )
        self.assertNotIn(
            self.first, self.candidates(now=self.now - timedelta(microseconds=1))
        )
        self.assertIn(self.first, self.candidates(now=self.now))

    def test_own_current_loans_and_holds_are_excluded_even_with_spare_copies(self):
        Order.objects.create(
            user=self.reader,
            book=self.first,
            plated_end_at=self.now + timedelta(days=14),
        )
        Reservation.objects.create(
            user=self.reader, book=self.second, created_at=self.now
        )
        self.assertEqual(self.candidates(), [])
        self.assertEqual(list(fallback_candidates(self.reader, now=self.now)), [])

    def test_fallback_is_stable_alphabetical_and_uses_the_same_stock_rule(self):
        upper = Book.objects.create(name="Alpha", count=1)
        lower = Book.objects.create(name="alpha", count=1)
        expected = [upper.pk, lower.pk, self.second.pk, self.first.pk]
        self.assertEqual(
            list(
                fallback_candidates(self.reader, now=self.now).values_list(
                    "pk", flat=True
                )
            ),
            expected,
        )
        self.assertEqual(
            list(
                fallback_candidates(
                    self.reader, now=self.now, exclude_book_ids=(upper.pk,)
                ).values_list("pk", flat=True)
            ),
            expected[1:],
        )
        self.stock(self.first, 0)
        self.assertNotIn(
            self.first, list(fallback_candidates(self.reader, now=self.now))
        )

    def test_missing_embeddings_events_and_rating_models_do_not_break_api_fallback(
        self,
    ):
        BookEmbedding.objects.all().delete()
        client = APIClient()
        client.force_login(self.reader)
        response = client.get("/api/v1/books/recommendations/?limit=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [b["id"] for b in response.json()], [self.second.pk, self.first.pk]
        )
        self.assertEqual(
            [b.pk for b in recommend_books(self.reader, 2)],
            [self.second.pk, self.first.pk],
        )
