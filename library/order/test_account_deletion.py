"""Deleting an account keeps the library's loans and reservations (KAN-82).

The records stay with their dates, book and state; only the link to the person goes.
Pages and the API show such a reader as "Deleted reader" and nobody's name or email.
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditEntry
from authentication.models import (
    ROLE_ADMINISTRATOR,
    ROLE_LIBRARIAN,
    CustomUser,
)
from book.models import Book
from book.testing import FakeEncoderMixin

from . import services
from .models import DELETED_READER, Order, Reservation, ReservationState
from .services import ReservationRefused

ACTIVE = ReservationState.ACTIVE
CANCELLED = ReservationState.CANCELLED


def account(email, role=0):
    return CustomUser.objects.create_user(
        email=email,
        password="test-password",
        first_name="Leaving",
        middle_name="",
        last_name="Person",
        is_active=True,
        role=role,
    )


class DeletedReaderTestCase(FakeEncoderMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.librarian = account("desk-librarian@example.com", ROLE_LIBRARIAN)
        cls.administrator = account("site-admin@example.com", ROLE_ADMINISTRATOR)
        cls.book = Book.objects.create(name="Kept book", count=2)

    def setUp(self):
        self.reader = account("leaving-reader@example.com")

    def open_loan(self, reader=None, book=None, **fields):
        fields.setdefault("plated_end_at", timezone.now() + timedelta(days=14))
        return Order.objects.create(
            user=reader or self.reader, book=book or self.book, **fields
        )

    def reserve(self, reader=None, book=None):
        return Reservation.objects.create(
            user=reader or self.reader, book=book or self.book
        )

    def available(self, book=None):
        book = book or self.book
        return Book.objects.with_availability(timezone.now()).get(pk=book.pk)

    def signed_in(self, user):
        self.client.force_login(user)
        return self.client


class DeletionChannelTests(DeletedReaderTestCase):
    """Every way of deleting the account keeps its loans and reservations."""

    def delete_by_model(self, reader):
        reader.delete()

    def delete_by_id(self, reader):
        self.assertTrue(CustomUser.delete_by_id(reader.pk))

    def delete_by_api(self, reader):
        client = APIClient()
        client.force_authenticate(self.librarian)
        response = client.delete(f"/api/v1/user/{reader.pk}/")
        self.assertEqual(response.status_code, 204)

    def delete_in_admin(self, reader):
        url = reverse("admin:authentication_customuser_delete", args=[reader.pk])
        response = self.signed_in(self.administrator).post(url, {"post": "yes"})
        self.assertEqual(response.status_code, 302)

    def delete_in_bulk_in_admin(self, reader):
        response = self.signed_in(self.administrator).post(
            reverse("admin:authentication_customuser_changelist"),
            {
                "action": "delete_selected",
                "_selected_action": [reader.pk],
                "post": "yes",
            },
        )
        self.assertEqual(response.status_code, 302)

    def test_every_channel_keeps_the_records_without_the_reader(self):
        channels = {
            "model": self.delete_by_model,
            "delete_by_id": self.delete_by_id,
            "api": self.delete_by_api,
            "admin": self.delete_in_admin,
            "admin_bulk": self.delete_in_bulk_in_admin,
        }
        for channel, delete in channels.items():
            with self.subTest(channel=channel):
                reader = account(f"{channel}-reader@example.com")
                returned = self.open_loan(reader, end_at=timezone.now())
                held = self.reserve(reader)
                before = (Order.objects.count(), Reservation.objects.count())
                delete(reader)
                self.assertFalse(CustomUser.objects.filter(pk=reader.pk).exists())
                self.assertEqual(
                    (Order.objects.count(), Reservation.objects.count()), before
                )
                returned.refresh_from_db()
                held.refresh_from_db()
                self.assertIsNone(returned.user_id)
                self.assertIsNone(held.user_id)
                self.assertIsNotNone(returned.end_at)
                self.assertEqual((held.state, held.book_id), (ACTIVE, self.book.pk))

    def test_deleting_the_reader_records_no_loan_deletion(self):
        loan = self.open_loan()
        self.reader.delete()
        self.assertFalse(
            AuditEntry.objects.filter(action="loan_deleted", target_id=loan.pk).exists()
        )

    def test_a_book_whose_reader_was_deleted_still_cannot_be_deleted(self):
        book = Book.objects.create(name="Borrowed once", count=1)
        self.open_loan(book=book, end_at=timezone.now())
        self.reader.delete()
        response = self.signed_in(self.librarian).post(
            reverse("book_delete", args=[book.pk])
        )
        self.assertIn(response.status_code, (302, 409))
        self.assertTrue(Book.objects.filter(pk=book.pk).exists())


class OpenLoanTests(DeletedReaderTestCase):
    """A deleted reader's unreturned book stays out until a librarian closes the
    loan."""

    def test_the_open_loan_keeps_its_copy(self):
        loan = self.open_loan()
        available = self.available().available_count
        self.reader.delete()
        loan.refresh_from_db()
        self.assertIsNone(loan.end_at)
        self.assertEqual(self.available().available_count, available)

    def test_a_librarian_closes_it_and_the_audit_records_it(self):
        loan = self.open_loan()
        available = self.available().available_count
        self.reader.delete()
        client = self.signed_in(self.librarian)
        page = client.get(reverse("order_close", args=[loan.pk]))
        self.assertContains(page, DELETED_READER)
        response = client.post(reverse("order_close", args=[loan.pk]))
        self.assertEqual(response.status_code, 302)
        loan.refresh_from_db()
        self.assertIsNotNone(loan.end_at)
        self.assertEqual(self.available().available_count, available + 1)
        entry = AuditEntry.objects.get(action="loan_returned", target_id=loan.pk)
        self.assertIn(DELETED_READER, entry.target_label)
        self.assertNotIn("Leaving", entry.target_label)

    def test_a_librarian_changes_it_on_the_loan_page(self):
        loan = self.open_loan()
        self.reader.delete()
        client = self.signed_in(self.librarian)
        url = reverse("order_update", args=[loan.pk])
        self.assertContains(client.get(url), DELETED_READER)
        due = timezone.localtime(loan.plated_end_at + timedelta(days=7))
        response = client.post(
            url, {"plated_end_at": due.strftime("%Y-%m-%dT%H:%M"), "end_at": ""}
        )
        self.assertEqual(response.status_code, 302)
        loan.refresh_from_db()
        self.assertEqual(timezone.localtime(loan.plated_end_at).date(), due.date())
        self.assertIsNone(loan.user_id)

    def test_a_librarian_closes_it_in_the_admin(self):
        loan = self.open_loan()
        self.reader.delete()
        client = self.signed_in(self.administrator)
        url = reverse("admin:order_order_change", args=[loan.pk])
        self.assertEqual(client.get(url).status_code, 200)
        now = timezone.localtime()
        due = timezone.localtime(loan.plated_end_at)
        response = client.post(
            url,
            {
                "book": self.book.pk,
                "plated_end_at_0": due.strftime("%Y-%m-%d"),
                "plated_end_at_1": due.strftime("%H:%M:%S"),
                "end_at_0": now.strftime("%Y-%m-%d"),
                "end_at_1": now.strftime("%H:%M:%S"),
            },
        )
        self.assertEqual(response.status_code, 302)
        loan.refresh_from_db()
        self.assertIsNotNone(loan.end_at)
        self.assertIsNone(loan.user_id)

    def test_the_book_admin_page_still_saves(self):
        loan = self.open_loan()
        self.reader.delete()
        client = self.signed_in(self.administrator)
        url = reverse("admin:book_book_change", args=[self.book.pk])
        page = client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "leaving-reader@example.com")
        loan.refresh_from_db()
        self.assertIsNone(loan.user_id)

    def test_a_loan_cannot_be_started_or_left_without_a_reader(self):
        with self.assertRaises(ValueError):
            Order.objects.create(
                user=None,
                book=self.book,
                plated_end_at=timezone.now() + timedelta(days=14),
            )
        loan = self.open_loan()
        loan.user = None
        with self.assertRaises(ValueError):
            loan.save()
        with self.assertRaises(ValueError):
            Reservation.objects.create(user=None, book=self.book)


class PageTests(DeletedReaderTestCase):
    """Pages show "Deleted reader" where the reader's name and email were."""

    def test_the_loan_list_shows_a_deleted_reader(self):
        self.open_loan()
        self.reader.delete()
        page = self.signed_in(self.librarian).get(reverse("order_all"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, DELETED_READER)
        self.assertNotContains(page, "leaving-reader@example.com")

    def test_the_desk_lists_the_reservation_with_a_deleted_reader(self):
        self.reserve()
        self.reader.delete()
        page = self.signed_in(self.librarian).get(reverse("reservation_desk"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, DELETED_READER)
        self.assertNotContains(page, "leaving-reader@example.com")

    def test_the_reservation_of_a_deleted_reader_is_not_issued(self):
        held = self.reserve()
        self.reader.delete()
        held.refresh_from_db()
        client = self.signed_in(self.librarian)
        url = reverse("reservation_issue", args=[held.pk])
        page = client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, DELETED_READER)
        self.assertEqual(page.context["refusal"].code, "reader_deleted")
        response = client.post(url, {"days": 14})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["refusal"].code, "reader_deleted")
        with self.assertRaises(ReservationRefused) as refused:
            services.issue(self.librarian, held, 14)
        self.assertEqual(refused.exception.code, "reader_deleted")
        held.refresh_from_db()
        self.assertEqual(held.state, ACTIVE)
        self.assertFalse(Order.objects.filter(user__isnull=True).exists())

    def test_a_librarian_cancels_it_to_free_the_copy(self):
        held = self.reserve()
        available = self.available().available_count
        self.reader.delete()
        client = self.signed_in(self.librarian)
        url = reverse("reservation_cancel", args=[held.pk])
        page = client.get(url)
        self.assertContains(page, DELETED_READER)
        response = client.post(url, {"reason": "Account closed", "confirm": "yes"})
        self.assertEqual(response.status_code, 302)
        held.refresh_from_db()
        self.assertEqual(held.state, CANCELLED)
        self.assertFalse(held.cancelled_by_reader)
        self.assertEqual(self.available().available_count, available + 1)
        entry = AuditEntry.objects.get(
            action="reservation_cancelled", target_id=held.pk
        )
        self.assertIn(DELETED_READER, entry.target_label)

    def test_a_held_reservation_expires_with_a_system_entry(self):
        held = self.reserve()
        self.reader.delete()
        later = held.expires_at + timedelta(minutes=1)
        self.assertEqual(services.expire_due(later), 1)
        entry = AuditEntry.objects.get(action="reservation_expired", target_id=held.pk)
        self.assertIn(DELETED_READER, entry.target_label)

    def test_texts_name_no_one(self):
        loan = self.open_loan()
        held = self.reserve()
        self.reader.delete()
        loan.refresh_from_db()
        held.refresh_from_db()
        for text in (str(loan), loan.audit_label(), str(held), held.audit_label()):
            with self.subTest(text=text):
                self.assertIn(DELETED_READER, text)
                self.assertNotIn("Leaving", text)


