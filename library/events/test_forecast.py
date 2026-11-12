"""Book demand forecast (KAN-35, docs/ba/demand-forecast.md)."""

from datetime import timedelta

from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from authentication.models import ROLE_LIBRARIAN, CustomUser
from book.models import Book, BookLike, BookRating, FavoriteBook
from book.testing import FakeEncoderMixin
from order.models import Reservation, ReservationState

from .forecast import copies_needed, demand_forecast, forecast_loans, trend
from .models import EventType
from .test_overview import NOW, kyiv, loan, view


def account(email, role=0):
    return CustomUser.objects.create_user(
        email=email,
        password="forecast-password",
        first_name="Forecast",
        middle_name="",
        last_name="Reader",
        is_active=True,
        role=role,
    )


def hold(user, book, created, state=None, by=None):
    reservation = Reservation.objects.create(user=user, book=book, created_at=created)
    if state is not None:
        reservation.change_state(state, created + timedelta(hours=1))
        if state == ReservationState.CANCELLED:
            reservation.cancelled_by = by
            reservation.cancelled_at = created + timedelta(hours=1)
        reservation.save()
    return reservation


def dated(model, at, **fields):
    row = model.objects.create(**fields)
    stamps = {"created_at": at}
    if model is BookRating:
        stamps["updated_at"] = at
    model.objects.filter(pk=row.pk).update(**stamps)
    return row


class FormulaTests(SimpleTestCase):
    def test_trend_is_the_ratio_limited_to_half_and_double(self):
        self.assertEqual(trend(30, 20), 1.5)
        self.assertEqual(trend(90, 44), 2.0)
        self.assertEqual(trend(10, 40), 0.5)
        self.assertEqual(trend(0, 40), 0.5)

    def test_without_previous_activity_the_trend_is_one(self):
        self.assertEqual(trend(5, 0), 1.0)
        self.assertEqual(trend(0, 0), 1.0)
        self.assertEqual(trend(5, -2), 1.0)

    def test_forecast_rounds_half_up(self):
        self.assertEqual(forecast_loans(3, 1.5), 5)
        self.assertEqual(forecast_loans(14, 1.2), 17)
        self.assertEqual(forecast_loans(0, 2.0), 0)

    def test_copies_needed_round_up_from_the_loan_length(self):
        # A copy serves 30 / 14 loans a month, so 17 loans need 7.93 copies.
        self.assertEqual(copies_needed(17, 14), 8)
        self.assertEqual(copies_needed(15, 14), 7)
        self.assertEqual(copies_needed(1, 3), 1)
        self.assertEqual(copies_needed(0, 14), 0)


