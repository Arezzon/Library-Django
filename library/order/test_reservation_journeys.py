"""The whole reservation journey from both sides of the desk, through the web and the
API (FR-019 to FR-021, research R17)."""

from datetime import timedelta
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.urls import reverse
from django.utils import dateformat, timezone

from audit.models import AuditEntry
from authentication.models import ROLE_LIBRARIAN, CustomUser
from book.models import Book
from book.testing import FakeEncoderMixin

from .models import Order, Reservation, ReservationState
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
            mine, "The 48 hours ended. Reserve it again if a copy is available."
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
