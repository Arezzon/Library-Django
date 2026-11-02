"""Library overview metrics and API (KAN-34, docs/ba/analytics-dashboard.md)."""

from datetime import date, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from authentication.models import ROLE_ADMINISTRATOR, ROLE_LIBRARIAN, CustomUser
from book.models import Book
from book.testing import FakeEncoderMixin
from order.models import Order, Reservation, ReservationState

from .models import EventType, UserEvent
from .overview import library_overview, resolve_period

KYIV = ZoneInfo("Europe/Kyiv")
# A Wednesday, after the switch to winter time (EET, UTC+2).
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=KYIV)
URL = "/api/v1/analytics/overview/"


def kyiv(year, month, day, hour=12, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=KYIV)


def account(email, role=0):
    return CustomUser.objects.create_user(
        email=email,
        password="overview-password",
        first_name="Overview",
        middle_name="",
        last_name="Test",
        is_active=True,
        role=role,
    )


def loan(user, book, issued, returned=None, due=None):
    order = Order(user=user, book=book, plated_end_at=due or issued + timedelta(14))
    order.save()
    Order.objects.filter(pk=order.pk).update(created_at=issued)
    if returned is not None:
        order.refresh_from_db()
        order.end_at = returned
        order.save()
    return order


def view(book_id, at, user=None, event_type=EventType.BOOK_VIEW):
    return UserEvent.objects.create(
        user=user,
        event_type=event_type,
        source="server",
        book_id=book_id,
        occurred_at=at,
    )


class PeriodTests(TestCase):
    def test_days_end_today_in_kyiv_time(self):
        period = resolve_period("7d", NOW)
        self.assertEqual(period.start, date(2026, 10, 29))
        self.assertEqual(period.end, date(2026, 11, 5))
        self.assertEqual(period.previous_start, date(2026, 10, 22))
        self.assertEqual(period.bucket, "day")
        self.assertEqual(len(period.buckets()), 7)
        period = resolve_period("30d", NOW)
        self.assertEqual(period.start, date(2026, 10, 6))
        self.assertEqual(period.previous_start, date(2026, 9, 6))
        self.assertEqual(len(period.buckets()), 30)

    def test_ninety_days_are_thirteen_weeks_from_monday(self):
        period = resolve_period("90d", NOW)
        self.assertEqual(period.start, date(2026, 8, 10))
        self.assertEqual(period.start.weekday(), 0)
        self.assertEqual(period.previous_start, date(2026, 5, 11))
        self.assertEqual(period.bucket, "week")
        buckets = period.buckets()
        self.assertEqual(len(buckets), 13)
        self.assertEqual(buckets[-1], date(2026, 11, 2))

    def test_twelve_months_start_on_the_first_of_a_month(self):
        period = resolve_period("12m", NOW)
        self.assertEqual(period.start, date(2025, 12, 1))
        self.assertEqual(period.previous_start, date(2024, 12, 1))
        self.assertEqual(period.bucket, "month")
        buckets = period.buckets()
        self.assertEqual(len(buckets), 12)
        self.assertEqual(buckets[0], date(2025, 12, 1))
        self.assertEqual(buckets[-1], date(2026, 11, 1))

    def test_an_unknown_period_is_refused(self):
        with self.assertRaises(ValueError):
            resolve_period("1y", NOW)


class EmptyOverviewTests(TestCase):
    def test_an_empty_library_gives_zeros_and_no_history(self):
        overview = library_overview("30d", 10, now=NOW)
        self.assertEqual(
            overview["history_start"],
            {"loans": None, "reservations": None, "events": None},
        )
        summary = overview["summary"]
        for key in ("loans_issued", "returns", "active_borrowers", "book_views"):
            with self.subTest(metric=key):
                self.assertEqual(summary[key], {"value": 0, "previous": None})
        self.assertEqual(summary["overdue_now"]["value"], 0)
        self.assertEqual(summary["overdue_now"]["readers"], 0)
        self.assertEqual(summary["reservations"]["value"], 0)
        self.assertEqual(len(overview["series"]), 30)
        self.assertTrue(all(not row["covered"] for row in overview["series"]))
        self.assertTrue(all(row["loans"] == 0 for row in overview["series"]))
        self.assertEqual(overview["top_borrowed"], [])
        self.assertEqual(overview["top_viewed"], [])
        self.assertEqual(
            overview["readers"],
            {
                "active": 0,
                "first_time": 0,
                "returning": 0,
                "loans_per_borrower": {"1": 0, "2-3": 0, "4+": 0},
                "with_overdue": 0,
                "searches": 0,
            },
        )


