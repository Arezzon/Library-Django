"""Private numerical ratings, strict API validation and PostgreSQL invariants."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from authentication.models import CustomUser

from .models import Book, BookLike, BookRating, FavoriteBook
from .ratings import rating_state, set_rating
from .testing import FakeEncoderMixin


def account(name):
    return CustomUser.objects.create_user(
        email=f"rating-{name}@example.com",
        password="test-password",
        first_name=name,
        last_name="Reader",
        middle_name="",
        is_active=True,
    )


class RatingTests(FakeEncoderMixin, TestCase):
    def setUp(self):
        self.reader = account("one")
        self.other = account("two")
        self.book = Book.objects.create(name="Rating seed", count=1)
        self.url = f"/api/v1/books/{self.book.pk}/rating/"
        self.client = APIClient()
        self.client.force_login(self.reader)

    def test_owned_crud_retries_and_timestamps(self):
        self.assertEqual(
            self.client.get(self.url).json(), {"book_id": self.book.pk, "value": None}
        )
        for _ in range(2):
            self.assertEqual(
                self.client.put(self.url, {"value": 5}, format="json").status_code, 200
            )
        rating = BookRating.objects.get()
        original_time = rating.updated_at
        self.client.put(self.url, {"value": 5}, format="json")
        rating.refresh_from_db()
        self.assertEqual(rating.updated_at, original_time)
        self.assertEqual(
            self.client.patch(self.url, {"value": 1}, format="json").json()["value"], 1
        )
        self.assertEqual(BookRating.objects.count(), 1)
        for _ in range(2):
            self.assertIsNone(self.client.delete(self.url).json()["value"])
        self.assertFalse(BookRating.objects.exists())

    def test_invalid_range_types_and_owner_selectors_do_not_mutate(self):
        set_rating(self.reader, self.book.pk, 4)
        for value in (0, 6, -1, True, False, 1.5, "5", None, [], {}):
            with self.subTest(value=value):
                response = self.client.put(self.url, {"value": value}, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn("no-store", response["Cache-Control"])
        for data in (
            {},
            {"value": 5, "user_id": self.other.pk},
            {"value": 5, "book_id": self.book.pk},
            {"liked": True},
        ):
            self.assertEqual(
                self.client.put(self.url, data, format="json").status_code, 400
            )
        for method in (
            self.client.get,
            self.client.put,
            self.client.patch,
            self.client.delete,
        ):
            self.assertEqual(method(self.url + "?user_id=2").status_code, 400)
        self.assertEqual(
            self.client.delete(
                self.url, {"user_id": self.other.pk}, format="json"
            ).status_code,
            400,
        )
        self.assertEqual(rating_state(self.reader, self.book.pk)["value"], 4)

    def test_no_other_reader_or_librarian_can_target_foreign_state(self):
        set_rating(self.other, self.book.pk, 1)
        for role in (0, 1):
            self.reader.role = role
            self.reader.save(update_fields=["role"])
            self.assertIsNone(self.client.get(self.url).json()["value"])
            self.client.put(self.url, {"value": 5}, format="json")
            self.client.delete(self.url)
            self.assertEqual(rating_state(self.other, self.book.pk)["value"], 1)
        self.assertEqual(
            self.client.get("/api/v1/books/999999/rating/").status_code, 404
        )
        self.assertEqual(
            self.client.put(
                "/api/v1/books/999999/rating/", {"value": 5}, format="json"
            ).status_code,
            404,
        )

    def test_authentication_csrf_and_service_defense(self):
        self.client.logout()
        for method in (
            self.client.get,
            self.client.put,
            self.client.patch,
            self.client.delete,
        ):
            self.assertEqual(method(self.url).status_code, 401)
        self.reader.is_active = False
        self.reader.save(update_fields=["is_active"])
        self.client.force_authenticate(self.reader)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        for user in (AnonymousUser(), self.reader):
            with self.assertRaises(PermissionDenied):
                set_rating(user, self.book.pk, 5)
        self.reader.is_active = True  # stale object: database account is still inactive
        with self.assertRaises(PermissionDenied):
            set_rating(self.reader, self.book.pk, 5)
        with self.assertRaises(ValueError):
            set_rating(self.reader, self.book.pk, "5")
        self.reader.save(update_fields=["is_active"])
        browser = APIClient(enforce_csrf_checks=True)
        browser.force_login(self.reader)
        self.assertEqual(
            browser.put(self.url, {"value": 5}, format="json").status_code, 403
        )

    def test_model_constraints_and_cascade(self):
        rating = BookRating.objects.create(user=self.reader, book=self.book, value=3)
        self.assertEqual(str(rating), f"Rating(book={self.book.pk})")
        for value in (0, 6):
            with self.assertRaises(ValidationError):
                BookRating(user=self.other, book=self.book, value=value).full_clean()
            with self.assertRaises(IntegrityError), transaction.atomic():
                BookRating.objects.create(user=self.other, book=self.book, value=value)
        with self.assertRaises(IntegrityError), transaction.atomic():
            BookRating.objects.create(user=self.reader, book=self.book, value=4)
        self.book.delete()
        self.assertFalse(BookRating.objects.exists())

    def test_ratings_are_durable_and_independent_of_feedback_and_queue(self):
        BookLike.objects.create(user=self.reader, book=self.book)
        FavoriteBook.objects.create(user=self.reader, book=self.book)
        with patch(
            "events.services.persist_event.apply_async",
            side_effect=RuntimeError("offline"),
        ):
            self.client.put(self.url, {"value": 1}, format="json")
        self.client.logout()
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get(self.url).json()["value"], 1)
        self.client.delete(self.url)
        self.assertTrue(BookLike.objects.exists())
        self.assertTrue(FavoriteBook.objects.exists())


class ConcurrentRatingTests(FakeEncoderMixin, TransactionTestCase):
    def test_simultaneous_retries_keep_one_current_rating(self):
        user = account("concurrent")
        book = Book.objects.create(name="Concurrent rating", count=1)
        barrier = Barrier(2)

        def save():
            close_old_connections()
            try:
                actor = CustomUser.objects.get(pk=user.pk)
                barrier.wait(timeout=10)
                return set_rating(actor, book.pk, 5)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: save(), range(2)))
        self.assertTrue(all(row["value"] == 5 for row in results))
        self.assertEqual(BookRating.objects.filter(user=user, book=book).count(), 1)


class RatingMigrationTests(TransactionTestCase):
    def test_existing_catalog_survives_forward_migration(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("book", "0006_booklike_favoritebook")])
        try:
            old_apps = executor.loader.project_state(
                [("book", "0006_booklike_favoritebook")]
            ).apps
            legacy = old_apps.get_model("book", "Book").objects.create(
                name="Existing catalog book", count=3
            )
            identity = legacy.pk
            executor = MigrationExecutor(connection)
            executor.migrate([("book", "0007_book_rating")])
            self.assertEqual(
                Book.objects.get(pk=identity).name, "Existing catalog book"
            )
            self.assertEqual(Book.objects.get(pk=identity).count, 3)
            self.assertFalse(BookRating.objects.exists())
        finally:
            MigrationExecutor(connection).migrate([("book", "0007_book_rating")])
