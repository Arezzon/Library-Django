"""Controlled quality checks for current, private numerical rating signals."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import CustomUser
from order.models import Order, Reservation

from .embedding_config import resolve
from .models import Book, BookEmbedding, BookLike, FavoriteBook
from .rating_rules import rating_weight
from .ratings import read_rating_signals, set_rating
from .recommendations import recommend_books
from .testing import FakeEncoderMixin


class RatingRecommendationTests(FakeEncoderMixin, TestCase):
    def setUp(self):
        self.reader = self.account("reader")
        self.other = self.account("other")
        self.seed = self.book("Own rated science seed", 0, [1, 0])
        self.other_seed = self.book("Other private art seed", 0, [0, 1])
        self.science = self.book("A Science candidate", 2, [1, 0])
        self.art = self.book("Z Art candidate", 2, [0, 1])
        self.client = APIClient()
        self.client.force_login(self.reader)
        self.rating_url = f"/api/v1/books/{self.seed.pk}/rating/"

    def account(self, name):
        return CustomUser.objects.create_user(
            email=f"rating-rec-{name}@example.com",
            password="test-password",
            first_name=name,
            last_name="Reader",
            middle_name="",
            is_active=True,
        )

    def book(self, name, count, xy):
        book = Book.objects.create(name=name, count=count)
        BookEmbedding.objects.filter(book=book).update(
            vector=xy + [0.0] * (resolve().dimensions - 2)
        )
        return book

    def ids(self, user=None):
        return [book.pk for book in recommend_books(user or self.reader, 20)]

    def test_all_scale_values_have_the_documented_direction_and_stable_top_n(self):
        self.assertEqual(
            [rating_weight(value) for value in range(1, 6)], [-12, -6, 0, 6, 12]
        )
        for value in range(1, 6):
            with self.subTest(value=value):
                set_rating(self.reader, self.seed.pk, value)
                expected = self.art if value < 3 else self.science
                self.assertEqual(self.ids()[0], expected.pk)
                self.assertEqual(self.ids(), self.ids())
                self.assertNotIn(self.seed.pk, self.ids())
                self.assertEqual(len(recommend_books(self.reader, 1)), 1)

    def test_different_readers_have_different_rankings_and_owned_input(self):
        set_rating(self.reader, self.seed.pk, 5)
        set_rating(self.other, self.seed.pk, 1)
        self.assertEqual(self.ids()[0], self.science.pk)
        self.assertEqual(self.ids(self.other)[0], self.art.pk)
        with self.assertNumQueries(1):
            signals = read_rating_signals(self.reader)
        self.assertEqual(len(signals), 1)
        self.assertEqual(vars(signals[0]), {"book_id": self.seed.pk, "value": 5})
        self.assertNotEqual(signals, read_rating_signals(self.other))

    def test_api_update_and_delete_affect_the_next_recommendation_request(self):
        def first():
            response = self.client.get("/api/v1/books/recommendations/?limit=1")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Cache-Control"], "private, no-store")
            return response.json()[0]["id"]

        self.client.put(self.rating_url, {"value": 5}, format="json")
        self.assertEqual(first(), self.science.pk)
        self.client.patch(self.rating_url, {"value": 1}, format="json")
        self.assertEqual(first(), self.art.pk)
        self.client.delete(self.rating_url)
        self.assertEqual(first(), self.science.pk)
        self.assertEqual(read_rating_signals(self.reader), ())

    def test_4_to_5_changes_strength_against_competing_explicit_signals(self):
        second_art_seed = self.book("Another own art seed", 0, [0, 1])
        BookLike.objects.create(user=self.reader, book=self.other_seed)
        FavoriteBook.objects.create(user=self.reader, book=second_art_seed)
        set_rating(self.reader, self.seed.pk, 4)
        self.assertEqual(self.ids()[0], self.art.pk)
        set_rating(self.reader, self.seed.pk, 5)
        self.assertEqual(self.ids()[0], self.science.pk)

    def test_low_rating_overrides_same_book_like_and_removal_restores_it(self):
        BookLike.objects.create(user=self.reader, book=self.seed)
        FavoriteBook.objects.create(user=self.reader, book=self.seed)
        set_rating(self.reader, self.seed.pk, 1)
        self.assertEqual(self.ids()[0], self.art.pk)
        set_rating(self.reader, self.seed.pk, None)
        self.assertEqual(self.ids()[0], self.science.pk)
        self.assertTrue(
            BookLike.objects.filter(user=self.reader, book=self.seed).exists()
        )
        self.assertTrue(
            FavoriteBook.objects.filter(user=self.reader, book=self.seed).exists()
        )

    def test_neutral_rating_keeps_independent_positive_signals(self):
        BookLike.objects.create(user=self.reader, book=self.seed)
        set_rating(self.reader, self.seed.pk, 3)
        result = recommend_books(self.reader, 1)[0]
        self.assertEqual(result.pk, self.science.pk)
        self.assertIn("подобається", result.reason)
        self.assertNotIn("високо", result.reason)

    def test_rated_books_are_excluded_even_with_no_usable_vector_or_profile(self):
        set_rating(self.reader, self.science.pk, 3)
        BookEmbedding.objects.filter(book=self.science).delete()
        self.assertEqual(self.ids(), [self.art.pk])
        set_rating(self.reader, self.art.pk, 3)
        self.assertEqual(self.ids(), [])
        set_rating(self.reader, self.science.pk, None)
        self.assertEqual(self.ids(), [self.science.pk])

    def test_signal_cap_does_not_reintroduce_older_rated_books(self):
        set_rating(self.reader, self.science.pk, 3)
        set_rating(self.reader, self.seed.pk, 5)
        set_rating(self.reader, self.other_seed.pk, 5)
        with patch("book.ratings.RATING_SIGNAL_LIMIT", 2):
            self.assertEqual(len(read_rating_signals(self.reader)), 2)
            self.assertNotIn(
                self.science.pk,
                [row.book_id for row in read_rating_signals(self.reader)],
            )
            self.assertNotIn(self.science.pk, self.ids())

    def test_loan_return_reservation_expiry_and_stock_are_rechecked(self):
        set_rating(self.reader, self.seed.pk, 5)
        self.science.count = 1
        self.science.save(update_fields=["count"])
        self.assertIn(self.science.pk, self.ids())
        loan = Order.objects.create(
            user=self.other,
            book=self.science,
            plated_end_at=timezone.now() + timedelta(days=7),
        )
        self.assertNotIn(self.science.pk, self.ids())
        loan.end_at = timezone.now()
        loan.save(update_fields=["end_at"])
        self.assertIn(self.science.pk, self.ids())
        hold = Reservation.objects.create(user=self.other, book=self.science)
        self.assertNotIn(self.science.pk, self.ids())
        with patch("book.recommendations.timezone.now", return_value=hold.expires_at):
            self.assertIn(self.science.pk, self.ids())
        self.science.count = 0
        self.science.save(update_fields=["count"])
        self.assertNotIn(self.science.pk, self.ids())
        self.assertTrue(
            all(book.available_count > 0 for book in recommend_books(self.reader))
        )

    def test_reasons_use_only_own_actual_high_or_low_rating(self):
        set_rating(self.reader, self.seed.pk, 5)
        set_rating(self.other, self.other_seed.pk, 5)
        reasons = [book.reason for book in recommend_books(self.reader)]
        self.assertIn("високо", reasons[0])
        self.assertIn(self.seed.name, reasons[0])
        self.assertNotIn(self.other_seed.name, " ".join(reasons))
        opposite = self.book("Opposite direction candidate", 1, [-1, 0])
        set_rating(self.reader, self.seed.pk, 1)
        result = recommend_books(self.reader, 1)[0]
        self.assertEqual(result.pk, opposite.pk)
        self.assertIn("низької оцінки", result.reason)
        self.assertNotIn("високо", result.reason)

    def test_no_inference_or_new_embedding_is_required_and_access_is_checked(self):
        previous = list(BookEmbedding.objects.values_list("book_id", "updated_at"))
        with patch(
            "book.embeddings.load_embedding_model",
            side_effect=AssertionError("inference forbidden"),
        ):
            set_rating(self.reader, self.seed.pk, 5)
            self.assertEqual(self.ids()[0], self.science.pk)
            set_rating(self.reader, self.seed.pk, 1)
            self.assertEqual(self.ids()[0], self.art.pk)
        self.assertEqual(
            list(BookEmbedding.objects.values_list("book_id", "updated_at")), previous
        )
        with self.assertRaises(PermissionDenied), self.assertNumQueries(0):
            read_rating_signals(AnonymousUser())
