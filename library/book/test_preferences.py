"""Persistence, private access and explicit recommendation signals."""

from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import CustomUser

from .embedding_config import resolve
from .models import Book, BookEmbedding, BookLike, FavoriteBook
from .preferences import preference_state, read_book_preferences, set_preferences
from .recommendations import recommend_books
from .testing import FakeEncoderMixin


class PreferenceTests(FakeEncoderMixin, TestCase):
    def setUp(self):
        self.user = self.account("one")
        self.other = self.account("two")
        self.book = Book.objects.create(name="Private seed", count=0)
        self.candidate = Book.objects.create(name="Z matching", count=1)
        self.fallback = Book.objects.create(name="A fallback", count=1)
        for book, xy in (
            (self.book, [1, 0]),
            (self.candidate, [1, 0]),
            (self.fallback, [0, 1]),
        ):
            BookEmbedding.objects.filter(book=book).update(
                vector=xy + [0.0] * (resolve().dimensions - 2)
            )
        self.client = APIClient()
        self.client.force_login(self.user)
        self.url = f"/api/v1/books/{self.book.pk}/preferences/"
        self.list_url = "/api/v1/me/book-preferences/"

    def account(self, name):
        return CustomUser.objects.create_user(
            email=f"pref-{name}@example.com",
            password="test-password",
            first_name=name,
            last_name="Reader",
            middle_name="",
            is_active=True,
        )

    def test_partial_idempotent_updates_and_delete(self):
        self.assertEqual(
            self.client.get(self.url).json(),
            {"book_id": self.book.pk, "liked": False, "favorite": False},
        )
        for _ in range(2):
            self.assertEqual(
                self.client.patch(self.url, {"liked": True}, format="json").status_code,
                200,
            )
        self.client.patch(self.url, {"favorite": True}, format="json")
        self.assertEqual(BookLike.objects.count(), 1)
        self.assertEqual(FavoriteBook.objects.count(), 1)
        self.client.patch(self.url, {"liked": False}, format="json")
        self.assertEqual(
            preference_state(self.user, self.book.pk),
            {"book_id": self.book.pk, "liked": False, "favorite": True},
        )
        for _ in range(2):
            self.assertEqual(self.client.delete(self.url).status_code, 200)
        self.assertFalse(BookLike.objects.exists())
        self.assertFalse(FavoriteBook.objects.exists())

    def test_states_survive_new_session_and_queue_failure(self):
        with patch(
            "events.services.persist_event.apply_async",
            side_effect=RuntimeError("offline"),
        ):
            self.client.patch(
                self.url, {"liked": True, "favorite": True}, format="json"
            )
        self.client.logout()
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertTrue(response.json()["liked"])
        self.assertTrue(response.json()["favorite"])
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_only_own_state_even_for_librarian(self):
        set_preferences(self.other, self.book.pk, liked=True, favorite=True)
        for role in (0, 1):
            self.user.role = role
            self.user.save(update_fields=["role"])
            self.assertFalse(self.client.get(self.url).json()["liked"])
            self.assertEqual(self.client.get(self.list_url).json(), [])
            self.client.delete(self.url)
            self.assertTrue(preference_state(self.other, self.book.pk)["liked"])
            self.assertEqual(read_book_preferences(self.user), ())
            self.assertNotContains(
                self.client.get("/book/preferences/"), "Private seed"
            )

    def test_reject_owner_selectors_ratings_and_non_boolean_values(self):
        for data in (
            {},
            {"user_id": self.other.pk, "liked": True},
            {"book_id": self.candidate.pk},
            {"rating": 5},
            {"liked": "true"},
            {"favorite": 1},
            {"liked": None},
        ):
            with self.subTest(data=data):
                self.assertEqual(
                    self.client.patch(self.url, data, format="json").status_code, 400
                )
        self.assertEqual(
            self.client.get(self.url, {"user_id": self.other.pk}).status_code, 400
        )
        self.assertEqual(
            self.client.get(self.list_url, {"user_id": self.other.pk}).status_code, 400
        )
        self.assertEqual(
            self.client.get(self.list_url, {"kind": "ratings"}).status_code, 400
        )
        self.assertFalse(BookLike.objects.exists())

    def test_authentication_and_csrf(self):
        self.client.logout()
        for method in (self.client.get, self.client.patch, self.client.delete):
            self.assertEqual(method(self.url).status_code, 401)
        self.assertEqual(self.client.get(self.list_url).status_code, 401)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        for user in (self.user, AnonymousUser()):
            with self.assertRaises(PermissionDenied):
                read_book_preferences(user)
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.user)
        self.assertEqual(
            browser.post(
                f"/book/{self.book.pk}/preferences/", {"action": "like"}
            ).status_code,
            403,
        )
        self.assertEqual(
            browser.patch(
                self.url, data='{"liked":true}', content_type="application/json"
            ).status_code,
            403,
        )

    def test_web_desired_actions_filters_and_unavailable_saved_book(self):
        url = f"/book/{self.book.pk}/preferences/"
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(
            self.client.post(
                url, {"action": "like", "user_id": self.other.pk}
            ).status_code,
            400,
        )
        for _ in range(2):
            self.assertEqual(
                self.client.post(url, {"action": "favorite"}).status_code, 302
            )
        self.assertEqual(FavoriteBook.objects.count(), 1)
        self.assertEqual(self.client.get(self.list_url, {"kind": "likes"}).json(), [])
        saved = self.client.get(self.list_url, {"kind": "favorites"}).json()
        self.assertEqual([item["id"] for item in saved], [self.book.pk])
        self.assertContains(self.client.get("/book/preferences/"), "Private seed")
        self.assertContains(
            self.client.get(f"/book/{self.book.pk}/"), 'aria-pressed="true"'
        )
        self.assertIn(
            "no-store", self.client.get(f"/book/{self.book.pk}/")["Cache-Control"]
        )
        self.assertNotIn(self.book.pk, [b.pk for b in recommend_books(self.user)])
        self.client.post(url, {"action": "unfavorite"})
        self.assertEqual(self.client.get(self.list_url).json(), [])

    def test_constraints_and_cascade(self):
        for model in (BookLike, FavoriteBook):
            model.objects.create(user=self.user, book=self.book)
            with self.assertRaises(IntegrityError), transaction.atomic():
                model.objects.create(user=self.user, book=self.book)
        self.book.delete()
        self.assertFalse(BookLike.objects.exists())
        self.assertFalse(FavoriteBook.objects.exists())

    def test_current_preferences_change_ranking_and_removal_restores_fallback(self):
        self.assertEqual(recommend_books(self.user, 1)[0].pk, self.fallback.pk)
        for flag, reason in (("liked", "подобається"), ("favorite", "до обраного")):
            with self.subTest(flag=flag):
                set_preferences(self.user, self.book.pk, **{flag: True})
                result = recommend_books(self.user, 1)[0]
                self.assertEqual(result.pk, self.candidate.pk)
                self.assertIn(reason, result.reason)
                self.assertIn(self.book.name, result.reason)
                self.assertEqual(recommend_books(self.other, 1)[0].pk, self.fallback.pk)
                set_preferences(self.user, self.book.pk, liked=False, favorite=False)
                self.assertEqual(recommend_books(self.user, 1)[0].pk, self.fallback.pk)

    def test_combined_preferences_supply_one_signal(self):
        from .recommendations import _profile

        set_preferences(self.user, self.book.pk, liked=True, favorite=True)
        signals = read_book_preferences(self.user)
        self.assertEqual(len(signals), 1)
        self.assertTrue(signals[0].liked and signals[0].favorite)
        self.assertEqual(len(_profile(self.user, timezone.now())[2]), 1)


class ConcurrentPreferenceTests(FakeEncoderMixin, TransactionTestCase):
    def test_simultaneous_repeated_adds_create_one_row_per_state(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        from django.db import close_old_connections

        user = CustomUser.objects.create_user(
            email="concurrent-pref@example.com",
            password="test-password",
            first_name="Reader",
            last_name="Test",
            middle_name="",
            is_active=True,
        )
        book = Book.objects.create(name="Concurrent seed", count=1)
        barrier = Barrier(2)

        def add():
            close_old_connections()
            try:
                actor = CustomUser.objects.get(pk=user.pk)
                barrier.wait(timeout=10)
                return set_preferences(actor, book.pk, liked=True, favorite=True)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: add(), range(2)))
        self.assertTrue(
            all(result["liked"] and result["favorite"] for result in results)
        )
        self.assertEqual(BookLike.objects.filter(user=user, book=book).count(), 1)
        self.assertEqual(FavoriteBook.objects.filter(user=user, book=book).count(), 1)
