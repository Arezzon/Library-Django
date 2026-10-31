"""Ranking, live stock and account-isolation regressions for KAN-31."""

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

from .embedding_config import resolve
from .models import Book, BookEmbedding
from .recommendations import recommend_books
from .testing import FakeEncoderMixin


class RecommendationTests(FakeEncoderMixin, TestCase):
    def setUp(self):
        def account(name, role=0):
            return CustomUser.objects.create_user(
                email=f"{name}@example.com",
                password="test-password",
                first_name=name,
                middle_name="",
                last_name="Reader",
                is_active=True,
                role=role,
            )

        self.reader = account("science")
        self.other = account("art")
        self.librarian = account("librarian", ROLE_LIBRARIAN)
        self.seed = self.book("Science history", 0, 0)
        self.other_seed = self.book("Art history", 0, 1)
        self.science = self.book("Zoology", 2, 0)
        self.art = self.book("Art", 2, 1)
        self.extra = self.book("Biology", 2, 0)
        self.client = APIClient()
        self.client.force_login(self.reader)
        self.now = timezone.now()

    def book(self, name, count, direction):
        book = Book.objects.create(name=name, count=count)
        vector = [0.0] * resolve().dimensions
        vector[direction] = 1.0
        BookEmbedding.objects.filter(book=book).update(vector=vector)
        return book

    def stock(self, book, count):
        book.count = count
        book.save(update_fields=["count"])

    def event(self, user=None, book=None, kind=EventType.BOOK_VIEW, when=None):
        return UserEvent.objects.create(
            user=user or self.reader,
            book_id=(book or self.seed).pk,
            event_type=kind,
            source="server",
            occurred_at=when or self.now,
        )

    def ids(self, user=None, limit=10):
        return [b.pk for b in recommend_books(user or self.reader, limit)]

    def test_different_histories_produce_different_ranking_without_inference(self):
        self.event()
        self.event(self.other, self.other_seed)
        with patch("book.embeddings.load_embedding_model") as loader:
            self.assertEqual(self.ids()[:2], [self.science.pk, self.extra.pk])
            self.assertEqual(self.ids(self.other)[0], self.art.pk)
        loader.assert_not_called()

    def search(self, query, user=None, when=None, source="server"):
        return UserEvent.objects.create(
            user=user or self.reader,
            event_type=EventType.SEARCH,
            source=source,
            properties={"query": query},
            occurred_at=when or self.now,
        )

    def test_search_only_histories_produce_personalized_results(self):
        self.search("solar physics")
        self.search("painting", user=self.other)
        spec = resolve()
        with patch("book.embeddings.load_embedding_model") as loader:
            loader.return_value.embed.side_effect = lambda texts, **kwargs: [
                (
                    [1.0, 0.0] + [0.0] * (spec.dimensions - 2)
                    if texts[0] == spec.query_prefix + "solar physics"
                    else [0.0, 1.0] + [0.0] * (spec.dimensions - 2)
                )
            ]
            self.assertEqual(self.ids()[0], self.science.pk)
            self.assertEqual(self.ids(self.other)[0], self.art.pk)
        self.assertEqual(loader.return_value.embed.call_count, 2)

    def test_searches_are_deduplicated_and_inference_is_bounded(self):
        for i, query in enumerate(
            ["physics", " Physics ", "history", "poetry", "math"]
        ):
            self.search(query, when=self.now - timedelta(seconds=i))
        with patch("book.embeddings.load_embedding_model") as loader:
            loader.return_value.embed.side_effect = lambda texts, **kwargs: [
                [1.0] + [0.0] * (resolve().dimensions - 1)
            ]
            self.ids()
        self.assertEqual(loader.return_value.embed.call_count, 3)
        self.assertEqual(
            [call.args[0] for call in loader.return_value.embed.call_args_list],
            [[resolve().query_prefix + q] for q in ("physics", "history", "poetry")],
        )

    def test_foreign_client_empty_and_malformed_searches_are_ignored(self):
        self.search("painting", user=self.other)
        self.search("painting", source="client")
        self.search(" ")
        self.search(None)
        event = self.search("ignored")
        event.properties = ["not a mapping"]
        event.save(update_fields=["properties"])
        with patch("book.embeddings.load_embedding_model") as loader:
            self.assertEqual(self.ids()[0], self.art.pk)
        loader.assert_not_called()

    def test_search_encoder_failure_preserves_books_or_uses_fallback(self):
        self.search("physics")
        with patch("book.embeddings.load_embedding_model", side_effect=RuntimeError):
            self.assertEqual(self.ids()[0], self.art.pk)
            self.event()
            self.assertEqual(self.ids()[0], self.science.pk)

    def test_invalid_search_vector_preserves_available_fallback(self):
        self.search("physics")
        with patch("book.embeddings.load_embedding_model") as loader:
            loader.return_value.embed.return_value = [[0.0] * resolve().dimensions]
            self.assertEqual(self.ids()[0], self.art.pk)

    def test_stronger_actions_outweigh_repeated_views(self):
        for _ in range(15):
            self.event(book=self.seed)
        self.event(book=self.other_seed, kind=EventType.ORDER_CREATED)
        self.assertEqual(self.ids()[0], self.art.pk)

    def test_signals_from_other_accounts_never_change_own_result(self):
        self.event()
        before = self.ids()
        self.event(self.other, self.other_seed, EventType.ORDER_CREATED)
        self.event(self.librarian, self.other_seed, EventType.ORDER_RETURNED)
        self.assertEqual(self.ids(), before)

    def test_empty_history_is_stable_alphabetical_available_fallback(self):
        self.assertEqual(self.ids(), [self.art.pk, self.extra.pk, self.science.pk])
        self.assertEqual(self.ids(limit=2), self.ids()[:2])

    def test_recent_history_only_and_unusable_events_fall_back(self):
        self.event(when=self.now - timedelta(days=91))
        self.event(kind=EventType.LOGIN)
        self.event(when=self.now + timedelta(days=2))
        event = self.event()
        event.book_id = 99999999
        event.save(update_fields=["book_id"])
        self.assertEqual(self.ids()[0], self.art.pk)

    def test_missing_incompatible_or_zero_profile_vectors_use_fallback(self):
        self.event()
        BookEmbedding.objects.filter(book=self.seed).update(model_revision="old")
        self.assertEqual(self.ids()[0], self.art.pk)
        BookEmbedding.objects.filter(book=self.seed).update(
            model_revision=resolve().tag, vector=[0.0] * resolve().dimensions
        )
        self.assertEqual(self.ids()[0], self.art.pk)
        BookEmbedding.objects.filter(book=self.seed).delete()
        self.assertEqual(self.ids()[0], self.art.pk)

    def test_known_seed_books_are_not_recommended_back_to_reader(self):
        self.stock(self.seed, 2)
        self.event()
        self.assertNotIn(self.seed.pk, self.ids())

    def test_candidates_without_vectors_fill_remaining_slots_without_duplicates(self):
        self.event()
        BookEmbedding.objects.filter(book=self.art).delete()
        self.assertEqual(self.ids(), [self.science.pk, self.extra.pk, self.art.pk])

    def test_no_available_books_returns_empty_list(self):
        for book in Book.objects.all():
            self.stock(book, 0)
        self.assertEqual(self.ids(), [])

    def test_active_loans_and_return_update_personalized_and_fallback_results(self):
        self.stock(self.science, 1)
        loan = Order.objects.create(
            user=self.other,
            book=self.science,
            plated_end_at=self.now + timedelta(days=14),
        )
        self.assertNotIn(self.science.pk, self.ids())
        self.event()
        self.assertNotIn(self.science.pk, self.ids())
        loan.end_at = self.now
        loan.save(update_fields=["end_at"])
        self.assertIn(self.science.pk, self.ids())

    def test_unexpired_reservations_consume_stock_but_deadline_releases_it(self):
        self.stock(self.science, 1)
        Reservation.objects.create(user=self.other, book=self.science)
        self.event()
        self.assertNotIn(self.science.pk, self.ids())
        with patch(
            "book.recommendations.timezone.now",
            return_value=self.now + timedelta(hours=49),
        ):
            self.assertIn(self.science.pk, self.ids())

    def test_cancellation_and_stock_change_update_next_result(self):
        self.stock(self.science, 1)
        reservation = Reservation.objects.create(user=self.other, book=self.science)
        self.assertNotIn(self.science.pk, self.ids())
        cancel(self.other, reservation)
        self.assertIn(self.science.pk, self.ids())
        self.stock(self.science, 0)
        self.assertNotIn(self.science.pk, self.ids())
        self.stock(self.science, 1)
        self.assertIn(self.science.pk, self.ids())

    def test_profile_history_is_bounded_to_latest_200_events(self):
        UserEvent.objects.bulk_create(
            [
                UserEvent(
                    user=self.reader,
                    book_id=self.seed.pk,
                    event_type=EventType.BOOK_VIEW,
                    source="server",
                    occurred_at=self.now - timedelta(seconds=i),
                )
                for i in range(200)
            ]
        )
        self.event(
            book=self.other_seed,
            kind=EventType.ORDER_CREATED,
            when=self.now - timedelta(days=1),
        )
        self.assertEqual(self.ids()[0], self.science.pk)

    def test_loans_and_reservations_are_counted_together(self):
        Order.objects.create(
            user=self.other,
            book=self.science,
            plated_end_at=self.now + timedelta(days=14),
        )
        Reservation.objects.create(user=self.reader, book=self.science)
        self.assertNotIn(self.science.pk, self.ids(self.librarian))

    def test_own_current_loan_or_hold_excluded_even_with_spare_copies(self):
        Order.objects.create(
            user=self.reader,
            book=self.science,
            plated_end_at=self.now + timedelta(days=14),
        )
        Reservation.objects.create(user=self.reader, book=self.art)
        self.assertEqual(self.ids(), [self.extra.pk])

    def test_limit_validation_at_service_boundary(self):
        for limit in (0, -1, 21, True, 1.5, "2"):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                recommend_books(self.reader, limit)

    def test_service_requires_active_account(self):
        with self.assertRaises(PermissionDenied):
            recommend_books(AnonymousUser())
        self.reader.is_active = False
        with self.assertRaises(PermissionDenied):
            recommend_books(self.reader)

    def test_api_returns_only_catalog_fields_and_honors_limit(self):
        response = self.client.get("/api/v1/books/recommendations/", {"limit": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([b["id"] for b in response.json()], self.ids(limit=2))
        self.assertEqual(
            set(response.json()[0]),
            {
                "id",
                "name",
                "description",
                "count",
                "available_count",
                "authors",
                "reason",
            },
        )
        self.assertGreater(response.json()[0]["available_count"], 0)

    def test_anonymous_inactive_and_account_override_are_refused(self):
        self.client.logout()
        self.assertEqual(
            self.client.get("/api/v1/books/recommendations/").status_code, 401
        )
        self.client.force_login(self.reader)
        for parameters in ({"user_id": self.other.pk}, {"user": self.other.pk}):
            self.assertEqual(
                self.client.get(
                    "/api/v1/books/recommendations/", parameters
                ).status_code,
                400,
            )
        self.reader.is_active = False
        self.client.force_authenticate(self.reader)
        self.assertEqual(
            self.client.get("/api/v1/books/recommendations/").status_code, 403
        )

    def test_api_history_is_always_from_session_account_including_librarian(self):
        self.event()
        self.event(self.librarian, self.other_seed)
        self.assertEqual(
            self.client.get("/api/v1/books/recommendations/").json()[0]["id"],
            self.science.pk,
        )
        self.client.force_login(self.librarian)
        self.assertEqual(
            self.client.get("/api/v1/books/recommendations/").json()[0]["id"],
            self.art.pk,
        )

    def test_api_invalid_limits_and_write_methods(self):
        for limit in ("0", "21", "abc", "1.2"):
            self.assertEqual(
                self.client.get(
                    "/api/v1/books/recommendations/", {"limit": limit}
                ).status_code,
                400,
            )
        self.assertEqual(
            self.client.post("/api/v1/books/recommendations/").status_code, 405
        )
