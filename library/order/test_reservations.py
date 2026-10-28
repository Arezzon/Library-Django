"""The reservation: its deadline, states, constraints and guards (data-model.md §1)."""

from datetime import UTC, datetime, timedelta

from django.db import IntegrityError, connection, transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from authentication.models import ROLE_LIBRARIAN, CustomUser
from book.models import Book
from book.testing import FakeEncoderMixin

from .models import (
    RESERVATION_HOURS,
    Order,
    Reservation,
    ReservationState,
    ReservationStateError,
)

ACTIVE = ReservationState.ACTIVE
ISSUED = ReservationState.ISSUED
CANCELLED = ReservationState.CANCELLED
EXPIRED = ReservationState.EXPIRED
FORTY_EIGHT_HOURS = timedelta(hours=48)


def account(email, role=0):
    return CustomUser.objects.create_user(
        email=email,
        password="test-password",
        first_name="Test",
        middle_name="",
        last_name="Reader",
        is_active=True,
        role=role,
    )


def unsaved(state=ACTIVE):
    """A reservation in memory, for the rules that need no database."""
    created_at = timezone.now()
    return Reservation(
        state=state, created_at=created_at, expires_at=created_at + FORTY_EIGHT_HOURS
    )


class ReservationTestCase(FakeEncoderMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reader = account("reservation-reader@example.com")
        cls.book = Book.objects.create(name="Reserved book", count=2)

    def reserve(self, **fields):
        fields.setdefault("user", self.reader)
        fields.setdefault("book", self.book)
        return Reservation.objects.create(**fields)

    def lend(self):
        return Order.objects.create(
            user=self.reader,
            book=self.book,
            plated_end_at=timezone.now() + timedelta(days=14),
        )


class DeadlineTests(ReservationTestCase):
    def test_a_reservation_is_active_for_exactly_48_hours(self):
        reservation = self.reserve()
        reservation.refresh_from_db()
        self.assertEqual(RESERVATION_HOURS, 48)
        self.assertEqual(reservation.state, ACTIVE)
        self.assertEqual(
            reservation.expires_at - reservation.created_at, FORTY_EIGHT_HOURS
        )

    def test_the_deadline_is_set_on_creation_whatever_is_given(self):
        created_at = timezone.now()
        reservation = self.reserve(
            created_at=created_at, expires_at=created_at + timedelta(hours=1)
        )
        self.assertEqual(reservation.expires_at, created_at + FORTY_EIGHT_HOURS)

    def test_the_database_refuses_any_other_deadline(self):
        reservation = self.reserve()
        stored = Reservation.objects.filter(pk=reservation.pk)
        for hours in (0, 47, 49):
            deadline = reservation.created_at + timedelta(hours=hours)
            with self.subTest(hours=hours):
                with (
                    self.assertRaisesMessage(
                        IntegrityError, "reservation_lasts_48_hours"
                    ),
                    transaction.atomic(),
                ):
                    stored.update(expires_at=deadline)
        # save() sets the deadline once, on creation, and never moves it later.
        reservation.expires_at += timedelta(seconds=1)
        with (
            self.assertRaisesMessage(IntegrityError, "reservation_lasts_48_hours"),
            transaction.atomic(),
        ):
            reservation.save()
        reservation.refresh_from_db()
        self.assertEqual(
            reservation.expires_at - reservation.created_at, FORTY_EIGHT_HOURS
        )

    def test_the_deadline_check_holds_in_any_session_time_zone(self):
        """A restore into a server set to another zone keeps the reservations that
        span a change of summer time: Europe/Berlin leaves it on 25 October 2026."""
        created_at = datetime(2026, 10, 24, 10, tzinfo=UTC)
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL TIME ZONE 'Europe/Berlin'")
            reservation = self.reserve(created_at=created_at)
        self.assertEqual(reservation.expires_at, datetime(2026, 10, 26, 10, tzinfo=UTC))


class StateTests(SimpleTestCase):
    def test_before_the_deadline_an_active_reservation_is_issued_or_cancelled(self):
        for state in (ISSUED, CANCELLED):
            with self.subTest(state=state):
                reservation = unsaved()
                now = reservation.expires_at - timedelta(microseconds=1)
                reservation.change_state(state, now)
                self.assertEqual(reservation.state, state)

    def test_before_the_deadline_an_active_reservation_cannot_expire(self):
        reservation = unsaved()
        with self.assertRaises(ReservationStateError):
            reservation.change_state(
                EXPIRED, reservation.expires_at - timedelta(microseconds=1)
            )
        self.assertEqual(reservation.state, ACTIVE)

    def test_from_the_deadline_an_active_reservation_can_only_expire(self):
        for late in (timedelta(0), timedelta(days=1)):
            with self.subTest(late=late):
                reservation = unsaved()
                now = reservation.expires_at + late
                for state in (ACTIVE, ISSUED, CANCELLED):
                    with self.assertRaises(ReservationStateError):
                        reservation.change_state(state, now)
                    self.assertEqual(reservation.state, ACTIVE)
                reservation.change_state(EXPIRED, now)
                self.assertEqual(reservation.state, EXPIRED)

    def test_issued_cancelled_and_expired_are_final(self):
        for final in (ISSUED, CANCELLED, EXPIRED):
            reservation = unsaved(final)
            for late in (timedelta(days=-1), timedelta(days=1)):
                for state in ReservationState.values:
                    with self.subTest(final=final, late=late, state=state):
                        with self.assertRaises(ReservationStateError):
                            reservation.change_state(
                                state, reservation.expires_at + late
                            )
                        self.assertEqual(reservation.state, final)

    def test_the_effective_state_is_expired_from_the_deadline(self):
        reservation = unsaved()
        deadline = reservation.expires_at
        self.assertEqual(
            reservation.effective_state(deadline - timedelta(microseconds=1)), ACTIVE
        )
        self.assertEqual(reservation.effective_state(deadline), EXPIRED)
        self.assertEqual(
            reservation.effective_state(deadline + timedelta(days=1)), EXPIRED
        )
        for final in (ISSUED, CANCELLED, EXPIRED):
            reservation = unsaved(final)
            for now in (deadline - timedelta(days=1), deadline + timedelta(days=1)):
                with self.subTest(final=final, now=now):
                    self.assertEqual(reservation.effective_state(now), final)


class ConstraintTests(ReservationTestCase):
    def test_a_reader_holds_one_active_reservation_of_a_book(self):
        first = self.reserve()
        with (
            self.assertRaisesMessage(
                IntegrityError, "one_active_reservation_per_reader_and_book"
            ),
            transaction.atomic(),
        ):
            self.reserve()
        self.reserve(user=account("second-reader@example.com"))
        now = timezone.now()
        first.change_state(CANCELLED, now)
        first.cancelled_at = now
        first.save()
        self.reserve()
        self.assertEqual(Reservation.objects.filter(user=self.reader).count(), 2)

    def test_a_cancelled_reservation_records_when(self):
        reservation = self.reserve()
        reservation.state = CANCELLED
        with (
            self.assertRaisesMessage(IntegrityError, "cancelled_reservation_has_time"),
            transaction.atomic(),
        ):
            reservation.save()
        reservation.cancelled_at = timezone.now()
        reservation.save()
        reservation.refresh_from_db()
        self.assertEqual(reservation.state, CANCELLED)


class BulkWriteTests(ReservationTestCase):
    def test_bulk_writes_of_the_state_the_loan_and_the_cancellation_are_refused(self):
        reservation = self.reserve()
        loan = self.lend()
        librarian = account("guard-librarian@example.com", ROLE_LIBRARIAN)
        stored = Reservation.objects.filter(pk=reservation.pk)
        now = timezone.now()
        changes = (
            {"state": CANCELLED},
            {"loan": loan},
            {"loan_id": loan.pk},
            {"cancelled_by": librarian},
            {"cancelled_by_id": librarian.pk},
            {"cancelled_at": now},
            {"cancel_reason": "Damaged copy"},
            {"cancellation_seen_at": now},
        )
        # Refused before Django opens a transaction of its own, so the caller's
        # transaction stays usable.
        with transaction.atomic():
            for change in changes:
                with self.subTest(change=list(change)), self.assertRaises(ValueError):
                    stored.update(**change)
            for change in changes:
                fields = list(change)
                with self.subTest(fields=fields), self.assertRaises(ValueError):
                    Reservation.objects.bulk_update([reservation], fields)
            with self.assertRaises(ValueError):
                Reservation.objects.bulk_create(
                    [Reservation(user=librarian, book=self.book)]
                )
            moved = now - timedelta(hours=1)
            self.assertEqual(
                stored.update(created_at=moved, expires_at=moved + FORTY_EIGHT_HOURS),
                1,
            )
            reservation.created_at = now
            reservation.expires_at = now + FORTY_EIGHT_HOURS
            self.assertEqual(
                Reservation.objects.bulk_update(
                    [reservation], ["created_at", "expires_at"]
                ),
                1,
            )
        reservation.refresh_from_db()
        self.assertEqual(
            (
                reservation.state,
                reservation.loan,
                reservation.cancelled_by,
                reservation.cancelled_at,
                reservation.cancel_reason,
                reservation.cancellation_seen_at,
                reservation.created_at,
            ),
            (ACTIVE, None, None, None, "", None, now),
        )
        self.assertEqual(Reservation.objects.count(), 1)


class DeletionTests(ReservationTestCase):
    def test_deleting_the_loan_keeps_the_issued_reservation(self):
        loan = self.lend()
        reservation = self.reserve()
        reservation.change_state(ISSUED, timezone.now())
        reservation.loan = loan
        reservation.save()
        loan.delete()
        reservation.refresh_from_db()
        self.assertEqual((reservation.state, reservation.loan), (ISSUED, None))

    def test_deleting_the_canceller_keeps_the_cancellation(self):
        librarian = account("canceller@example.com", ROLE_LIBRARIAN)
        reservation = self.reserve()
        now = timezone.now()
        reservation.change_state(CANCELLED, now)
        reservation.cancelled_by = librarian
        reservation.cancelled_at = now
        reservation.cancel_reason = "Damaged copy"
        reservation.save()
        librarian.delete()
        reservation.refresh_from_db()
        self.assertEqual(
            (reservation.state, reservation.cancelled_by, reservation.cancel_reason),
            (CANCELLED, None, "Damaged copy"),
        )

    def test_deleting_the_reader_deletes_their_reservations(self):
        leaving = account("leaving-reader@example.com")
        reservation = self.reserve(user=leaving)
        kept = self.reserve()
        leaving.delete()
        self.assertFalse(Reservation.objects.filter(pk=reservation.pk).exists())
        self.assertTrue(Reservation.objects.filter(pk=kept.pk).exists())


class ReservationAdminTests(ReservationTestCase):
    """Librarians read reservations in the admin site; nobody changes them there."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.librarian = account("admin-librarian@example.com", ROLE_LIBRARIAN)

    def test_librarians_read_each_reservation_with_its_current_state(self):
        current = self.reserve()
        lapsed = self.reserve(
            user=account("lapsed-reader@example.com"),
            created_at=timezone.now() - timedelta(hours=RESERVATION_HOURS + 1),
        )
        self.client.force_login(self.librarian)
        listing = self.client.get("/admin/order/reservation/")
        self.assertContains(listing, "reservation-reader@example.com")
        self.assertContains(listing, "lapsed-reader@example.com")
        for reservation, state in ((current, "Active"), (lapsed, "Expired")):
            with self.subTest(state=state):
                page = self.client.get(
                    f"/admin/order/reservation/{reservation.pk}/change/"
                )
                self.assertContains(page, state)
                self.assertContains(page, reservation.book.name)
                for label in ("Reader", "Book", "State", "Created at", "Expires at"):
                    self.assertContains(page, f"{label}:")

    def test_nobody_adds_changes_or_deletes_a_reservation_there(self):
        reservation = self.reserve()
        url = f"/admin/order/reservation/{reservation.pk}"
        self.client.force_login(self.librarian)
        attempts = [
            ("add", self.client.get, "/admin/order/reservation/add/", {}),
            ("change", self.client.post, f"{url}/change/", {"state": CANCELLED}),
            ("delete page", self.client.get, f"{url}/delete/", {}),
            ("deletion", self.client.post, f"{url}/delete/", {"post": "yes"}),
        ]
        for attempt, send, path, data in attempts:
            with self.subTest(attempt=attempt):
                self.assertEqual(send(path, data).status_code, 403)
        listing = self.client.get("/admin/order/reservation/")
        self.assertNotContains(listing, "delete_selected")
        reservation.refresh_from_db()
        self.assertEqual(reservation.state, ACTIVE)

    def test_readers_are_sent_to_the_admin_sign_in(self):
        self.client.force_login(self.reader)
        response = self.client.get("/admin/order/reservation/")
        self.assertRedirects(
            response,
            "/admin/login/?next=/admin/order/reservation/",
            fetch_redirect_response=False,
        )
