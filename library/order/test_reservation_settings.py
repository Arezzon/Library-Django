"""The shared collection policy, role boundary and recorded reservation deadline."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import ROLE_ADMINISTRATOR, ROLE_LIBRARIAN
from book.models import Book
from book.testing import FakeEncoderMixin

from .models import Reservation, ReservationSettings
from .services import reserve
from .test_reservations import account


class ReservationSettingsTests(FakeEncoderMixin, TestCase):
    def setUp(self):
        self.librarian = account("policy-librarian@example.com", ROLE_LIBRARIAN)
        self.reader = account("policy-reader@example.com")
        self.book = Book.objects.create(name="Policy book", count=10)
        self.url = reverse("reservation_settings")

    def set_hours(self, hours):
        ReservationSettings.objects.update_or_create(pk=1, defaults={"hours": hours})

    def test_default_and_missing_policy_are_48_hours(self):
        self.assertEqual(ReservationSettings.current_hours(), 48)
        ReservationSettings.objects.all().delete()
        self.assertEqual(ReservationSettings.current_hours(), 48)
        held = reserve(self.reader, self.book)
        self.assertEqual(held.expires_at - held.created_at, timedelta(hours=48))

    def test_librarian_saves_boundaries_and_value_survives_a_new_session(self):
        self.client.force_login(self.librarian)
        for hours in (1, 168, 48):
            with self.subTest(hours=hours):
                self.assertEqual(
                    self.client.post(self.url, {"hours": hours}).status_code, 302
                )
                self.assertEqual(ReservationSettings.current_hours(), hours)
                self.assertEqual(ReservationSettings.objects.count(), 1)
                self.assertEqual(
                    str(ReservationSettings.objects.get(pk=1)),
                    f"Reservation duration: {hours} hours",
                )
                other = Client()
                other.force_login(self.librarian)
                self.assertEqual(
                    other.get(self.url).context["form"].initial["hours"], hours
                )

    def test_invalid_values_leave_the_policy_unchanged(self):
        self.client.force_login(self.librarian)
        for value in (0, 169, -1, "1.5", "NaN", "", "abc"):
            with self.subTest(value=value):
                response = self.client.post(self.url, {"hours": value})
                self.assertEqual(response.status_code, 400)
                self.assertIn("hours", response.context["form"].errors)
                self.assertEqual(ReservationSettings.current_hours(), 48)

    def test_readers_and_guests_cannot_read_or_write_settings(self):
        for user, status in ((None, 302), (self.reader, 404)):
            client = Client()
            if user:
                client.force_login(user)
            for method in (client.get, client.post):
                self.assertEqual(method(self.url, {"hours": 1}).status_code, status)
            self.assertEqual(ReservationSettings.current_hours(), 48)
        self.client.force_login(self.reader)
        self.assertNotContains(self.client.get(reverse("home")), self.url)

    def test_administrator_can_manage_settings(self):
        self.client.force_login(account("policy-admin@example.com", ROLE_ADMINISTRATOR))
        self.assertEqual(self.client.post(self.url, {"hours": 24}).status_code, 302)
        self.assertEqual(ReservationSettings.current_hours(), 24)

    def test_csrf_is_required_and_valid_token_works(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.librarian)
        self.assertEqual(client.post(self.url, {"hours": 1}).status_code, 403)
        client.get(self.url)
        token = client.cookies["csrftoken"].value
        self.assertEqual(
            client.post(
                self.url, {"hours": 1, "csrfmiddlewaretoken": token}
            ).status_code,
            302,
        )
        self.assertEqual(ReservationSettings.current_hours(), 1)

    def test_database_enforces_range_and_singleton(self):
        for hours in (0, 169):
            with self.subTest(hours=hours):
                policy = ReservationSettings(pk=1, hours=hours)
                with self.assertRaises(ValidationError):
                    policy.full_clean()
                with self.assertRaises(IntegrityError), transaction.atomic():
                    ReservationSettings.objects.update_or_create(
                        pk=1, defaults={"hours": hours}
                    )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReservationSettings.objects.create(pk=2, hours=48)

    def test_web_and_api_use_same_policy_and_keep_old_deadlines(self):
        now = timezone.now()
        self.client.force_login(self.reader)
        api = APIClient()
        api.force_authenticate(self.reader)
        for hours in (1, 168):
            self.set_hours(hours)
            for channel in ("web", "api"):
                book = Book.objects.create(name=f"{channel} {hours}", count=2)
                # Separate readers keep the independent maximum-three-holds rule intact.
                reader = account(f"{channel}-{hours}@example.com")
                self.client.force_login(reader)
                api.force_authenticate(reader)
                with patch("order.services.timezone.now", return_value=now):
                    if channel == "web":
                        response = self.client.post(reverse("reserve", args=[book.pk]))
                        self.assertEqual(response.status_code, 302)
                    else:
                        response = api.post(
                            "/api/v1/reservation/", {"book": book.pk}, format="json"
                        )
                        self.assertEqual(response.status_code, 201)
                held = Reservation.objects.get(user=reader, book=book)
                self.assertEqual(held.expires_at, now + timedelta(hours=hours))
        original = list(Reservation.objects.values_list("pk", "expires_at"))
        self.set_hours(24)
        self.assertEqual(
            list(Reservation.objects.values_list("pk", "expires_at")), original
        )
        held = Reservation.objects.first()
        held.save()
        held.refresh_from_db()
        self.assertEqual(held.expires_at, dict(original)[held.pk])

    def test_reader_button_shows_current_policy(self):
        self.set_hours(1)
        self.client.force_login(self.reader)
        self.assertContains(
            self.client.get(reverse("book_detail", args=[self.book.pk])),
            "Reserve for 1 Hour",
        )
        self.set_hours(168)
        self.assertContains(
            self.client.get(reverse("book_detail", args=[self.book.pk])),
            "Reserve for 168 Hours",
        )

    def test_elapsed_hours_across_daylight_saving_and_stock_uses_recorded_deadline(
        self,
    ):
        self.set_hours(48)
        now = datetime(2026, 10, 24, 12, tzinfo=ZoneInfo("Europe/Kyiv"))
        self.book.count = 1
        self.book.save()
        held = reserve(self.reader, self.book, now=now)
        expected = now.astimezone(UTC) + timedelta(hours=48)
        self.assertEqual(held.expires_at, expected)
        self.set_hours(1)
        before = Book.objects.with_availability(expected - timedelta(seconds=1)).get(
            pk=self.book.pk
        )
        after = Book.objects.with_availability(expected).get(pk=self.book.pk)
        self.assertEqual(before.available_count, 0)
        self.assertEqual(after.available_count, 1)

    def test_api_cannot_override_duration_or_deadline(self):
        self.set_hours(24)
        api = APIClient()
        api.force_authenticate(self.reader)
        response = api.post(
            "/api/v1/reservation/",
            {
                "book": self.book.pk,
                "hours": 168,
                "expires_at": "2099-01-01T00:00:00Z",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        held = Reservation.objects.get(user=self.reader, book=self.book)
        self.assertEqual(held.expires_at - held.created_at, timedelta(hours=24))
        self.assertEqual(ReservationSettings.current_hours(), 24)