class ForecastTests(FakeEncoderMixin, TestCase):
    """Hand-computed figures for a window of 6 Oct – 4 Nov and a previous one of
    6 Sep – 5 Oct 2026, both in Kyiv time."""

    @classmethod
    def setUpTestData(cls):
        cls.ann = account("ann-forecast@example.com")
        cls.bob = account("bob-forecast@example.com")
        cls.cat = account("cat-forecast@example.com")
        cls.dan = account("dan-forecast@example.com")
        cls.librarian = account("lib-forecast@example.com", ROLE_LIBRARIAN)
        cls.atlas = Book.objects.create(name="Atlas", count=2)
        cls.dune = Book.objects.create(name="Dune", count=1)
        cls.emma = Book.objects.create(name="Emma", count=2)
        cls.quiet = Book.objects.create(name="Quiet", count=3)

        # Atlas loans: two issued in each window; L4 is still out, as is L3.
        loan(cls.ann, cls.atlas, kyiv(2026, 9, 20), returned=kyiv(2026, 9, 30))
        loan(cls.ann, cls.atlas, kyiv(2026, 10, 1))
        loan(cls.bob, cls.atlas, kyiv(2026, 10, 10), returned=kyiv(2026, 10, 14))
        loan(cls.cat, cls.atlas, kyiv(2026, 10, 20))
        # Atlas reservations: one in the previous window, then one of each outcome.
        hold(cls.bob, cls.atlas, kyiv(2026, 9, 25), ReservationState.ISSUED)
        hold(cls.ann, cls.atlas, kyiv(2026, 10, 12), ReservationState.ISSUED)
        hold(cls.bob, cls.atlas, kyiv(2026, 11, 3))  # active until 5 Nov
        hold(cls.cat, cls.atlas, kyiv(2026, 10, 15))  # past its deadline: expired
        hold(
            cls.dan,
            cls.atlas,
            kyiv(2026, 10, 25),
            ReservationState.CANCELLED,
            by=cls.dan,
        )
        hold(
            cls.ann,
            cls.atlas,
            kyiv(2026, 10, 28),
            ReservationState.CANCELLED,
            by=cls.librarian,
        )
        # Atlas interest: repeats on one day by one account count once.
        view(cls.atlas.pk, kyiv(2026, 10, 20, 10), cls.ann)
        view(cls.atlas.pk, kyiv(2026, 10, 20, 18), cls.ann)
        view(cls.atlas.pk, kyiv(2026, 10, 20), cls.bob)
        view(cls.atlas.pk, kyiv(2026, 10, 21), cls.ann)
        view(cls.atlas.pk, kyiv(2026, 10, 24, 9), None)
        view(cls.atlas.pk, kyiv(2026, 10, 24, 15), None)
        view(cls.atlas.pk, kyiv(2026, 10, 22), cls.ann, EventType.BOOK_CLICK)
        view(cls.atlas.pk, kyiv(2026, 10, 23, 9), cls.bob, EventType.BORROW_INTENT)
        view(cls.atlas.pk, kyiv(2026, 10, 23, 11), cls.bob, EventType.BORROW_INTENT)
        view(cls.atlas.pk, kyiv(2026, 9, 10), cls.ann)
        # Atlas preferences.
        dated(BookLike, kyiv(2026, 10, 30), user=cls.ann, book=cls.atlas)
        dated(FavoriteBook, kyiv(2026, 10, 31), user=cls.bob, book=cls.atlas)
        dated(BookRating, kyiv(2026, 10, 29), user=cls.cat, book=cls.atlas, value=5)
        dated(BookRating, kyiv(2026, 9, 15), user=cls.ann, book=cls.atlas, value=2)

        # Dune: one short loan and one view in the window.
        loan(cls.bob, cls.dune, kyiv(2026, 10, 30), returned=kyiv(2026, 11, 2))
        view(cls.dune.pk, kyiv(2026, 11, 1), cls.cat)
        # Emma: only a like in the previous window. Quiet: nothing at all.
        dated(BookLike, kyiv(2026, 9, 20), user=cls.cat, book=cls.emma)

    def forecast(self, **kwargs):
        return demand_forecast(now=NOW, **kwargs)

    def book(self, forecast, book):
        return next(row for row in forecast["books"] if row["book_id"] == book.pk)

    def test_the_windows_are_thirty_kyiv_days(self):
        window = self.forecast()["window"]
        self.assertEqual(
            window,
            {
                "start": "2026-10-06",
                "end": "2026-11-04",
                "previous_start": "2026-09-06",
            },
        )

    def test_only_books_with_activity_are_listed_in_demand_order(self):
        books = self.forecast()["books"]
        self.assertEqual([row["title"] for row in books], ["Atlas", "Dune", "Emma"])

    def test_loan_score_counts_issues_and_copies_out_at_each_window_end(self):
        loans = self.book(self.forecast(), self.atlas)["scores"]["loans"]
        self.assertEqual(loans["terms"], {"issued": 2, "on_loan": 2})
        self.assertEqual(loans["previous_terms"], {"issued": 2, "on_loan": 1})
        self.assertEqual((loans["current"], loans["previous"]), (3.0, 2.5))

    def test_reservation_score_weighs_each_outcome(self):
        holds = self.book(self.forecast(), self.atlas)["scores"]["reservations"]
        self.assertEqual(
            holds["terms"],
            {
                "issued": 1,
                "active": 1,
                "expired": 1,
                "cancelled_by_reader": 1,
                "cancelled_by_library": 1,
            },
        )
        self.assertEqual((holds["current"], holds["previous"]), (2.2, 1.0))

    def test_loans_and_reservations_outlive_their_accounts(self):
        # KAN-82: deleting the readers and the librarian keeps every loan and
        # reservation, and who cancelled each one.
        before = self.book(self.forecast(), self.atlas)["scores"]
        for user in (self.ann, self.bob, self.cat, self.dan, self.librarian):
            user.delete()
        after = self.book(self.forecast(), self.atlas)["scores"]
        for score in ("loans", "reservations"):
            with self.subTest(score=score):
                self.assertEqual(after[score], before[score])

    def test_interest_counts_each_kind_once_per_account_and_day(self):
        interest = self.book(self.forecast(), self.atlas)["scores"]["interest"]
        self.assertEqual(
            interest["terms"], {"book_view": 4, "book_click": 1, "borrow_intent": 1}
        )
        self.assertEqual((interest["current"], interest["previous"]), (1.2, 0.1))

    def test_preferences_add_likes_favourites_and_ratings_around_three(self):
        preferences = self.book(self.forecast(), self.atlas)["scores"]["preferences"]
        self.assertEqual(preferences["terms"], {"like": 1, "favorite": 1, "rating": 2})
        self.assertEqual((preferences["current"], preferences["previous"]), (2.1, -0.4))

    def test_stock_pressure_is_a_snapshot_of_copies_taken(self):
        atlas = self.book(self.forecast(), self.atlas)
        # Two loans out and bob's active hold take more than the two copies.
        self.assertEqual(
            atlas["scores"]["stock"]["terms"], {"utilisation": 1.0, "stock_out": 1}
        )
        self.assertEqual(atlas["scores"]["stock"]["current"], 6.0)
        self.assertIsNone(atlas["scores"]["stock"]["previous"])
        self.assertEqual((atlas["copies"], atlas["available"]), (2, 0))
        dune = self.book(self.forecast(), self.dune)
        self.assertEqual(dune["scores"]["stock"]["current"], 0.0)

    def test_demand_scales_each_score_against_the_catalog(self):
        forecast = self.forecast()
        self.assertEqual(self.book(forecast, self.atlas)["demand"], 100)
        # Dune: 0.40 × 1/3 of the top loan score + 0.15 × 0.1/1.2 of the top interest.
        self.assertEqual(self.book(forecast, self.dune)["demand"], 15)
        self.assertEqual(self.book(forecast, self.emma)["demand"], 0)

    def test_trend_forecast_and_copies(self):
        forecast = self.forecast()
        atlas = self.book(forecast, self.atlas)
        # A rose from 44.0 to 90: limited to double.
        self.assertEqual(atlas["trend"], 2.0)
        self.assertEqual(atlas["forecast"], 4)
        self.assertEqual(atlas["loan_days"], 7.0)  # returns after 10 and 4 days
        self.assertEqual((atlas["copies_needed"], atlas["to_buy"]), (1, 0))
        dune = self.book(forecast, self.dune)
        self.assertEqual((dune["trend"], dune["forecast"]), (1.0, 1))
        self.assertEqual(dune["loan_days"], 3.0)
        emma = self.book(forecast, self.emma)
        self.assertEqual((emma["trend"], emma["forecast"]), (0.5, 0))
        self.assertEqual(emma["loan_days"], 14.0)  # no returned loans: the default

    def test_a_book_short_of_copies_is_recommended_for_purchase(self):
        busy = Book.objects.create(name="Busy", count=1)
        for day in (8, 12, 16, 20, 24, 28):
            reader = account(f"busy-{day}@example.com")
            loan(reader, busy, kyiv(2026, 10, day), returned=kyiv(2026, 10, day + 3))
        row = self.book(self.forecast(), busy)
        # 6 loans, no previous activity: 6 forecast loans of 3 days fit one copy.
        self.assertEqual((row["forecast"], row["copies_needed"]), (6, 1))
        long_loans = Book.objects.create(name="Long loans", count=1)
        for day in (7, 9, 11):
            reader = account(f"long-{day}@example.com")
            loan(reader, long_loans, kyiv(2026, 10, day), returned=kyiv(2026, 11, 3))
        row = self.book(self.forecast(), long_loans)
        # 3 loans of about 25 days: a copy serves 1.2 a month, so 3 copies are needed.
        self.assertEqual((row["forecast"], row["copies_needed"]), (3, 3))
        self.assertEqual(row["to_buy"], 2)
        totals = self.forecast()["totals"]
        self.assertEqual(totals["books_to_buy"], 1)
        self.assertEqual(totals["copies_to_buy"], 2)

    def test_totals_count_rising_books(self):
        totals = self.forecast()["totals"]
        self.assertEqual(totals["rising"], 1)  # Atlas; Dune had nothing before
        self.assertEqual((totals["books_to_buy"], totals["copies_to_buy"]), (0, 0))

    def test_limit_cuts_the_list_but_not_the_totals(self):
        forecast = self.forecast(limit=1)
        self.assertEqual(len(forecast["books"]), 1)
        self.assertEqual(forecast["totals"]["rising"], 1)

    def test_the_forecast_holds_no_account_data(self):
        text = str(self.forecast())
        for user in (self.ann, self.bob, self.cat, self.dan, self.librarian):
            self.assertNotIn(user.email, text)
        self.assertNotIn("Forecast Reader", text)

    def test_query_count_does_not_grow_with_the_catalog(self):
        with CaptureQueriesContext(connection) as before:
            self.forecast()
        for index in range(5):
            reader = account(f"extra-{index}@example.com")
            book = Book.objects.create(name=f"Extra {index}", count=2)
            loan(reader, book, kyiv(2026, 10, 10 + index), returned=kyiv(2026, 10, 20))
            view(book.pk, kyiv(2026, 10, 12), reader)
            hold(reader, book, kyiv(2026, 10, 13), ReservationState.ISSUED)
            dated(BookLike, kyiv(2026, 10, 14), user=reader, book=book)
        with CaptureQueriesContext(connection) as after:
            self.forecast()
        self.assertEqual(len(after), len(before))


class EmptyForecastTests(TestCase):
    def test_an_empty_library_has_no_books_and_zero_totals(self):
        forecast = demand_forecast(now=NOW)
        self.assertEqual(forecast["books"], [])
        self.assertFalse(forecast["has_activity"])
        self.assertEqual(
            forecast["totals"], {"books_to_buy": 0, "copies_to_buy": 0, "rising": 0}
        )
