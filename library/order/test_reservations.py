"""The reservation: its deadline, states, constraints and guards (data-model.md §1)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from functools import partial
from threading import Barrier
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import (
    IntegrityError,
    close_old_connections,
    connection,
    connections,
    transaction,
)
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import dateformat, timezone

from audit.models import AuditEntry
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
from .services import (
    ReservationRefused,
    cancel,
    eligibility,
    issue,
    lend,
    reserve,
)
from .tasks import expire_reservations

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


KYIV = ZoneInfo("Europe/Kyiv")


def in_kyiv(moment, pattern="j M Y, H:i T"):
    """A time as pages show it, worked out independently of the settings."""
    return dateformat.format(moment.astimezone(KYIV), pattern)


class ReservingTests(ReservationTestCase):
    """Story 2 through the web and the API (contracts/reservations-api.md)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.other = account("reserving-other@example.com")
        cls.librarian = account("reserving-librarian@example.com", ROLE_LIBRARIAN)

    def signed_in(self, user=None):
        self.client.force_login(user or self.reader)
        return self.client

    def api_reserve(self, book, user=None):
        return self.signed_in(user).post(
            "/api/v1/reservation/", {"book": book.pk}, content_type="application/json"
        )

    def assertRefused(self, response, code, detail):
        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual((body["code"], body["detail"]), (code, detail))
        return body

    def test_a_reservation_is_active_at_once_and_holds_a_copy_everywhere(self):
        client = self.signed_in()
        response = client.post(reverse("reserve", args=[self.book.pk]), follow=True)
        self.assertEqual(response.redirect_chain, [(reverse("reservation_my"), 302)])
        reservation = Reservation.objects.get(user=self.reader, book=self.book)
        self.assertEqual(reservation.state, ACTIVE)
        self.assertEqual(
            reservation.expires_at - reservation.created_at, FORTY_EIGHT_HOURS
        )
        self.assertContains(
            response,
            "Collect it from a librarian before " + in_kyiv(reservation.expires_at),
        )
        # One of the two copies is held: the book page, the catalog, search, the API.
        page = client.get(reverse("book_detail", args=[self.book.pk]))
        self.assertContains(page, "1 of 2 Available")
        self.assertContains(client.get(reverse("book_list")), "1 of 2 in stock")
        api = client.get(f"/api/v1/book/{self.book.pk}/").json()
        self.assertEqual(api["available_count"], 1)
        found = client.get("/api/v1/books/search/", {"q": "Reserved book"}).json()
        self.assertEqual(
            [book["available_count"] for book in found if book["id"] == self.book.pk],
            [1],
        )
        entry = AuditEntry.objects.get(
            action="reservation_created", target_id=reservation.pk
        )
        self.assertEqual((entry.channel, entry.actor_id), ("web", self.reader.pk))

    def test_the_api_answers_201_with_the_reservation(self):
        response = self.api_reserve(self.book)
        self.assertEqual(response.status_code, 201)
        body = response.json()
        reservation = Reservation.objects.get(pk=body["id"])
        self.assertEqual(
            (body["book"], body["user"], body["state"], body["loan"]),
            (self.book.pk, self.reader.pk, "active", None),
        )
        self.assertEqual(
            body["expires_at"], timezone.localtime(reservation.expires_at).isoformat()
        )
        self.assertRegex(body["expires_at"], r"\+0[23]:00$")
        self.assertNotIn("cancelled_by", body)
        entry = AuditEntry.objects.get(
            action="reservation_created", target_id=reservation.pk
        )
        self.assertEqual(entry.channel, "api")

    def test_no_copy_available(self):
        last = Book.objects.create(name="Last copy", count=1)
        self.assertEqual(self.api_reserve(last, self.other).status_code, 201)
        self.assertRefused(
            self.api_reserve(last),
            "no_copy_available",
            "No copy of “Last copy” is available right now. Try again later or choose "
            "another book.",
        )
        self.assertFalse(Reservation.objects.filter(user=self.reader).exists())

    def test_already_reserved(self):
        self.assertEqual(self.api_reserve(self.book).status_code, 201)
        held = Reservation.objects.get(user=self.reader)
        self.assertRefused(
            self.api_reserve(self.book),
            "already_reserved",
            "You already reserved “Reserved book”. Collect it from a librarian before "
            + in_kyiv(held.expires_at)
            + ".",
        )
        self.assertEqual(Reservation.objects.filter(user=self.reader).count(), 1)

    def test_already_on_loan(self):
        self.lend()
        self.assertRefused(
            self.api_reserve(self.book),
            "already_on_loan",
            "You already have “Reserved book” on loan.",
        )
        self.assertFalse(Reservation.objects.exists())

    def test_reservation_limit_for_a_4th_reservation(self):
        books = [Book.objects.create(name=f"Title {n}", count=1) for n in range(4)]
        for book in books[:3]:
            self.assertEqual(self.api_reserve(book).status_code, 201)
        self.assertRefused(
            self.api_reserve(books[3]),
            "reservation_limit",
            "You already have 3 active reservations, the most allowed. Collect or "
            "cancel one to reserve another book.",
        )
        self.assertEqual(Reservation.objects.filter(user=self.reader).count(), 3)

    def test_overdue_loan_names_the_book_and_its_due_date(self):
        due = timezone.now() - timedelta(seconds=1)
        overdue = Book.objects.create(name="Dune", count=1)
        Order.objects.create(user=self.reader, book=overdue, plated_end_at=due)
        body = self.assertRefused(
            self.api_reserve(self.book),
            "overdue_loan",
            f"“Dune” was due on {in_kyiv(due, 'j M Y')}. Return it before reserving or "
            "borrowing another book.",
        )
        self.assertEqual(
            (body["book"], body["due"]),
            (overdue.pk, timezone.localtime(due).isoformat()),
        )
        self.assertFalse(Reservation.objects.exists())

    def test_a_refusal_on_the_web_returns_to_the_book_page_with_its_message(self):
        self.lend()
        response = self.signed_in().post(
            reverse("reserve", args=[self.book.pk]), follow=True
        )
        self.assertEqual(
            response.redirect_chain,
            [(reverse("book_detail", args=[self.book.pk]), 302)],
        )
        self.assertContains(response, "You already have “Reserved book” on loan.")
        self.assertFalse(Reservation.objects.exists())

    def test_the_book_page_offers_reserving_or_says_why_not(self):
        client = self.signed_in()
        page = client.get(reverse("book_detail", args=[self.book.pk]))
        self.assertContains(page, f'action="{reverse("reserve", args=[self.book.pk])}"')
        self.assertContains(page, 'data-track-event="borrow_intent"', count=1)
        self.lend()
        page = client.get(reverse("book_detail", args=[self.book.pk]))
        self.assertNotContains(page, reverse("reserve", args=[self.book.pk]))
        self.assertContains(page, "You already have “Reserved book” on loan.")

    def test_my_reservations_show_the_state_the_deadline_and_the_next_step(self):
        held = reserve(self.reader, self.book)
        lapsed_book = Book.objects.create(name="Lapsed title", count=1)
        Reservation.objects.create(
            user=self.reader,
            book=lapsed_book,
            created_at=timezone.now() - timedelta(hours=49),
        )
        page = self.signed_in().get(reverse("reservation_my"))
        self.assertContains(page, "Reserved book")
        self.assertContains(page, "Active")
        self.assertContains(page, in_kyiv(held.created_at))
        self.assertContains(page, in_kyiv(held.expires_at))
        self.assertRegex(in_kyiv(held.expires_at), r" EES?T$")
        self.assertContains(page, "Collect it from a librarian before")
        self.assertContains(page, "Lapsed title")
        self.assertContains(page, "Expired")
        self.assertNotContains(
            self.signed_in(self.other).get(reverse("reservation_my")), "Reserved book"
        )

    def test_an_empty_list_says_how_to_reserve(self):
        page = self.signed_in().get(reverse("reservation_my"))
        self.assertContains(page, "You have no reservations.")

    def test_at_48_hours_the_copy_is_free_again_with_no_task_run(self):
        held = reserve(self.reader, self.book)
        client = self.signed_in()
        for moment, available, state in (
            (held.expires_at - timedelta(seconds=1), 1, "active"),
            (held.expires_at, 2, "expired"),
        ):
            with (
                self.subTest(state=state),
                patch("django.utils.timezone.now", return_value=moment),
            ):
                book = client.get(f"/api/v1/book/{self.book.pk}/").json()
                self.assertEqual(book["available_count"], available)
                reservation = client.get(f"/api/v1/reservation/{held.pk}/").json()
                self.assertEqual(reservation["state"], state)
        held.refresh_from_db()
        self.assertEqual(held.state, ACTIVE)

    def test_lending_a_reserved_book_to_its_reader_issues_the_reservation(self):
        last = Book.objects.create(name="Last copy", count=1)
        held = reserve(self.reader, last)
        response = self.signed_in(self.librarian).post(
            reverse("order_lend"),
            {"reader": self.reader.pk, "book": last.pk, "days": 14},
        )
        self.assertRedirects(
            response, reverse("order_all"), fetch_redirect_response=False
        )
        loan = Order.objects.get(user=self.reader, book=last)
        held.refresh_from_db()
        self.assertEqual((held.state, held.loan), (ISSUED, loan))
        self.assertEqual(Book.objects.get(pk=last.pk).available_count, 0)
        entry = AuditEntry.objects.get(action="reservation_issued", target_id=held.pk)
        self.assertEqual(entry.after, {"state": "issued", "loan": loan.pk})

    def test_a_reservation_on_the_last_copy_blocks_another_readers_loan(self):
        last = Book.objects.create(name="Last copy", count=1)
        reserve(self.other, last)
        with self.assertRaises(ReservationRefused) as refused:
            lend(self.librarian, self.reader, last, 14)
        self.assertEqual(refused.exception.code, "no_copy_available")
        self.assertFalse(Order.objects.filter(book=last).exists())

    def test_reserving_works_while_the_event_broker_is_unavailable(self):
        from kombu.exceptions import OperationalError as BrokerError

        with (
            patch(
                "events.services.persist_event.apply_async",
                side_effect=BrokerError("broker down"),
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.signed_in().post(reverse("reserve", args=[self.book.pk]))
        self.assertRedirects(
            response, reverse("reservation_my"), fetch_redirect_response=False
        )
        self.assertTrue(Reservation.objects.filter(user=self.reader).exists())

    def past_reservations(self):
        """One reservation in each state, each of a book of its own."""
        now = timezone.now()
        books = [Book.objects.create(name=f"Past {n}", count=1) for n in range(4)]
        current = reserve(self.reader, books[0])
        lapsed = self.reserve(book=books[1], created_at=now - timedelta(hours=49))
        issued = self.reserve(book=books[2], state=ISSUED)
        cancelled = self.reserve(
            book=books[3],
            state=CANCELLED,
            cancelled_at=now,
            cancel_reason="Copy damaged",
        )
        return current, lapsed, issued, cancelled

    def test_the_state_filter_reads_the_effective_state(self):
        current, lapsed, issued, cancelled = self.past_reservations()
        client = self.signed_in()
        ids = [row["id"] for row in client.get("/api/v1/reservation/").json()]
        self.assertEqual(ids[0], current.pk)
        self.assertCountEqual(ids, [current.pk, lapsed.pk, issued.pk, cancelled.pk])
        for state, expected in (
            ("active", current),
            ("expired", lapsed),
            ("issued", issued),
            ("cancelled", cancelled),
        ):
            with self.subTest(state=state):
                rows = client.get("/api/v1/reservation/", {"state": state}).json()
                self.assertEqual([row["id"] for row in rows], [expected.pk])
                self.assertEqual(rows[0]["state"], state)
        refused = client.get("/api/v1/reservation/", {"state": "held"})
        self.assertEqual(refused.status_code, 400)
        self.assertIn("state", refused.json())

    def test_my_reservations_say_what_comes_next_in_each_state(self):
        self.past_reservations()
        page = self.signed_in().get(reverse("reservation_my"))
        for text in (
            "Collect it from a librarian before",
            "The 48 hours ended. Reserve it again if a copy is available.",
            "Collected.",
            "The library cancelled it on",
            "Reason: Copy damaged",
        ):
            with self.subTest(text=text):
                self.assertContains(page, text)

    def test_a_held_copy_whose_total_was_lowered_away_is_not_lent(self):
        last = Book.objects.create(name="Lost copy", count=1)
        held = reserve(self.reader, last)
        last.count = 0
        last.save()
        refusal = (
            "No copy of “Lost copy” is available. A reservation may be holding the last "
            "one."
        )
        client = self.signed_in(self.librarian)
        # The issue page comes back with the refusal.
        response = client.post(
            reverse("reservation_issue", args=[held.pk]), {"days": 14}
        )
        self.assertContains(response, refusal)
        response = client.post(
            reverse("order_lend"),
            {"reader": self.reader.pk, "book": last.pk, "days": 14},
        )
        self.assertContains(response, refusal)
        held.refresh_from_db()
        self.assertEqual((held.state, held.loan), (ACTIVE, None))
        self.assertFalse(Order.objects.filter(book=last).exists())

    def test_the_schema_documents_the_reservation_api(self):
        paths = self.client.get("/api/schema/?format=json").json()["paths"]
        one = paths["/api/v1/reservation/{id}/"]["get"]["parameters"]
        self.assertEqual(
            [p["schema"]["type"] for p in one if p["in"] == "path"], ["integer"]
        )
        listing = paths["/api/v1/reservation/"]["get"]["parameters"]
        self.assertIn("state", [p["name"] for p in listing])
        create = paths["/api/v1/reservation/"]["post"]["responses"]
        self.assertIn("409", create)

    def test_eligibility_tells_the_page_why_without_locking(self):
        self.assertIsNone(eligibility(self.reader, self.book, timezone.now()))
        self.lend()
        refusal = eligibility(self.reader, self.book, timezone.now())
        self.assertEqual(refusal.code, "already_on_loan")


class ScheduledExpiryTests(ReservationTestCase):
    def test_the_scheduled_expiry_records_each_due_reservation(self):
        due = self.reserve(created_at=timezone.now() - timedelta(hours=49))
        current = self.reserve(user=account("current-reader@example.com"))
        with self.assertLogs("order.tasks", "INFO") as logs:
            self.assertEqual(expire_reservations(), 1)
        due.refresh_from_db()
        current.refresh_from_db()
        self.assertEqual((due.state, current.state), (EXPIRED, ACTIVE))
        entry = AuditEntry.objects.get(action="reservation_expired", target_id=due.pk)
        self.assertEqual(
            (entry.channel, entry.actor_id, entry.occurred_at),
            ("system", None, due.expires_at),
        )
        self.assertEqual(
            (entry.before, entry.after), ({"state": "active"}, {"state": "expired"})
        )
        self.assertIn("Expired 1 reservation", logs.output[0])
        self.assertEqual(expire_reservations(), 0)

    def test_reserving_expires_the_readers_due_reservations_first(self):
        books = [Book.objects.create(name=f"Due {n}", count=1) for n in range(3)]
        for book in books:
            self.reserve(book=book, created_at=timezone.now() - timedelta(hours=49))
        reserve(self.reader, self.book)
        self.assertEqual(
            Reservation.objects.filter(user=self.reader, state=EXPIRED).count(), 3
        )

    def test_the_schedule_runs_the_expiry_every_5_minutes(self):
        schedule = settings.CELERY_BEAT_SCHEDULE["expire-reservations"]
        self.assertEqual(
            (schedule["task"], schedule["schedule"]),
            ("order.tasks.expire_reservations", 300),
        )
        self.assertEqual(settings.TIME_ZONE, "Europe/Kyiv")


class DeskTests(ReservationTestCase):
    """Story 3: librarians issue, lend and cancel with a reason; readers cancel their
    own reservations (contracts/reservations-api.md, PR 6)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.other = account("desk-other@example.com")
        cls.librarian = account("desk-librarian@example.com", ROLE_LIBRARIAN)

    def signed_in(self, user):
        self.client.force_login(user)
        return self.client

    def api(self, user, path, body=None):
        return self.signed_in(user).post(
            path, body or {}, content_type="application/json"
        )

    def overdue(self):
        """A loan of the reader's that was due yesterday."""
        return Order.objects.create(
            user=self.reader,
            book=Book.objects.create(name="Overdue book", count=1),
            plated_end_at=timezone.now() - timedelta(days=1),
        )

    def available(self, book=None):
        return Book.objects.get(pk=(book or self.book).pk).available_count

    def test_issuing_starts_one_loan_for_the_chosen_period(self):
        held = reserve(self.reader, self.book)
        self.assertEqual(self.available(), 1)
        client = self.signed_in(self.librarian)
        url = reverse("reservation_issue", args=[held.pk])
        page = client.get(url)
        self.assertContains(page, 'value="14"')
        self.assertContains(page, "reservation-reader@example.com")
        before = timezone.now()
        response = client.post(url, {"days": 7})
        self.assertRedirects(
            response, reverse("reservation_desk"), fetch_redirect_response=False
        )
        held.refresh_from_db()
        loan = Order.objects.get(book=self.book)
        self.assertEqual(
            (held.state, held.loan, loan.user), (ISSUED, loan, self.reader)
        )
        self.assertGreaterEqual(loan.plated_end_at, before + timedelta(days=7))
        self.assertLessEqual(loan.plated_end_at, timezone.now() + timedelta(days=7))
        self.assertEqual(self.available(), 1)
        entry = AuditEntry.objects.get(action="reservation_issued", target_id=held.pk)
        self.assertEqual(
            (entry.actor_id, entry.after),
            (self.librarian.pk, {"state": "issued", "loan": loan.pk}),
        )

    def test_the_api_issues_for_14_days_unless_told_otherwise(self):
        held = reserve(self.reader, self.book)
        path = f"/api/v1/reservation/{held.pk}/issue/"
        for days in (0, 31, "soon"):
            with self.subTest(days=days):
                response = self.api(self.librarian, path, {"days": days})
                self.assertEqual(response.status_code, 400)
                self.assertIn("days", response.json())
        before = timezone.now()
        response = self.api(self.librarian, path)
        self.assertEqual(response.status_code, 201)
        body = response.json()
        loan = Order.objects.get(book=self.book)
        self.assertEqual(
            (body["reservation"]["state"], body["reservation"]["loan"]),
            ("issued", loan.pk),
        )
        self.assertEqual(
            (body["loan"]["id"], body["loan"]["user"]), (loan.pk, self.reader.pk)
        )
        self.assertGreaterEqual(loan.plated_end_at, before + timedelta(days=14))
        self.assertLessEqual(loan.plated_end_at, timezone.now() + timedelta(days=14))

    def test_a_repeated_issue_starts_no_second_loan(self):
        held = reserve(self.reader, self.book)
        loan = issue(self.librarian, held, 14)
        with self.assertRaises(ReservationRefused) as refused:
            issue(self.librarian, held, 14)
        self.assertEqual(
            (refused.exception.code, refused.exception.context),
            ("already_issued", {"loan": loan.pk}),
        )
        detail = f"This reservation was already issued as loan #{loan.pk}."
        response = self.api(self.librarian, f"/api/v1/reservation/{held.pk}/issue/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(),
            {"code": "already_issued", "detail": detail, "loan": loan.pk},
        )
        page = self.signed_in(self.librarian).post(
            reverse("reservation_issue", args=[held.pk]), {"days": 14}, follow=True
        )
        self.assertContains(page, detail)
        self.assertEqual(Order.objects.filter(book=self.book).count(), 1)

    def test_an_expired_reservation_is_not_issued(self):
        lapsed = self.reserve(created_at=timezone.now() - timedelta(hours=49))
        with self.assertRaises(ReservationRefused) as refused:
            issue(self.librarian, lapsed, 14)
        self.assertEqual(refused.exception.code, "reservation_expired")
        self.assertEqual(
            refused.exception.message,
            f"This reservation expired at {in_kyiv(lapsed.expires_at)}. You can lend "
            "the book directly only if a copy is available.",
        )
        response = self.api(self.librarian, f"/api/v1/reservation/{lapsed.pk}/issue/")
        self.assertEqual(
            (response.status_code, response.json()["code"]),
            (409, "reservation_expired"),
        )
        self.assertFalse(Order.objects.exists())

    def test_issuing_one_second_before_the_deadline_succeeds_and_at_it_is_refused(self):
        early = reserve(self.reader, self.book)
        issue(self.librarian, early, 14, now=early.expires_at - timedelta(seconds=1))
        early.refresh_from_db()
        self.assertEqual(early.state, ISSUED)
        late = reserve(self.other, self.book)
        with self.assertRaises(ReservationRefused) as refused:
            issue(self.librarian, late, 14, now=late.expires_at)
        self.assertEqual(refused.exception.code, "reservation_expired")
        self.assertFalse(Order.objects.filter(user=self.other).exists())

    def test_a_cancelled_reservation_is_not_issued(self):
        held = reserve(self.reader, self.book)
        cancel(self.reader, held)
        with self.assertRaises(ReservationRefused) as refused:
            issue(self.librarian, held, 14)
        self.assertEqual(
            (refused.exception.code, refused.exception.message),
            ("not_active", "This reservation is cancelled; nothing was changed."),
        )
        self.assertFalse(Order.objects.exists())

    def test_a_librarian_cancels_with_a_reason_and_the_copy_is_free_at_once(self):
        last = Book.objects.create(name="Damaged copy", count=1)
        held = reserve(self.reader, last)
        self.assertEqual(self.available(last), 0)
        client = self.signed_in(self.librarian)
        url = reverse("reservation_cancel", args=[held.pk])
        self.assertContains(client.get(url), 'name="reason"')
        for reason in ("", "   ", "x" * 501):
            with self.subTest(reason=reason[:5]):
                self.assertEqual(client.post(url, {"reason": reason}).status_code, 200)
                held.refresh_from_db()
                self.assertEqual(held.state, ACTIVE)
        confirmation = client.post(url, {"reason": "Copy damaged"})
        self.assertContains(confirmation, "Confirm Cancellation")
        held.refresh_from_db()
        self.assertEqual(held.state, ACTIVE)
        response = client.post(url, {"reason": "Copy damaged", "confirm": "yes"})
        self.assertRedirects(
            response, reverse("reservation_desk"), fetch_redirect_response=False
        )
        held.refresh_from_db()
        self.assertEqual(
            (held.state, held.cancelled_by, held.cancel_reason),
            (CANCELLED, self.librarian, "Copy damaged"),
        )
        self.assertEqual(self.available(last), 1)
        entry = AuditEntry.objects.get(
            action="reservation_cancelled", target_id=held.pk
        )
        self.assertEqual(
            (entry.actor_id, entry.reason, entry.occurred_at),
            (self.librarian.pk, "Copy damaged", held.cancelled_at),
        )
        self.assertEqual(
            (entry.before, entry.after), ({"state": "active"}, {"state": "cancelled"})
        )

    def test_the_service_refuses_a_librarians_cancellation_without_a_reason(self):
        held = reserve(self.reader, self.book)
        for reason in ("", "  ", "x" * 501):
            with self.subTest(reason=reason[:5]):
                with self.assertRaises(ValidationError):
                    cancel(self.librarian, held, reason)
        held.refresh_from_db()
        self.assertEqual(held.state, ACTIVE)

    def test_the_api_asks_a_librarian_for_a_reason(self):
        held = reserve(self.reader, self.book)
        path = f"/api/v1/reservation/{held.pk}/cancel/"
        for body in ({}, {"reason": ""}, {"reason": "x" * 501}):
            with self.subTest(body=str(body)[:20]):
                response = self.api(self.librarian, path, body)
                self.assertEqual(response.status_code, 400)
                self.assertIn("reason", response.json())
        response = self.api(self.librarian, path, {"reason": "x" * 500})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            (body["state"], body["cancel_reason"], body["cancelled_by"]),
            ("cancelled", "x" * 500, self.librarian.pk),
        )
        self.assertTrue(body["cancelled_by_library"])
        again = self.api(self.librarian, path, {"reason": "Twice"})
        self.assertEqual(again.status_code, 409)
        self.assertEqual(
            again.json(),
            {
                "code": "not_active",
                "detail": "This reservation is cancelled; nothing was changed.",
            },
        )

    def test_a_reader_cancels_their_own_without_a_reason(self):
        mine = reserve(self.reader, self.book)
        theirs = reserve(self.other, self.book)
        client = self.signed_in(self.reader)
        url = reverse("reservation_cancel", args=[mine.pk])
        self.assertContains(client.get(reverse("reservation_my")), f'href="{url}"')
        self.assertNotContains(client.get(url), 'name="reason"')
        other_url = reverse("reservation_cancel", args=[theirs.pk])
        self.assertEqual(client.get(other_url).status_code, 404)
        self.assertEqual(client.post(other_url).status_code, 404)
        api = self.api(self.reader, f"/api/v1/reservation/{theirs.pk}/cancel/")
        self.assertEqual(api.status_code, 404)
        response = self.client.post(url)
        self.assertRedirects(
            response, reverse("reservation_my"), fetch_redirect_response=False
        )
        mine.refresh_from_db()
        self.assertEqual(
            (mine.state, mine.cancelled_by, mine.cancel_reason),
            (CANCELLED, self.reader, ""),
        )
        theirs.refresh_from_db()
        self.assertEqual(theirs.state, ACTIVE)
        again = self.client.post(url, follow=True)
        self.assertContains(again, "This reservation is no longer active.")
        third = reserve(self.reader, Book.objects.create(name="Another", count=1))
        response = self.api(self.reader, f"/api/v1/reservation/{third.pk}/cancel/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            (body["state"], body["cancelled_by_library"]), ("cancelled", False)
        )
        self.assertNotIn("cancelled_by", body)
        entry = AuditEntry.objects.get(
            action="reservation_cancelled", target_id=mine.pk
        )
        self.assertEqual((entry.actor_id, entry.reason), (self.reader.pk, ""))

    def test_readers_cannot_lend_issue_or_cancel_someone_elses(self):
        theirs = reserve(self.other, self.book)
        due = (timezone.now() + timedelta(days=14)).isoformat()
        client = self.signed_in(self.reader)
        lend_form = {"reader": self.reader.pk, "book": self.book.pk, "days": 14}
        issue_url = reverse("reservation_issue", args=[theirs.pk])
        refused = {
            "lend page": client.get(reverse("order_lend")).status_code,
            "lend": client.post(reverse("order_lend"), lend_form).status_code,
            "desk": client.get(reverse("reservation_desk")).status_code,
            "issue page": client.get(issue_url).status_code,
            "issue": client.post(issue_url, {"days": 14}).status_code,
            "cancel": client.post(
                reverse("reservation_cancel", args=[theirs.pk])
            ).status_code,
        }
        loan = {"book": self.book.pk, "plated_end_at": due}
        for name, path, body in (
            ("api loan", "/api/v1/order/", {**loan, "user": self.reader.pk}),
            ("api own loan", f"/api/v1/user/{self.reader.pk}/order/", loan),
            ("api issue", f"/api/v1/reservation/{theirs.pk}/issue/", None),
            ("api cancel", f"/api/v1/reservation/{theirs.pk}/cancel/", None),
        ):
            refused[name] = self.api(self.reader, path, body).status_code
        self.assertEqual(
            refused,
            {
                "lend page": 403,
                "lend": 403,
                "desk": 403,
                "issue page": 403,
                "issue": 403,
                "cancel": 404,
                "api loan": 403,
                "api own loan": 403,
                "api issue": 403,
                "api cancel": 404,
            },
        )
        for call in (
            partial(lend, self.reader, self.reader, self.book, 14),
            partial(issue, self.reader, theirs, 14),
            partial(cancel, self.reader, theirs),
        ):
            with self.subTest(call=call.func.__name__):
                with self.assertRaises(PermissionDenied):
                    call()
        theirs.refresh_from_db()
        self.assertEqual(theirs.state, ACTIVE)
        self.assertFalse(Order.objects.exists())

    def test_an_overdue_reader_is_neither_issued_nor_lent_a_book(self):
        held = reserve(self.reader, self.book)
        late = self.overdue()
        message = (
            "Test Reader has an overdue loan: “Overdue book”, due "
            f"{in_kyiv(late.plated_end_at, 'j M Y')}. It must be returned first."
        )
        free = Book.objects.create(name="Free book", count=1)
        for call in (
            partial(issue, self.librarian, held, 14),
            partial(lend, self.librarian, self.reader, free, 14),
        ):
            with self.subTest(call=call.func.__name__):
                with self.assertRaises(ReservationRefused) as refused:
                    call()
                self.assertEqual(
                    (refused.exception.code, refused.exception.message),
                    ("overdue_loan", message),
                )
        client = self.signed_in(self.librarian)
        page = client.post(
            reverse("reservation_issue", args=[held.pk]), {"days": 14}, follow=True
        )
        self.assertContains(page, message)
        page = client.post(
            reverse("order_lend"),
            {"reader": self.reader.pk, "book": free.pk, "days": 14},
        )
        self.assertContains(page, message)
        response = self.api(self.librarian, f"/api/v1/reservation/{held.pk}/issue/")
        self.assertEqual(response.json()["code"], "overdue_loan")
        self.assertEqual(Order.objects.filter(user=self.reader).count(), 1)

    def test_the_overdue_rule_does_not_block_correcting_a_loan(self):
        late = self.overdue()
        returned = Order.objects.create(
            user=self.reader,
            book=self.book,
            plated_end_at=timezone.now() + timedelta(days=7),
            end_at=timezone.now(),
        )
        client = self.signed_in(self.librarian)
        due = timezone.localtime(timezone.now() + timedelta(days=7))
        response = client.post(
            reverse("order_update", args=[returned.pk]),
            {"plated_end_at": due.strftime("%Y-%m-%d %H:%M"), "end_at": ""},
        )
        self.assertRedirects(response, reverse("order_all"))
        returned.refresh_from_db()
        self.assertIsNone(returned.end_at)
        right_book = Book.objects.create(name="Right book", count=1)
        response = client.patch(
            f"/api/v1/order/{late.pk}/",
            {"book": right_book.pk},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        late.refresh_from_db()
        self.assertEqual(late.book, right_book)

    def test_a_loan_a_reader_started_before_can_still_be_returned(self):
        earlier = self.lend()  # as readers lent to themselves until this change
        response = self.signed_in(self.librarian).post(
            reverse("order_close", args=[earlier.pk])
        )
        self.assertRedirects(response, reverse("order_all"))
        earlier.refresh_from_db()
        self.assertIsNotNone(earlier.end_at)

    def test_issuing_and_cancelling_work_while_the_event_broker_is_unavailable(self):
        from kombu.exceptions import OperationalError as BrokerError

        held = reserve(self.reader, self.book)
        other = reserve(self.other, self.book)
        client = self.signed_in(self.librarian)
        with (
            patch(
                "events.services.persist_event.apply_async",
                side_effect=BrokerError("broker down"),
            ),
            self.assertLogs("events.services", level="ERROR"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            issued = client.post(
                reverse("reservation_issue", args=[held.pk]), {"days": 14}
            )
            cancelled = client.post(
                reverse("reservation_cancel", args=[other.pk]),
                {"reason": "Copy damaged", "confirm": "yes"},
            )
        self.assertEqual((issued.status_code, cancelled.status_code), (302, 302))
        held.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((held.state, other.state), (ISSUED, CANCELLED))

    def test_the_desk_lists_active_reservations_by_deadline(self):
        now = timezone.now()
        later = self.reserve(created_at=now - timedelta(hours=1))
        sooner = self.reserve(user=self.other, created_at=now - timedelta(hours=2))
        self.reserve(
            book=Book.objects.create(name="Lapsed book", count=1),
            created_at=now - timedelta(hours=49),
        )
        self.reserve(
            book=Book.objects.create(name="Issued book", count=1), state=ISSUED
        )
        page = self.signed_in(self.librarian).get(reverse("reservation_desk"))
        self.assertEqual(
            [row.pk for row in page.context["reservations"]], [sooner.pk, later.pk]
        )
        self.assertNotContains(page, "Lapsed book")
        self.assertNotContains(page, "Issued book")
        for text in (
            "desk-other@example.com",
            in_kyiv(sooner.expires_at),
            "1 day 21 hours left",
            reverse("reservation_issue", args=[sooner.pk]),
            reverse("reservation_cancel", args=[sooner.pk]),
        ):
            with self.subTest(text=text):
                self.assertContains(page, text)

    def test_the_old_borrow_route_sends_readers_to_reserve_and_librarians_to_lend(self):
        url = reverse("order_create", args=[self.book.pk])
        book_page = reverse("book_detail", args=[self.book.pk])
        client = self.signed_in(self.reader)
        for response in (client.get(url), client.post(url, {"days": 14})):
            self.assertRedirects(response, book_page, fetch_redirect_response=False)
        self.assertFalse(Order.objects.exists())
        lend_url = f"{reverse('order_lend')}?book={self.book.pk}"
        response = self.signed_in(self.librarian).get(url)
        self.assertRedirects(response, lend_url, fetch_redirect_response=False)
        form = self.client.get(lend_url).context["form"]
        self.assertEqual(str(form["book"].value()), str(self.book.pk))
        self.assertEqual(str(form["days"].value()), "14")

    def test_lending_directly_under_the_availability_rule(self):
        last = Book.objects.create(name="Last copy", count=1)
        reserve(self.other, last)
        client = self.signed_in(self.librarian)
        page = client.post(
            reverse("order_lend"),
            {"reader": self.reader.pk, "book": last.pk, "days": 14},
        )
        self.assertContains(
            page,
            "No copy of “Last copy” is available. A reservation may be holding the last one.",
        )
        response = client.post(
            reverse("order_lend"),
            {"reader": self.reader.pk, "book": self.book.pk, "days": 21},
        )
        self.assertRedirects(
            response, reverse("order_all"), fetch_redirect_response=False
        )
        loan = Order.objects.get(user=self.reader)
        self.assertEqual(loan.book, self.book)
        self.assertGreater(loan.plated_end_at, timezone.now() + timedelta(days=20))
        self.assertEqual(self.client.post(reverse("order_lend"), {}).status_code, 200)
        self.assertEqual(Order.objects.count(), 1)

    def test_the_book_page_offers_librarians_a_direct_loan_and_readers_reserving(self):
        reader_page = self.signed_in(self.reader).get(
            reverse("book_detail", args=[self.book.pk])
        )
        self.assertContains(reader_page, "Reserve for 48 Hours")
        self.assertNotContains(
            reader_page, reverse("order_create", args=[self.book.pk])
        )
        self.assertNotContains(reader_page, "Lend Directly")
        librarian_page = self.signed_in(self.librarian).get(
            reverse("book_detail", args=[self.book.pk])
        )
        self.assertContains(
            librarian_page, f"{reverse('order_lend')}?book={self.book.pk}"
        )
        self.assertContains(librarian_page, "Lend Directly")

    def test_the_navigation_leads_to_my_reservations_and_the_desk(self):
        reader_page = self.signed_in(self.reader).get(reverse("book_list"))
        self.assertContains(reader_page, reverse("reservation_my"))
        self.assertNotContains(reader_page, reverse("reservation_desk"))
        librarian_page = self.signed_in(self.librarian).get(reverse("book_list"))
        self.assertContains(librarian_page, reverse("reservation_desk"))


class CancellationNoticeTests(ReservationTestCase):
    """The reader sees the library's cancellation on their next page until they dismiss
    it, and showing it writes nothing (FR-017, R15)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.librarian = account("notice-librarian@example.com", ROLE_LIBRARIAN)

    def cancelled_by_the_library(self):
        held = reserve(self.reader, self.book)
        cancel(self.librarian, held, "Copy damaged")
        held.refresh_from_db()
        return held

    def notice(self, held):
        return (
            "The library cancelled your reservation of “Reserved book” on "
            f"{in_kyiv(held.cancelled_at)}."
        )

    def test_the_reader_sees_the_cancellation_until_dismissing_it(self):
        held = self.cancelled_by_the_library()
        self.client.force_login(self.reader)
        entries = AuditEntry.objects.count()
        page = self.client.get(reverse("book_list"))
        self.assertContains(page, 'role="status"')
        self.assertContains(page, self.notice(held))
        self.assertContains(page, "Copy damaged")
        dismiss = reverse("reservation_notice_dismiss", args=[held.pk])
        self.assertContains(page, f'action="{dismiss}"')
        held.refresh_from_db()
        self.assertIsNone(held.cancellation_seen_at)
        self.assertEqual(AuditEntry.objects.count(), entries)
        response = self.client.post(dismiss, {"next": reverse("book_list")})
        self.assertRedirects(
            response, reverse("book_list"), fetch_redirect_response=False
        )
        held.refresh_from_db()
        self.assertIsNotNone(held.cancellation_seen_at)
        self.assertNotContains(self.client.get(reverse("book_list")), "Copy damaged")

    def test_only_the_reader_dismisses_and_only_by_post(self):
        held = self.cancelled_by_the_library()
        dismiss = reverse("reservation_notice_dismiss", args=[held.pk])
        self.client.force_login(account("notice-other@example.com"))
        self.assertEqual(self.client.post(dismiss).status_code, 404)
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get(dismiss).status_code, 405)
        response = self.client.post(dismiss, {"next": "https://elsewhere.example/"})
        self.assertRedirects(
            response, reverse("reservation_my"), fetch_redirect_response=False
        )
        held.refresh_from_db()
        self.assertIsNotNone(held.cancellation_seen_at)

    def test_a_readers_own_cancellation_shows_no_notice(self):
        held = reserve(self.reader, self.book)
        cancel(self.reader, held)
        self.client.force_login(self.reader)
        self.assertNotContains(
            self.client.get(reverse("book_list")), "The library cancelled"
        )


class TimeLeftTests(SimpleTestCase):
    """The time left, as pages show it: its two largest units (FR-019)."""

    def test_the_time_left_reads_in_days_hours_and_minutes(self):
        from .services import time_left

        now = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
        for left, text in (
            (timedelta(days=1, hours=3, minutes=20), "1 day 3 hours left"),
            (timedelta(hours=47, minutes=59, seconds=59), "1 day 23 hours left"),
            (timedelta(days=2), "2 days left"),
            (timedelta(days=1, minutes=30), "1 day left"),
            (timedelta(hours=3), "3 hours left"),
            (timedelta(hours=1, minutes=1), "1 hour 1 minute left"),
            (timedelta(minutes=45, seconds=30), "45 minutes left"),
            (timedelta(seconds=30), "less than a minute left"),
        ):
            with self.subTest(left=left):
                self.assertEqual(time_left(now + left, now), text)


class ReservationPageTests(ReservationTestCase):
    """The finished pages: the time left, deadlines with their zone, the next step in
    each state, a confirmation before cancelling, and the services' messages on every
    reservation page (FR-019, FR-020, research R17)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.librarian = account("pages-librarian@example.com", ROLE_LIBRARIAN)

    def signed_in(self, user):
        self.client.force_login(user)
        return self.client

    def test_pages_that_show_a_deadline_show_the_time_left_and_the_zone(self):
        held = self.reserve(created_at=timezone.now() - timedelta(hours=20, minutes=30))
        deadline = in_kyiv(held.expires_at)
        self.assertRegex(deadline, r" EES?T$")
        cancel_url = reverse("reservation_cancel", args=[held.pk])
        pages = (
            (self.reader, reverse("reservation_my")),
            (self.reader, cancel_url),
            (self.librarian, reverse("reservation_desk")),
            (self.librarian, reverse("reservation_issue", args=[held.pk])),
            (self.librarian, cancel_url),
        )
        for user, url in pages:
            page = self.signed_in(user).get(url)
            with self.subTest(user=user.email, url=url):
                self.assertContains(page, deadline)
                self.assertContains(page, "1 day 3 hours left")

    def test_an_issued_reservation_says_when_to_return_the_book(self):
        loan = issue(self.librarian, reserve(self.reader, self.book), 14)
        client = self.signed_in(self.reader)
        due = in_kyiv(loan.plated_end_at, "j M Y")
        self.assertContains(
            client.get(reverse("reservation_my")), f"On loan. Return it by {due}."
        )
        loan.end_at = timezone.now()
        loan.save()
        self.assertContains(
            client.get(reverse("reservation_my")),
            f"Returned on {in_kyiv(loan.end_at, 'j M Y')}.",
        )

    def test_a_cancellation_says_who_cancelled_it(self):
        mine = reserve(self.reader, self.book)
        cancel(self.reader, mine)
        theirs = reserve(self.reader, Book.objects.create(name="Second book", count=1))
        cancel(self.librarian, theirs, "Copy damaged")
        theirs.refresh_from_db()
        page = self.signed_in(self.reader).get(reverse("reservation_my"))
        for text in (
            "You cancelled it. Reserve it again if a copy is available.",
            f"The library cancelled it on {in_kyiv(theirs.cancelled_at)}. Reserve it "
            "again if a copy is available.",
            "Reason: Copy damaged",
        ):
            with self.subTest(text=text):
                self.assertContains(page, text)

    def test_a_librarian_confirms_the_reason_before_the_reservation_is_cancelled(self):
        held = reserve(self.reader, self.book)
        client = self.signed_in(self.librarian)
        url = reverse("reservation_cancel", args=[held.pk])
        confirmation = client.post(url, {"reason": "  Copy damaged "})
        self.assertContains(confirmation, "Confirm Cancellation")
        self.assertContains(
            confirmation, '<input type="hidden" name="reason" value="Copy damaged">'
        )
        self.assertContains(confirmation, 'name="confirm" value="yes"')
        self.assertNotContains(confirmation, "<textarea")
        edit = client.post(url, {"reason": "Copy damaged", "edit": "yes"})
        self.assertContains(edit, "Copy damaged</textarea>")
        self.assertNotContains(edit, "Confirm Cancellation")
        held.refresh_from_db()
        self.assertEqual(held.state, ACTIVE)
        self.assertFalse(
            AuditEntry.objects.filter(action="reservation_cancelled").exists()
        )
        response = client.post(url, {"reason": "Copy damaged", "confirm": "yes"})
        self.assertRedirects(
            response, reverse("reservation_desk"), fetch_redirect_response=False
        )
        held.refresh_from_db()
        self.assertEqual((held.state, held.cancel_reason), (CANCELLED, "Copy damaged"))

    def test_the_readers_cancel_page_is_the_confirmation_step(self):
        held = reserve(self.reader, self.book)
        page = self.signed_in(self.reader).get(
            reverse("reservation_cancel", args=[held.pk])
        )
        self.assertContains(page, "Yes, Cancel Reservation")
        self.assertContains(page, "Keep Reservation")
        held.refresh_from_db()
        self.assertEqual(held.state, ACTIVE)

    def test_the_issue_page_says_why_it_cannot_issue_and_what_to_do_next(self):
        now = timezone.now()
        lapsed = self.reserve(created_at=now - timedelta(hours=49))
        issued_from = reserve(self.reader, Book.objects.create(name="Issued", count=1))
        loan = issue(self.librarian, issued_from, 14)
        cancelled = reserve(self.reader, Book.objects.create(name="Cancelled", count=1))
        cancel(self.reader, cancelled)
        late_reader = account("pages-late@example.com")
        overdue_held = reserve(late_reader, self.book)
        late = Order.objects.create(
            user=late_reader,
            book=Book.objects.create(name="Overdue book", count=1),
            plated_end_at=now - timedelta(days=1),
        )
        cases = (
            (
                lapsed,
                f"This reservation expired at {in_kyiv(lapsed.expires_at)}. You can "
                "lend the book directly only if a copy is available.",
                f'href="{reverse("order_lend")}?book={self.book.pk}&amp;reader='
                f'{self.reader.pk}"',
            ),
            (
                issued_from,
                f"This reservation was already issued as loan #{loan.pk}.",
                f'href="{reverse("order_update", args=[loan.pk])}"',
            ),
            (
                cancelled,
                "This reservation is cancelled; nothing was changed.",
                "Back to Desk",
            ),
            (
                overdue_held,
                "Test Reader has an overdue loan: “Overdue book”, due "
                f"{in_kyiv(late.plated_end_at, 'j M Y')}. It must be returned first.",
                f'href="{reverse("books_by_user", args=[late_reader.pk])}"',
            ),
        )
        client = self.signed_in(self.librarian)
        for reservation, message, next_step in cases:
            url = reverse("reservation_issue", args=[reservation.pk])
            for page in (client.get(url), client.post(url, {"days": 14})):
                with self.subTest(url=url, method=page.wsgi_request.method):
                    self.assertContains(page, message)
                    self.assertContains(page, next_step)
                    self.assertNotContains(page, 'name="days"')
        self.assertEqual(Order.objects.count(), 2)

    def test_the_cancel_page_says_when_a_reservation_is_no_longer_active(self):
        lapsed = self.reserve(created_at=timezone.now() - timedelta(hours=49))
        url = reverse("reservation_cancel", args=[lapsed.pk])
        for user, message in (
            (self.reader, "This reservation is no longer active."),
            (self.librarian, "This reservation is expired; nothing was changed."),
        ):
            client = self.signed_in(user)
            for page in (
                client.get(url),
                client.post(url, {"reason": "Too late", "confirm": "yes"}),
            ):
                with self.subTest(user=user.email, method=page.wsgi_request.method):
                    self.assertContains(page, message)
                    self.assertNotContains(page, "Yes, Cancel Reservation")
        lapsed.refresh_from_db()
        self.assertEqual(lapsed.state, ACTIVE)  # the scheduled expiry records it

    def test_a_waiting_message_shows_on_every_reservation_page(self):
        held = reserve(self.reader, self.book)
        client = self.signed_in(self.librarian)
        for n, url in enumerate(
            (
                reverse("reservation_desk"),
                reverse("reservation_issue", args=[held.pk]),
                reverse("reservation_cancel", args=[held.pk]),
                reverse("order_lend"),
                reverse("book_detail", args=[self.book.pk]),
            )
        ):
            book = Book.objects.create(name=f"Lent book {n}", count=1)
            lend_form = {"reader": self.reader.pk, "book": book.pk, "days": 14}
            client.post(reverse("order_lend"), lend_form)
            with self.subTest(url=url):
                self.assertContains(
                    client.get(url), f"Lent “Lent book {n}” to Test Reader"
                )
        client = self.signed_in(self.reader)
        for n, url in enumerate(
            (
                reverse("reservation_cancel", args=[held.pk]),
                reverse("book_detail", args=[self.book.pk]),
            )
        ):
            book = Book.objects.create(name=f"Wanted book {n}", count=1)
            client.post(reverse("reserve", args=[book.pk]))
            with self.subTest(url=url):
                self.assertContains(client.get(url), f"Reserved “Wanted book {n}”.")

    def test_the_book_page_links_the_next_step_and_counts_held_copies(self):
        last = Book.objects.create(name="Last copy", count=1)
        reserve(self.reader, last)
        page = self.signed_in(self.reader).get(reverse("book_detail", args=[last.pk]))
        self.assertContains(page, "You already reserved “Last copy”.")
        self.assertContains(page, "See My Reservations")
        other = account("pages-other@example.com")
        client = self.signed_in(other)
        page = client.get(reverse("book_detail", args=[last.pk]))
        self.assertContains(page, "0 of 1 Available")
        self.assertNotContains(page, "Borrowed")
        catalog = client.get(reverse("book_list"))
        self.assertContains(catalog, "0 of 1 in stock")
        self.assertNotContains(catalog, "(All borrowed)")
        self.assertNotContains(catalog, "(Borrowed)")
        Order.objects.create(
            user=other,
            book=Book.objects.create(name="Overdue book", count=1),
            plated_end_at=timezone.now() - timedelta(days=1),
        )
        page = client.get(reverse("book_detail", args=[self.book.pk]))
        self.assertContains(page, "was due on")
        self.assertContains(page, "See My Orders")


class ReservationRaceTests(FakeEncoderMixin, TransactionTestCase):
    """Simultaneous requests never hold or lend more copies than exist, nor more than 3
    reservations for one reader (FR-011, FR-012, SC-002)."""

    def race(self, calls):
        """Run each call on its own thread and connection, all released at once;
        return True for each that succeeded and the code of each refusal."""
        barrier = Barrier(len(calls))

        def contend(call):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    call()
                except ReservationRefused as refused:
                    return refused.code
                return True
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            futures = [pool.submit(contend, call) for call in calls]
            return [future.result(timeout=60) for future in futures]

    def test_20_readers_on_the_last_copy_succeed_exactly_once(self):
        readers = [account(f"racer{n}@example.com") for n in range(20)]
        for run in range(20):
            with self.subTest(run=run):
                book = Book.objects.create(name=f"Last copy {run}", count=1)
                results = self.race([partial(reserve, who, book) for who in readers])
                self.assertEqual(results.count(True), 1)
                self.assertEqual(Reservation.objects.filter(book=book).count(), 1)

    def test_a_reservation_racing_a_loan_of_the_last_copy_succeeds_exactly_once(self):
        librarian = account("lender@example.com", ROLE_LIBRARIAN)
        for run in range(10):
            with self.subTest(run=run):
                holder = account(f"holder{run}@example.com")
                borrower = account(f"borrower{run}@example.com")
                book = Book.objects.create(name=f"Contested copy {run}", count=1)
                results = self.race(
                    [
                        partial(reserve, holder, book),
                        partial(lend, librarian, borrower, book, 14),
                    ]
                )
                self.assertEqual(results.count(True), 1)
                held = Reservation.objects.filter(book=book).count()
                lent = Order.objects.filter(book=book).count()
                self.assertEqual(held + lent, 1)

    def test_one_reader_sending_5_reservations_at_once_holds_at_most_3(self):
        for run in range(20):
            with self.subTest(run=run):
                reader = account(f"eager{run}@example.com")
                books = [
                    Book.objects.create(name=f"Pick {run}-{n}", count=1)
                    for n in range(5)
                ]
                results = self.race([partial(reserve, reader, book) for book in books])
                self.assertEqual(results.count(True), 3)
                self.assertEqual(Reservation.objects.filter(user=reader).count(), 3)

    def test_two_librarians_issuing_one_reservation_start_one_loan(self):
        librarians = [account(f"desk{n}@example.com", ROLE_LIBRARIAN) for n in range(2)]
        for run in range(20):
            with self.subTest(run=run):
                reader = account(f"collector{run}@example.com")
                book = Book.objects.create(name=f"Collected {run}", count=1)
                held = reserve(reader, book)
                results = self.race(
                    [partial(issue, who, held, 14) for who in librarians]
                )
                self.assertCountEqual(results, [True, "already_issued"])
                self.assertEqual(Order.objects.filter(book=book).count(), 1)

    def test_a_loan_racing_an_issue_of_the_same_reservation_starts_one_loan(self):
        librarians = [
            account(f"counter{n}@example.com", ROLE_LIBRARIAN) for n in range(2)
        ]
        for run in range(20):
            with self.subTest(run=run):
                reader = account(f"visitor{run}@example.com")
                book = Book.objects.create(name=f"Held copy {run}", count=1)
                held = reserve(reader, book)
                results = self.race(
                    [
                        partial(issue, librarians[0], held, 14),
                        partial(lend, librarians[1], reader, book, 14),
                    ]
                )
                self.assertEqual(results.count(True), 1)
                self.assertEqual(Order.objects.filter(book=book).count(), 1)
                held.refresh_from_db()
                self.assertEqual(held.state, ISSUED)
