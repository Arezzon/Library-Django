"""The whole reservation journey from both sides of the desk, through the web and the
API (FR-019 to FR-021, research R17)."""

from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.urls import reverse
from django.utils import dateformat, timezone, translation
from django.utils.dateparse import parse_datetime

from audit.models import AuditEntry
from authentication.models import ROLE_LIBRARIAN, CustomUser
from book.models import Book
from book.testing import FakeEncoderMixin

from .models import (
    RESERVATION_HOURS,
    Order,
    Reservation,
    ReservationSettings,
    ReservationState,
)
from .services import cancel, issue, reserve
from .tasks import expire_reservations

KYIV = ZoneInfo("Europe/Kyiv")


def local(moment, pattern="j M Y, H:i T"):
    """A time as pages show it, worked out independently of the settings."""
    return dateformat.format(moment.astimezone(KYIV), pattern)


def account(email, first_name, last_name, role=CustomUser.ROLE_VISITOR):
    return CustomUser.objects.create_user(
        email=email,
        password="journey-password",
        first_name=first_name,
        middle_name="",
        last_name=last_name,
        role=role,
        is_active=True,
    )


class FormFields(HTMLParser):
    """The fields of a page that a person fills in, and the ids that labels name."""

    def __init__(self):
        super().__init__()
        self.fields, self.labelled = [], set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "label" and attrs.get("for"):
            self.labelled.add(attrs["for"])
        elif tag in ("input", "select", "textarea") and attrs.get("type") not in (
            "hidden",
            "submit",
            "button",
        ):
            self.fields.append(attrs.get("id") or attrs.get("name"))


class DeadlineTimes(HTMLParser):
    """Read the human and machine-readable deadline from rendered HTML."""

    def __init__(self, page):
        super().__init__()
        self.times = []
        self.current = None
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "time" and "data-reservation-deadline" in attrs:
            self.current = [
                int(attrs["data-reservation-deadline"]),
                parse_datetime(attrs["datetime"]),
                "",
            ]

    def handle_data(self, text):
        if self.current is not None:
            self.current[2] += text

    def handle_endtag(self, tag):
        if tag == "time" and self.current is not None:
            self.times.append(tuple(self.current))
            self.current = None