class OverviewTests(FakeEncoderMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ann = account("ann@example.com")
        cls.bob = account("bob@example.com")
        cls.librarian = account("lib@example.com", ROLE_LIBRARIAN)
        cls.dune = Book.objects.create(name="Dune", count=5)
        cls.emma = Book.objects.create(name="Emma", count=5)
        cls.atlas = Book.objects.create(name="Atlas", count=1)
        # Previous 7 days (22–28 Oct); 23:30 on the 28th is still the 28th in Kyiv.
        loan(cls.ann, cls.dune, kyiv(2026, 10, 20), returned=kyiv(2026, 10, 25))
        loan(cls.ann, cls.emma, kyiv(2026, 10, 28, 23, 30), returned=kyiv(2026, 11, 1))
        # This period (29 Oct – 4 Nov); 00:10 on the 29th is 22:10 UTC on the 28th.
        loan(cls.ann, cls.dune, kyiv(2026, 10, 29, 0, 10), returned=kyiv(2026, 11, 2))
        loan(cls.bob, cls.dune, kyiv(2026, 11, 2))
        loan(cls.bob, cls.emma, kyiv(2026, 11, 3))
        # Due before NOW and not returned: overdue, issued before both periods.
        loan(cls.librarian, cls.atlas, kyiv(2026, 9, 1), due=kyiv(2026, 9, 15))
        view(cls.emma.pk, kyiv(2026, 10, 30), cls.ann)
        view(cls.emma.pk, kyiv(2026, 10, 31), cls.bob)
        view(cls.emma.pk, kyiv(2026, 11, 1), cls.bob)
        view(cls.dune.pk, kyiv(2026, 11, 1), cls.bob)
        view(cls.dune.pk, kyiv(2026, 10, 25), cls.bob)
        view(999_999, kyiv(2026, 11, 2), cls.bob)  # a since-deleted book
        view(None, kyiv(2026, 11, 3), cls.bob, EventType.SEARCH)
        view(None, kyiv(2026, 10, 1), cls.ann, EventType.LOGIN)
        cls.reservations = [
            Reservation.objects.create(
                user=cls.ann, book=cls.emma, created_at=kyiv(2026, 11, 3)
            ),
            Reservation.objects.create(
                user=cls.bob, book=cls.atlas, created_at=kyiv(2026, 10, 30)
            ),
        ]
        cancelled = Reservation.objects.create(
            user=cls.librarian, book=cls.dune, created_at=kyiv(2026, 11, 3)
        )
        cancelled.change_state(ReservationState.CANCELLED, NOW)
        cancelled.cancelled_by = cls.librarian
        cancelled.cancelled_at = NOW
        cancelled.save()

    def overview(self, period="7d", limit=10):
        return library_overview(period, limit, now=NOW)

    def test_history_starts_at_each_source_first_record(self):
        self.assertEqual(
            self.overview()["history_start"],
            {
                "loans": "2026-09-01",
                "reservations": "2026-10-30",
                "events": "2026-10-01",
            },
        )

    def test_summary_counts_this_and_the_previous_period(self):
        summary = self.overview()["summary"]
        self.assertEqual(summary["loans_issued"], {"value": 3, "previous": 1})
        self.assertEqual(summary["returns"], {"value": 2, "previous": 1})
        self.assertEqual(summary["active_borrowers"], {"value": 2, "previous": 1})
        self.assertEqual(summary["book_views"], {"value": 5, "previous": 1})

    def test_overdue_is_a_snapshot_including_staff(self):
        overdue = self.overview()["summary"]["overdue_now"]
        self.assertEqual(overdue["value"], 1)
        self.assertEqual(overdue["readers"], 1)
        self.assertEqual(overdue["as_of"], "2026-11-04T12:00:00+02:00")

    def test_reservations_report_their_state_now(self):
        reservations = self.overview()["summary"]["reservations"]
        # The bob/atlas hold was made 30 Oct, so its 48 hours are over by NOW.
        self.assertEqual(reservations["value"], 3)
        self.assertEqual(reservations["active"], 1)
        self.assertEqual(reservations["expired"], 1)
        self.assertEqual(reservations["cancelled"], 1)
        self.assertEqual(reservations["issued"], 0)
        # History starts 30 Oct, inside the previous 7 days: no comparison.
        self.assertIsNone(reservations["previous"])

    def test_previous_is_hidden_when_history_starts_inside_it(self):
        overview = self.overview("30d")
        # Loans start 1 Sep; the previous 30 days (6 Sep – 5 Oct) are covered,
        # and nothing was issued in them: zero, not unknown.
        self.assertEqual(overview["summary"]["loans_issued"]["previous"], 0)
        # Events start 1 Oct, inside the previous 30 days (6 Sep – 5 Oct).
        self.assertIsNone(overview["summary"]["book_views"]["previous"])

    def test_series_buckets_loans_and_returns_by_kyiv_day(self):
        series = self.overview()["series"]
        self.assertEqual(
            [row["start"] for row in series],
            [f"2026-{m:02}-{d:02}" for m, d in ((10, 29), (10, 30), (10, 31))]
            + [f"2026-11-{d:02}" for d in range(1, 5)],
        )
        by_day = {row["start"]: row for row in series}
        self.assertEqual(by_day["2026-10-29"]["loans"], 1)
        self.assertEqual(by_day["2026-11-02"]["loans"], 1)
        self.assertEqual(by_day["2026-11-02"]["returns"], 1)
        self.assertEqual(by_day["2026-11-01"]["returns"], 1)
        self.assertEqual(sum(row["loans"] for row in series), 3)
        self.assertTrue(all(row["covered"] for row in series))
        self.assertEqual([row["partial"] for row in series], [False] * 6 + [True])

    def test_series_marks_buckets_before_history_as_not_covered(self):
        series = self.overview("12m")["series"]
        covered = {row["start"]: row["covered"] for row in series}
        self.assertFalse(covered["2026-08-01"])
        self.assertTrue(covered["2026-09-01"])
        self.assertEqual(
            {row["start"]: row["loans"] for row in series}["2026-10-01"], 3
        )

    def test_a_return_dated_before_any_issue_starts_the_history(self):
        loan(self.bob, self.emma, kyiv(2026, 9, 10), returned=kyiv(2026, 8, 20))
        overview = self.overview("12m")
        self.assertEqual(overview["history_start"]["loans"], "2026-08-20")
        august = {row["start"]: row for row in overview["series"]}["2026-08-01"]
        self.assertEqual(august["returns"], 1)
        self.assertTrue(august["covered"])

    def test_weekly_series_groups_from_monday(self):
        series = self.overview("90d")["series"]
        loans = {row["start"]: row["loans"] for row in series}
        self.assertEqual(loans["2026-10-26"], 2)  # 28 and 29 Oct
        self.assertEqual(loans["2026-11-02"], 2)

    def test_top_borrowed_ranks_by_loans_then_views(self):
        top = self.overview()["top_borrowed"]
        # Dune and Emma have 2 and 1 loans this week.
        self.assertEqual([row["title"] for row in top], ["Dune", "Emma"])
        dune = top[0]
        self.assertEqual(dune["loans"], 2)
        self.assertEqual(dune["views"], 1)
        self.assertEqual(dune["copies"], 5)
        self.assertEqual(dune["available"], 4)  # bob's loan; the hold is cancelled
        emma = top[1]
        self.assertEqual(emma["available"], 3)  # bob's loan and ann's active hold
        self.assertEqual(top[0]["book_id"], self.dune.pk)

    def test_top_borrowed_breaks_equal_loans_by_views(self):
        bach = Book.objects.create(name="Bach", count=2)
        loan(self.ann, bach, kyiv(2026, 11, 4, 9))
        top = self.overview()["top_borrowed"]
        # Bach and Emma both have 1 loan; Emma's 3 views put it ahead of Bach's
        # none, although Bach comes first by title.
        self.assertEqual([row["title"] for row in top], ["Dune", "Emma", "Bach"])
        self.assertEqual(top[2]["views"], 0)

    def test_top_viewed_keeps_deleted_books_without_a_title(self):
        top = self.overview()["top_viewed"]
        self.assertEqual(
            [(row["book_id"], row["views"]) for row in top],
            [(self.emma.pk, 3), (self.dune.pk, 1), (999_999, 1)],
        )
        self.assertEqual(top[0]["title"], "Emma")
        self.assertEqual(top[0]["loans"], 1)
        self.assertIsNone(top[2]["title"])
        self.assertIsNone(top[2]["loans"])

    def test_limit_cuts_both_lists(self):
        overview = self.overview(limit=1)
        self.assertEqual(len(overview["top_borrowed"]), 1)
        self.assertEqual(len(overview["top_viewed"]), 1)

    def test_readers_are_counted_without_identities(self):
        readers = self.overview()["readers"]
        # Ann borrowed before (20 Oct); Bob's first loan is this week.
        self.assertEqual(readers["active"], 2)
        self.assertEqual(readers["first_time"], 1)
        self.assertEqual(readers["returning"], 1)
        self.assertEqual(readers["loans_per_borrower"], {"1": 1, "2-3": 1, "4+": 0})
        self.assertEqual(readers["with_overdue"], 1)
        self.assertEqual(readers["searches"], 1)

    def test_the_overview_holds_no_personal_data(self):
        text = str(self.overview())
        for user in (self.ann, self.bob, self.librarian):
            with self.subTest(user=user.email):
                self.assertNotIn(user.email, text)
                self.assertNotIn("Overview Test", text)

    def test_query_count_does_not_grow_with_the_data(self):
        with CaptureQueriesContext(connection) as before:
            self.overview("30d")
        for index in range(5):
            book = Book.objects.create(name=f"Extra {index}", count=3)
            loan(self.librarian, book, kyiv(2026, 10, 20 + index))
            view(book.pk, kyiv(2026, 10, 20 + index), self.bob)
        with CaptureQueriesContext(connection) as after:
            self.overview("30d")
        self.assertEqual(len(after), len(before))


class OverviewApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reader = account("api-reader@example.com")
        cls.librarian = account("api-lib@example.com", ROLE_LIBRARIAN)
        cls.administrator = account("api-admin@example.com", ROLE_ADMINISTRATOR)

    def get(self, user=None, query=""):
        client = APIClient()
        if user is not None:
            client.force_login(user)
        return client.get(URL + query)

    def test_anonymous_is_asked_to_sign_in(self):
        response = self.get()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(set(response.json()), {"detail"})

    def test_a_reader_is_refused_without_figures(self):
        response = self.get(self.reader)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(set(response.json()), {"detail"})

    def test_librarians_and_administrators_get_the_overview(self):
        for user in (self.librarian, self.administrator):
            with self.subTest(user=user.email):
                response = self.get(user)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Cache-Control"], "private, no-store")
                data = response.json()
                self.assertEqual(data["period"]["key"], "30d")
                self.assertEqual(data["period"]["timezone"], "Europe/Kyiv")
                self.assertEqual(
                    set(data),
                    {
                        "period",
                        "history_start",
                        "summary",
                        "series",
                        "top_borrowed",
                        "top_viewed",
                        "readers",
                    },
                )

    def test_every_period_is_accepted(self):
        for key, bucket in (
            ("7d", "day"),
            ("30d", "day"),
            ("90d", "week"),
            ("12m", "month"),
        ):
            with self.subTest(period=key):
                response = self.get(self.librarian, f"?period={key}&limit=5")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["period"]["bucket"], bucket)

    def test_invalid_parameters_are_refused(self):
        for query in (
            "?period=1y",
            "?period=30",
            "?limit=0",
            "?limit=21",
            "?limit=ten",
            "?user_id=1",
        ):
            with self.subTest(query=query):
                self.assertEqual(self.get(self.librarian, query).status_code, 400)

    def test_the_view_uses_the_current_time(self):
        with patch("events.overview.timezone.now", return_value=NOW):
            data = self.get(self.librarian, "?period=7d").json()
        self.assertEqual(data["period"]["start"], "2026-10-29")
        self.assertEqual(data["period"]["end"], "2026-11-04")