class ApiTests(DeletedReaderTestCase):
    def api(self, user=None):
        client = APIClient()
        client.force_authenticate(user or self.librarian)
        return client

    def test_the_api_returns_the_records_without_a_reader(self):
        loan = self.open_loan()
        held = self.reserve()
        self.reader.delete()
        client = self.api()
        body = client.get(f"/api/v1/order/{loan.pk}/").json()
        self.assertIsNone(body["user"])
        body = client.get(f"/api/v1/reservation/{held.pk}/").json()
        self.assertIsNone(body["user"])

    def test_the_api_changes_the_loan_and_keeps_it_without_a_reader(self):
        loan = self.open_loan()
        self.reader.delete()
        response = self.api().patch(
            f"/api/v1/order/{loan.pk}/",
            {"end_at": timezone.now().isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        loan.refresh_from_db()
        self.assertIsNotNone(loan.end_at)
        self.assertIsNone(loan.user_id)

    def test_the_api_refuses_a_loan_without_a_reader(self):
        response = self.api().post(
            "/api/v1/order/",
            {
                "user": None,
                "book": self.book.pk,
                "plated_end_at": (timezone.now() + timedelta(days=14)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("user", response.json())
        loan = self.open_loan()
        response = self.api().patch(
            f"/api/v1/order/{loan.pk}/", {"user": None}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        loan.refresh_from_db()
        self.assertEqual(loan.user_id, self.reader.pk)


class CancellationOriginTests(DeletedReaderTestCase):
    """Who cancelled survives the deletion of both accounts."""

    def cancelled(self, actor, reason=""):
        held = self.reserve()
        services.cancel(actor, held, reason)
        held.refresh_from_db()
        return held

    def library_flag(self, held):
        client = APIClient()
        client.force_authenticate(self.librarian)
        return client.get(f"/api/v1/reservation/{held.pk}/").json()[
            "cancelled_by_library"
        ]

    def test_the_readers_own_cancellation_stays_theirs(self):
        held = self.cancelled(self.reader)
        self.assertTrue(held.cancelled_by_reader)
        self.reader.delete()
        held.refresh_from_db()
        self.assertTrue(held.cancelled_by_reader)
        self.assertFalse(self.library_flag(held))
        self.assertIn("You cancelled it", services.next_step(held, timezone.now()))

    def test_the_librarys_cancellation_stays_the_librarys(self):
        librarian = account("gone-librarian@example.com", ROLE_LIBRARIAN)
        held = self.cancelled(librarian, "Damaged copy")
        self.assertFalse(held.cancelled_by_reader)
        librarian.delete()
        self.reader.delete()
        held.refresh_from_db()
        self.assertEqual((held.cancelled_by_id, held.user_id), (None, None))
        self.assertFalse(held.cancelled_by_reader)
        self.assertTrue(self.library_flag(held))
        self.assertEqual(held.cancel_reason, "Damaged copy")
