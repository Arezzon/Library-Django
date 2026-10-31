"""Faithful, private explanations without changing recommendation ranking."""

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import CustomUser
from events.models import EventType, UserEvent

from .embedding_config import resolve
from .models import Book, BookEmbedding
from .recommendations import recommend_books
from .testing import FakeEncoderMixin


class RecommendationReasonTests(FakeEncoderMixin, TestCase):
    def setUp(self):
        self.reader = self.account("reader")
        self.other = self.account("other")
        self.first_seed = self.book("Власна історія", 0, (1, 0))
        self.second_seed = self.book("Інша власна книга", 0, (0, 1))
        self.first = self.book("First candidate", 2, (1, 0))
        self.second = self.book("Second candidate", 2, (0, 1))
        self.client = APIClient()
        self.client.force_login(self.reader)

    def account(self, name):
        return CustomUser.objects.create_user(
            email=f"reason-{name}@example.com",
            password="test-password",
            first_name=name,
            middle_name="",
            last_name="Reader",
            is_active=True,
        )

    def book(self, name, count, xy):
        book = Book.objects.create(name=name, count=count)
        self.vector(book, xy)
        return book

    def vector(self, book, xy):
        BookEmbedding.objects.filter(book=book).update(
            vector=list(xy) + [0.0] * (resolve().dimensions - 2)
        )

    def event(self, book=None, kind=EventType.BOOK_VIEW, user=None, query=None):
        return UserEvent.objects.create(
            user=user or self.reader,
            book_id=book.pk if book else None,
            event_type=kind,
            source="server",
            occurred_at=timezone.now(),
            properties={"query": query} if query else {},
        )

    def reasons(self):
        return {b.pk: b.reason for b in recommend_books(self.reader, 2)}

    def test_book_reasons_distinguish_actions_instead_of_claiming_reading(self):
        cases = [
            (EventType.BOOK_VIEW, "ви переглядали"),
            (EventType.BOOK_CLICK, "ви цікавилися книгою"),
            (EventType.BORROW_INTENT, "ви хотіли взяти"),
            (EventType.ORDER_CREATED, "ви брали в бібліотеці"),
            (EventType.ORDER_RETURNED, "ви повернули"),
        ]
        for kind, expected in cases:
            with self.subTest(kind=kind):
                UserEvent.objects.all().delete()
                self.event(self.first_seed, kind)
                reason = self.reasons()[self.first.pk]
                self.assertIn(expected, reason)
                self.assertIn(self.first_seed.name, reason)
                self.assertNotIn("ви читали", reason)

    def test_reason_is_chosen_for_each_candidate_not_just_latest_event(self):
        self.event(self.first_seed)
        self.event(self.second_seed)
        reasons = self.reasons()
        self.assertIn(self.first_seed.name, reasons[self.first.pk])
        self.assertIn(self.second_seed.name, reasons[self.second.pk])

    def test_weighted_contribution_beats_nearest_unweighted_source(self):
        self.vector(self.second_seed, (0.6, 0.8))
        self.event(self.first_seed, EventType.BOOK_VIEW)
        self.event(self.second_seed, EventType.ORDER_CREATED)
        reason = self.reasons()[self.first.pk]
        self.assertIn(self.second_seed.name, reason)
        self.assertIn("ви брали", reason)
        self.assertNotIn(self.first_seed.name, reason)

    def test_strongest_book_action_supplies_the_reason(self):
        self.event(self.first_seed, EventType.ORDER_CREATED)
        self.event(self.first_seed, EventType.BOOK_VIEW)
        self.assertIn("ви брали", self.reasons()[self.first.pk])

    def test_empty_history_has_truthful_fallback_reason_for_every_result(self):
        for reason in self.reasons().values():
            self.assertEqual(reason, "Доступна книга із запасного списку рекомендацій.")

    def test_fallback_padding_does_not_claim_a_personal_signal(self):
        self.event(self.first_seed)
        BookEmbedding.objects.filter(book=self.second).delete()
        reasons = self.reasons()
        self.assertIn(self.first_seed.name, reasons[self.first.pk])
        self.assertEqual(
            reasons[self.second.pk], "Доступна книга із запасного списку рекомендацій."
        )

    def test_deleted_or_incompatible_seed_is_not_named(self):
        self.event(self.first_seed)
        BookEmbedding.objects.filter(book=self.first_seed).update(model_revision="old")
        self.assertTrue(all("запасного списку" in r for r in self.reasons().values()))
        self.first_seed.delete()
        self.assertTrue(all("запасного списку" in r for r in self.reasons().values()))

    def test_search_reason_names_only_the_callers_effective_search(self):
        self.event(kind=EventType.SEARCH, query="власний пошук")
        self.event(
            kind=EventType.SEARCH, user=self.other, query="чужий приватний пошук"
        )
        reasons = self.reasons()
        self.assertIn("за вашим пошуком «власний пошук»", reasons[self.first.pk])
        self.assertNotIn("чужий приватний пошук", str(reasons))
        # A nonpositive contribution gets a neutral profile reason, not a false match.
        self.assertEqual(
            reasons[self.second.pk], "Рекомендовано за сукупністю ваших інтересів."
        )

    def test_failed_search_encoding_is_not_presented_as_a_reason(self):
        self.event(kind=EventType.SEARCH, query="необроблений пошук")
        self.event(self.first_seed)
        with patch("book.embeddings.load_embedding_model", side_effect=RuntimeError):
            reason = self.reasons()[self.first.pk]
        self.assertIn(self.first_seed.name, reason)
        self.assertNotIn("необроблений пошук", reason)

    def test_nonpositive_contributions_do_not_invent_a_specific_match(self):
        self.vector(self.first, (-1, 0))
        self.event(self.first_seed)
        self.assertEqual(
            self.reasons()[self.first.pk],
            "Рекомендовано за сукупністю ваших інтересів.",
        )

    def test_equal_contributions_have_stable_reasons_and_ranking(self):
        self.vector(self.second_seed, (1, 0))
        self.event(self.first_seed)
        self.event(self.second_seed)
        before = [(b.pk, b.reason) for b in recommend_books(self.reader, 2)]
        after = [(b.pk, b.reason) for b in recommend_books(self.reader, 2)]
        self.assertEqual(before, after)
        self.assertIn(self.first_seed.name, dict(before)[self.first.pk])

    def test_explanation_does_not_load_model_or_issue_per_book_queries(self):
        self.event(self.first_seed)
        self.event(self.second_seed)
        with patch("book.embeddings.load_embedding_model") as loader:
            with self.assertNumQueries(4):
                results = recommend_books(self.reader, 2)
        loader.assert_not_called()
        self.assertTrue(all(book.reason for book in results))

    def test_api_returns_reason_but_never_another_accounts_reason(self):
        self.event(self.first_seed, EventType.ORDER_CREATED)
        self.event(self.second_seed, EventType.ORDER_CREATED, user=self.other)
        response = self.client.get("/api/v1/books/recommendations/?limit=1")
        self.assertEqual(response.status_code, 200)
        reason = response.json()[0]["reason"]
        self.assertIn(self.first_seed.name, reason)
        self.assertNotIn(self.second_seed.name, reason)
        self.assertNotIn("user_id", response.json()[0])
        self.client.force_login(self.other)
        response = self.client.get("/api/v1/books/recommendations/?limit=1")
        self.assertIn(self.second_seed.name, response.json()[0]["reason"])

    def test_schema_documents_reason_and_other_catalog_responses_are_unchanged(self):
        schema = self.client.get("/api/schema/?format=json").json()
        response = schema["paths"]["/api/v1/books/recommendations/"]["get"][
            "responses"
        ]["200"]
        ref = response["content"]["application/json"]["schema"]["items"]["$ref"]
        properties = schema["components"]["schemas"][ref.rsplit("/", 1)[1]][
            "properties"
        ]
        self.assertEqual(properties["reason"]["type"], "string")
        self.assertTrue(properties["reason"]["readOnly"])
        detail = self.client.get(f"/api/v1/book/{self.first.pk}/").json()
        self.assertNotIn("reason", detail)
