"""The reservation: its deadline, states, constraints and guards (data-model.md §1)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from functools import partial
from threading import Barrier
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import PermissionDenied
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
from .services import ReservationRefused, eligibility, lend, reserve
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

    def test_a_readers_own_loan_of_a_reserved_book_issues_the_reservation(self):
        last = Book.objects.create(name="Last copy", count=1)
        held = reserve(self.reader, last)
        client = self.signed_in()
        self.assertEqual(
            client.get(reverse("order_create", args=[last.pk])).status_code, 200
        )
        response = client.post(reverse("order_create", args=[last.pk]), {"days": 14})
        self.assertRedirects(
            response, reverse("order_my"), fetch_redirect_response=False
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
            lend(self.reader, self.reader, last, 14)
        self.assertEqual(refused.exception.code, "no_copy_available")
        self.assertFalse(Order.objects.filter(book=last).exists())

    def test_readers_lend_only_to_themselves(self):
        with self.assertRaises(PermissionDenied):
            lend(self.reader, self.other, self.book, 14)
        self.assertFalse(Order.objects.exists())

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
            "Collected. It is now on loan; see My orders.",
            "Cancelled.",
            "Copy damaged",
        ):
            with self.subTest(text=text):
                self.assertContains(page, text)

    def test_a_held_copy_whose_total_was_lowered_away_is_not_lent(self):
        last = Book.objects.create(name="Lost copy", count=1)
        held = reserve(self.reader, last)
        last.count = 0
        last.save()
        client = self.signed_in()
        self.assertEqual(
            client.get(reverse("order_create", args=[last.pk])).status_code, 200
        )
        response = client.post(
            reverse("order_create", args=[last.pk]), {"days": 14}, follow=True
        )
        self.assertEqual(
            response.redirect_chain, [(reverse("book_detail", args=[last.pk]), 302)]
        )
        self.assertContains(response, "No copy of “Lost copy” is available right now.")
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


class ReservationRaceTests(FakeEncoderMixin, TransactionTestCase):
    """Simultaneous requests never hold or lend more copies than exist, nor more than 3
    reservations for one reader (FR-011, FR-012, SC-002)."""

    def race(self, calls):
        """Run each call on its own thread and connection, all released at once;
        return which succeeded."""
        barrier = Barrier(len(calls))

        def contend(call):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    call()
                except ReservationRefused:
                    return False
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
        for run in range(10):
            with self.subTest(run=run):
                holder = account(f"holder{run}@example.com")
                borrower = account(f"borrower{run}@example.com")
                book = Book.objects.create(name=f"Contested copy {run}", count=1)
                results = self.race(
                    [
                        partial(reserve, holder, book),
                        partial(lend, borrower, borrower, book, 14),
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
