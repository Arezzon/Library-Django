"""Current owned rating, aggregate-only summary and keyboard-ready form semantics."""

from django.test import Client, TestCase
from rest_framework.test import APIClient

from authentication.models import CustomUser

from .models import Book, BookRating
from .ratings import rating_overview, set_rating
from .testing import FakeEncoderMixin


class RatingInterfaceTests(FakeEncoderMixin, TestCase):
    def setUp(self):
        self.reader = self.account("reader")
        self.other = self.account("other")
        self.book = Book.objects.create(name="Rating interface book", count=1)
        self.detail = f"/book/{self.book.pk}/"
        self.action = self.detail + "rating/"
        self.summary = f"/api/v1/books/{self.book.pk}/rating-summary/"
        self.client = APIClient()
        self.client.force_login(self.reader)

    def account(self, name):
        return CustomUser.objects.create_user(
            email=f"rating-ui-{name}@example.com",
            password="test-password",
            first_name=name,
            last_name="Reader",
            middle_name="",
            is_active=True,
        )

    def test_empty_aggregate_and_owned_form(self):
        response = self.client.get(self.detail)
        self.assertContains(response, "You have not rated this book yet.")
        self.assertContains(response, "No ratings yet.")
        self.assertContains(response, 'for="id_value"')
        self.assertContains(response, 'aria-describedby="rating-help rating-errors"')
        self.assertContains(response, 'tabindex="-1"')
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(
            self.client.get(self.summary).json(),
            {"book_id": self.book.pk, "average": None, "count": 0},
        )

    def test_save_change_remove_and_new_login_keep_one_current_row(self):
        for _ in range(2):
            self.assertEqual(
                self.client.post(
                    self.action, {"action": "set", "value": "5"}
                ).status_code,
                302,
            )
        self.assertEqual(BookRating.objects.count(), 1)
        self.client.logout()
        self.client.force_login(self.reader)
        self.assertContains(self.client.get(self.detail), "5 / 5")
        self.client.post(self.action, {"action": "set", "value": "1"})
        self.assertEqual(BookRating.objects.get().value, 1)
        self.assertEqual(BookRating.objects.count(), 1)
        for _ in range(2):
            self.assertEqual(
                self.client.post(self.action, {"action": "remove"}).status_code, 302
            )
        self.assertFalse(BookRating.objects.exists())
        self.assertContains(
            self.client.get(self.detail), "You have not rated this book yet."
        )

    def test_aggregate_updates_without_exposing_other_raters(self):
        set_rating(self.reader, self.book.pk, 5)
        set_rating(self.other, self.book.pk, 1)
        with self.assertNumQueries(1):
            overview = rating_overview(self.reader, self.book.pk)
        self.assertEqual(
            overview, {"book_id": self.book.pk, "value": 5, "average": 3.0, "count": 2}
        )
        data = self.client.get(self.summary).json()
        self.assertEqual(data, {"book_id": self.book.pk, "average": 3.0, "count": 2})
        self.assertNotIn("value", data)
        response = self.client.get(self.detail)
        self.assertContains(response, "3.00 / 5")
        self.assertNotContains(response, self.other.email)
        self.assertEqual(response.context["rating_form"].initial["value"], 5)
        set_rating(self.other, self.book.pk, None)
        self.assertEqual(self.client.get(self.summary).json()["count"], 1)
        self.assertEqual(self.client.get(self.summary).json()["average"], 5.0)

    def test_invalid_values_and_foreign_selectors_do_not_change_current_state(self):
        set_rating(self.reader, self.book.pk, 4)
        set_rating(self.other, self.book.pk, 2)
        for value in ("0", "6", "1.5", "True", ""):
            response = self.client.post(self.action, {"action": "set", "value": value})
            self.assertContains(response, 'role="alert"', status_code=400)
            self.assertEqual(BookRating.objects.get(user=self.reader).value, 4)
        for data in (
            {"action": "remove", "user_id": self.other.pk},
            {"action": "remove", "value": "2"},
            {"action": "set", "value": ["1", "5"]},
            {"action": "invalid"},
        ):
            self.assertEqual(self.client.post(self.action, data).status_code, 400)
        self.assertEqual(
            self.client.post(
                self.action + "?user_id=2", {"action": "remove"}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(self.summary, {"user_id": self.other.pk}).status_code, 400
        )
        self.assertEqual(BookRating.objects.get(user=self.other).value, 2)
        self.assertEqual(BookRating.objects.get(user=self.reader).value, 4)

    def test_access_csrf_and_read_only_get(self):
        self.assertEqual(self.client.get(self.action).status_code, 405)
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.reader)
        self.assertEqual(
            browser.post(self.action, {"action": "set", "value": "5"}).status_code, 403
        )
        self.client.logout()
        self.assertEqual(
            self.client.post(self.action, {"action": "remove"}).status_code, 302
        )
        self.assertEqual(self.client.get(self.summary).status_code, 401)
        self.reader.is_active = False
        self.reader.save(update_fields=["is_active"])
        self.client.force_authenticate(self.reader)
        self.assertEqual(self.client.get(self.summary).status_code, 403)
        self.assertFalse(BookRating.objects.exists())

    def test_missing_summary_and_foreign_state_after_session_change(self):
        self.assertEqual(
            self.client.get("/api/v1/books/999999/rating-summary/").status_code, 404
        )
        set_rating(self.reader, self.book.pk, 5)
        self.client.logout()
        self.client.force_login(self.other)
        response = self.client.get(self.detail)
        self.assertIsNone(response.context["rating_overview"]["value"])
        self.assertContains(response, "You have not rated this book yet.")
        self.assertContains(response, "5.00 / 5")