class ReservationJourneyTests(FakeEncoderMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reader = account("journey-reader@example.com", "Olena", "Shevchenko")
        cls.librarian = account(
            "journey-librarian@example.com", "Desk", "Librarian", ROLE_LIBRARIAN
        )
        cls.book = Book.objects.create(name="Kobzar", count=2)

    def signed_in(self, user):
        self.client.force_login(user)
        return self.client

    def api(self, user, method, path, body=None):
        return getattr(self.signed_in(user), method)(
            path, body or {}, content_type="application/json"
        )

    def available(self):
        return Book.objects.get(pk=self.book.pk).available_count

    def assertLabelled(self, page):
        self.assertEqual(page.status_code, 200)
        fields = FormFields()
        fields.feed(page.content.decode())
        for field in fields.fields:
            with self.subTest(field=field, page=page.wsgi_request.path):
                self.assertIn(field, fields.labelled)

    def test_reserve_issue_and_return_on_the_web(self):
        client = self.signed_in(self.reader)
        self.assertContains(
            client.get(reverse("book_detail", args=[self.book.pk])), "2 of 2 Available"
        )
        mine = client.post(reverse("reserve", args=[self.book.pk]), follow=True)
        held = Reservation.objects.get(user=self.reader, book=self.book)
        deadline = local(held.expires_at)
        self.assertRegex(deadline, r" EES?T$")
        for text in (
            f"Reserved “Kobzar”. Collect it from a librarian before {deadline}.",
            "Active",
            "1 day 23 hours left",
            f"Collect it from a librarian before {deadline}.",
        ):
            with self.subTest(text=text):
                self.assertContains(mine, text)
        self.assertEqual(self.available(), 1)

        client = self.signed_in(self.librarian)
        desk = client.get(reverse("reservation_desk"))
        issue_url = reverse("reservation_issue", args=[held.pk])
        for text in (
            "Olena Shevchenko",
            deadline,
            "1 day 23 hours left",
            f'href="{issue_url}"',
        ):
            with self.subTest(text=text):
                self.assertContains(desk, text)
        self.assertContains(client.get(issue_url), f"{deadline} (1 day 23 hours left)")
        issued = client.post(issue_url, {"days": 14}, follow=True)
        loan = Order.objects.get(user=self.reader, book=self.book)
        due = local(loan.plated_end_at, "j M Y")
        self.assertContains(
            issued,
            f"Issued “Kobzar” to Olena Shevchenko as loan #{loan.pk}, due {due}.",
        )
        self.assertContains(issued, "No active reservations.")
        self.assertEqual(self.available(), 1)  # the held copy became the lent one

        client = self.signed_in(self.reader)
        self.assertContains(client.get(reverse("order_my")), "Kobzar")
        mine = client.get(reverse("reservation_my"))
        self.assertContains(mine, "Issued")
        self.assertContains(mine, f"On loan. Return it by {due}.")

        self.signed_in(self.librarian).post(reverse("order_close", args=[loan.pk]))
        loan.refresh_from_db()
        self.assertIsNotNone(loan.end_at)
        client = self.signed_in(self.reader)
        self.assertContains(
            client.get(reverse("book_detail", args=[self.book.pk])), "2 of 2 Available"
        )
        self.assertContains(
            client.get(reverse("reservation_my")),
            f"Returned on {local(loan.end_at, 'j M Y')}.",
        )

    def test_reserve_issue_and_return_through_the_api(self):
        response = self.api(
            self.reader, "post", "/api/v1/reservation/", {"book": self.book.pk}
        )
        self.assertEqual(response.status_code, 201)
        held = response.json()["id"]
        self.assertEqual(response.json()["state"], "active")
        response = self.api(
            self.librarian, "post", f"/api/v1/reservation/{held}/issue/", {"days": 14}
        )
        self.assertEqual(response.status_code, 201)
        loan = response.json()["loan"]["id"]
        loans = self.api(self.reader, "get", f"/api/v1/user/{self.reader.pk}/order/")
        self.assertEqual([row["id"] for row in loans.json()], [loan])
        mine = self.api(self.reader, "get", f"/api/v1/reservation/{held}/").json()
        self.assertEqual((mine["state"], mine["loan"]), ("issued", loan))
        book = f"/api/v1/book/{self.book.pk}/"
        self.assertEqual(
            self.api(self.reader, "get", book).json()["available_count"], 1
        )
        returned = self.api(
            self.librarian,
            "patch",
            f"/api/v1/order/{loan}/",
            {"end_at": timezone.now().isoformat()},
        )
        self.assertEqual(returned.status_code, 200)
        self.assertEqual(
            self.api(self.reader, "get", book).json()["available_count"], 2
        )

    def test_a_librarian_cancels_with_a_reason_and_the_reader_dismisses_the_notice(
        self,
    ):
        held = reserve(self.reader, self.book)
        client = self.signed_in(self.librarian)
        url = reverse("reservation_cancel", args=[held.pk])
        self.assertContains(client.get(reverse("reservation_desk")), f'href="{url}"')
        self.assertContains(client.get(url), 'name="reason"')
        confirmation = client.post(url, {"reason": "The copy is damaged"})
        self.assertContains(confirmation, "Confirm Cancellation")
        self.assertContains(confirmation, "The copy is damaged")
        held.refresh_from_db()
        self.assertEqual(held.state, ReservationState.ACTIVE)
        done = client.post(
            url, {"reason": "The copy is damaged", "confirm": "yes"}, follow=True
        )
        self.assertContains(
            done, "Cancelled the reservation of “Kobzar” for Olena Shevchenko."
        )
        held.refresh_from_db()
        self.assertEqual(held.state, ReservationState.CANCELLED)
        self.assertEqual(self.available(), 2)

        client = self.signed_in(self.reader)
        when = local(held.cancelled_at)
        notice = f"The library cancelled your reservation of “Kobzar” on {when}."
        page = client.get(reverse("book_list"))
        self.assertContains(page, notice)
        self.assertContains(page, "Reason: The copy is damaged")
        self.assertContains(
            client.get(reverse("reservation_my")),
            f"The library cancelled it on {when}. Reserve it again if a copy is "
            "available.",
        )
        client.post(
            reverse("reservation_notice_dismiss", args=[held.pk]),
            {"next": reverse("book_list")},
        )
        self.assertNotContains(client.get(reverse("book_list")), notice)

    def test_the_cancellation_through_the_api(self):
        response = self.api(
            self.reader, "post", "/api/v1/reservation/", {"book": self.book.pk}
        )
        path = f"/api/v1/reservation/{response.json()['id']}/cancel/"
        self.assertEqual(self.api(self.librarian, "post", path).status_code, 400)
        response = self.api(
            self.librarian, "post", path, {"reason": "The copy is damaged"}
        )
        self.assertEqual(response.status_code, 200)
        held = response.json()["id"]
        mine = self.api(self.reader, "get", f"/api/v1/reservation/{held}/").json()
        self.assertEqual(
            (mine["state"], mine["cancel_reason"], mine["cancelled_by_library"]),
            ("cancelled", "The copy is damaged", True),
        )
        self.assertNotIn("cancelled_by", mine)
        self.assertEqual(self.available(), 2)
        self.assertContains(
            self.signed_in(self.reader).get(reverse("book_list")),
            "Reason: The copy is damaged",
        )

    def test_a_reservation_that_passes_its_deadline(self):
        lapsed = reserve(
            self.reader, self.book, now=timezone.now() - timedelta(hours=49)
        )
        client = self.signed_in(self.reader)
        mine = client.get(reverse("reservation_my"))
        self.assertContains(mine, "Expired")
        self.assertContains(
            mine,
            "The reservation period ended. Reserve it again if a copy is available.",
        )
        self.assertContains(
            client.get(reverse("book_detail", args=[self.book.pk])), "2 of 2 Available"
        )
        api = self.api(self.reader, "get", f"/api/v1/reservation/{lapsed.pk}/")
        self.assertEqual(api.json()["state"], "expired")

        client = self.signed_in(self.librarian)
        self.assertContains(
            client.get(reverse("reservation_desk")), "No active reservations."
        )
        page = client.get(reverse("reservation_issue", args=[lapsed.pk]))
        self.assertContains(
            page, f"This reservation expired at {local(lapsed.expires_at)}."
        )
        self.assertContains(
            page,
            f"{reverse('order_lend')}?book={self.book.pk}&amp;reader={self.reader.pk}",
        )
        self.assertNotContains(page, 'name="days"')

        lapsed.refresh_from_db()
        self.assertEqual(lapsed.state, ReservationState.ACTIVE)  # not recorded yet
        self.assertEqual(expire_reservations(), 1)
        lapsed.refresh_from_db()
        self.assertEqual(lapsed.state, ReservationState.EXPIRED)
        entry = AuditEntry.objects.get(
            action="reservation_expired", target_id=lapsed.pk
        )
        self.assertEqual(
            (entry.channel, entry.actor_id, entry.occurred_at),
            ("system", None, lapsed.expires_at),
        )

    def assertLastCopyHeld(self, book, other):
        """Another reader finds no copy and cannot reserve one, on the web or the
        API."""
        client = self.signed_in(other)
        self.assertContains(
            client.get(reverse("book_detail", args=[book.pk])), "0 of 1 Available"
        )
        page = client.post(reverse("reserve", args=[book.pk]), follow=True)
        self.assertContains(page, f"No copy of “{book.name}” is available right now.")
        response = self.api(other, "post", "/api/v1/reservation/", {"book": book.pk})
        self.assertEqual(
            (response.status_code, response.json()["code"]),
            (409, "no_copy_available"),
        )
        self.assertFalse(Reservation.objects.filter(user=other, book=book).exists())

    def assertLastCopyReserved(self, book, other, channel, now):
        """The copy is back in stock, and another reader reserves it through
        ``channel``, with a full term from ``now``."""
        client = self.signed_in(other)
        self.assertContains(
            client.get(reverse("book_detail", args=[book.pk])), "1 of 1 Available"
        )
        if channel == "web":
            page = client.post(reverse("reserve", args=[book.pk]), follow=True)
            self.assertContains(page, f"Reserved “{book.name}”.")
        else:
            response = self.api(
                other, "post", "/api/v1/reservation/", {"book": book.pk}
            )
            self.assertEqual(response.status_code, 201)
        held = Reservation.objects.get(user=other, book=book)
        self.assertEqual(held.state, ReservationState.ACTIVE)
        self.assertEqual(held.expires_at, now + timedelta(hours=RESERVATION_HOURS))
        self.assertEqual(Book.objects.get(pk=book.pk).available_count, 0)

    def test_the_last_copy_is_back_in_stock_at_the_deadline(self):
        # KAN-88: no task runs; the reservation's deadline alone frees the copy.
        # The term comes from RESERVATION_HOURS, so the moments follow it.
        for n, channel in enumerate(("web", "api")):
            with self.subTest(channel=channel):
                book = Book.objects.create(name=f"Last copy {n}", count=1)
                other = account(f"deadline-{n}@example.com", "Taras", "Bondar")
                held = reserve(self.reader, book)
                self.assertEqual(
                    held.expires_at - held.created_at,
                    timedelta(hours=RESERVATION_HOURS),
                )
                before = held.expires_at - timedelta(seconds=1)
                with patch("django.utils.timezone.now", return_value=before):
                    self.assertLastCopyHeld(book, other)
                with patch("django.utils.timezone.now", return_value=held.expires_at):
                    self.assertLastCopyReserved(book, other, channel, held.expires_at)
                    mine = self.api(
                        self.reader, "get", f"/api/v1/reservation/{held.pk}/"
                    )
                    self.assertEqual(mine.json()["state"], "expired")

    def test_the_last_copy_is_back_in_stock_once_its_reservation_is_cancelled(self):
        # KAN-88: a librarian's cancellation and the reader's own both free it at once.
        for n, (canceller, channel) in enumerate(
            (("librarian", "web"), ("reader", "api"))
        ):
            with self.subTest(canceller=canceller, channel=channel):
                book = Book.objects.create(name=f"Cancelled copy {n}", count=1)
                other = account(f"cancel-{n}@example.com", "Taras", "Bondar")
                held = reserve(self.reader, book)
                self.assertLastCopyHeld(book, other)
                if canceller == "librarian":
                    cancel(self.librarian, held, "The copy is damaged")
                else:
                    cancel(self.reader, held, "")
                now = timezone.now()
                with patch("django.utils.timezone.now", return_value=now):
                    self.assertLastCopyReserved(book, other, channel, now)

    def test_every_form_field_on_these_pages_has_a_label(self):
        held = reserve(self.reader, self.book)
        done = reserve(self.reader, Book.objects.create(name="Cancelled", count=1))
        cancel(self.librarian, done, "The copy is damaged")
        reader_pages = [
            reverse("book_detail", args=[self.book.pk]),
            reverse("reservation_my"),
            reverse("reservation_cancel", args=[held.pk]),
        ]
        client = self.signed_in(self.reader)
        for url in reader_pages:
            self.assertLabelled(client.get(url))
        client = self.signed_in(self.librarian)
        cancel_url = reverse("reservation_cancel", args=[held.pk])
        for page in (
            client.get(reverse("reservation_desk")),
            client.get(reverse("reservation_issue", args=[held.pk])),
            client.get(cancel_url),
            client.post(cancel_url, {"reason": "The copy is damaged"}),
            client.get(reverse("order_lend")),
        ):
            self.assertLabelled(page)
        issue(self.librarian, held, 14)
        self.assertLabelled(client.get(reverse("reservation_issue", args=[held.pk])))

    def deadline_text(self, response, reservation):
        times = DeadlineTimes(response.content.decode()).times
        matches = [(moment, text) for pk, moment, text in times if pk == reservation.pk]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0], reservation.expires_at)
        return matches[0][1]

    def test_confirmation_list_and_api_agree_in_winter_summer_and_locales(self):
        for language in ("en-us", "uk"):
            for now, english in (
                (datetime(2026, 12, 31, 21, 30, tzinfo=UTC), "1 Jan 2027, 00:30 EET"),
                (datetime(2027, 6, 30, 20, 30, tzinfo=UTC), "1 Jul 2027, 00:30 EEST"),
            ):
                with (
                    self.subTest(language=language, now=now),
                    translation.override(language),
                    timezone.override(KYIV),
                    patch("django.utils.timezone.now", return_value=now),
                ):
                    ReservationSettings.objects.update_or_create(
                        pk=1, defaults={"hours": 1}
                    )
                    book = Book.objects.create(
                        name=f"Deadline {language} {now.month}", count=2
                    )
                    page = self.signed_in(self.reader).post(
                        reverse("reserve", args=[book.pk]), follow=True
                    )
                    held = Reservation.objects.get(user=self.reader, book=book)
                    text = self.deadline_text(page, held)
                    self.assertEqual(text, local(held.expires_at))
                    if language == "en-us":
                        self.assertEqual(text, english)
                    self.assertContains(
                        page,
                        f"Reserved “{book.name}”. Collect it from a librarian before {text}.",
                    )
                    api = self.api(
                        self.reader, "get", f"/api/v1/reservation/{held.pk}/"
                    )
                    self.assertEqual(api.status_code, 200)
                    self.assertEqual(
                        parse_datetime(api.json()["expires_at"]), held.expires_at
                    )
                    # Use the same catalog later without retaining four active holds.
                    cancel(self.reader, held, now=now)

    def test_policy_changes_only_change_new_displayed_deadlines(self):
        now = datetime(2027, 1, 4, 10, 15, tzinfo=UTC)
        with (
            patch("django.utils.timezone.now", return_value=now),
            timezone.override(KYIV),
        ):
            ReservationSettings.objects.update_or_create(pk=1, defaults={"hours": 1})
            first_page = self.signed_in(self.reader).post(
                reverse("reserve", args=[self.book.pk]), follow=True
            )
            first = Reservation.objects.get(user=self.reader, book=self.book)
            before = self.deadline_text(first_page, first)
            librarian = self.signed_in(self.librarian)
            self.assertEqual(
                librarian.post(
                    reverse("reservation_settings"), {"hours": 168}
                ).status_code,
                302,
            )
            other = Book.objects.create(name="New policy book", count=2)
            page = self.signed_in(self.reader).post(
                reverse("reserve", args=[other.pk]), follow=True
            )
            second = Reservation.objects.get(user=self.reader, book=other)
            self.assertEqual(self.deadline_text(page, first), before)
            self.assertEqual(self.deadline_text(page, second), "11 Jan 2027, 12:15 EET")
            self.assertContains(
                page,
                "Reserved “New policy book”. Collect it from a librarian before 11 Jan 2027, 12:15 EET.",
            )
            first.refresh_from_db()
            self.assertEqual(first.expires_at, now + timedelta(hours=1))
            for held in (first, second):
                data = self.api(
                    self.reader, "get", f"/api/v1/reservation/{held.pk}/"
                ).json()
                self.assertEqual(parse_datetime(data["expires_at"]), held.expires_at)

    def test_api_created_reservation_shows_its_stored_deadline(self):
        ReservationSettings.objects.update_or_create(pk=1, defaults={"hours": 24})
        response = self.api(
            self.reader, "post", "/api/v1/reservation/", {"book": self.book.pk}
        )
        self.assertEqual(response.status_code, 201)
        held = Reservation.objects.get(pk=response.json()["id"])
        page = self.signed_in(self.reader).get(reverse("reservation_my"))
        self.assertEqual(
            self.deadline_text(page, held),
            local(parse_datetime(response.json()["expires_at"])),
        )

    def test_expired_deadline_stays_visible_and_matches_api_without_a_worker(self):
        held = reserve(self.reader, self.book)
        with patch("django.utils.timezone.now", return_value=held.expires_at):
            page = self.signed_in(self.reader).get(reverse("reservation_my"))
            self.assertEqual(self.deadline_text(page, held), local(held.expires_at))
            self.assertContains(page, "Expired")
            self.assertNotContains(page, "hours left")
            data = self.api(
                self.reader, "get", f"/api/v1/reservation/{held.pk}/"
            ).json()
            self.assertEqual(data["state"], "expired")
            self.assertEqual(parse_datetime(data["expires_at"]), held.expires_at)

    def test_cancelled_deadline_does_not_disappear_or_become_expired(self):
        held = reserve(self.reader, self.book)
        cancel(self.reader, held)
        with patch(
            "django.utils.timezone.now",
            return_value=held.expires_at + timedelta(days=1),
        ):
            page = self.signed_in(self.reader).get(reverse("reservation_my"))
            self.assertEqual(self.deadline_text(page, held), local(held.expires_at))
            self.assertContains(page, "Cancelled")
            self.assertNotContains(page, "hours left")
            data = self.api(
                self.reader, "get", f"/api/v1/reservation/{held.pk}/"
            ).json()
            self.assertEqual(data["state"], "cancelled")
            self.assertEqual(parse_datetime(data["expires_at"]), held.expires_at)
