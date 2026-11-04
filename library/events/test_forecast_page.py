"""The Forecast tab (KAN-35, docs/ba/demand-forecast.md)."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from authentication.models import ROLE_ADMINISTRATOR, ROLE_LIBRARIAN, CustomUser
from book.models import Book
from book.testing import FakeEncoderMixin
from library.testing import assert_same_query_count

from .test_overview import NOW, kyiv, loan, view

URL = "/events/forecast/"


def account(email, role=0):
    return CustomUser.objects.create_user(
        email=email,
        password="forecast-page-password",
        first_name="Forecast",
        middle_name="",
        last_name="Visitor",
        is_active=True,
        role=role,
    )


class ForecastAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reader = account("fp-reader@example.com")
        cls.librarian = account("fp-lib@example.com", ROLE_LIBRARIAN)
        cls.administrator = account("fp-admin@example.com", ROLE_ADMINISTRATOR)

    def test_anonymous_is_sent_to_sign_in(self):
        self.assertRedirects(
            self.client.get(URL),
            "/authentication/login/?next=/events/forecast/",
            fetch_redirect_response=False,
        )

    def test_a_reader_gets_the_not_found_page(self):
        self.client.force_login(self.reader)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")
        self.assertNotContains(response, "Book demand forecast", status_code=404)

    def test_librarians_and_administrators_see_the_third_tab(self):
        for user in (self.librarian, self.administrator):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                response = self.client.get(URL)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "<h1", count=1)
                self.assertContains(response, 'aria-current="page">Forecast')
        overview = self.client.get(reverse("events_dashboard"))
        self.assertContains(overview, f'href="{URL}"')

    def test_an_empty_library_explains_instead_of_an_empty_table(self):
        self.client.force_login(self.librarian)
        response = self.client.get(URL)
        self.assertContains(response, "No loans, reservations or tracked activity yet.")
        self.assertNotContains(response, "Books by demand")
        self.assertContains(response, "How the forecast works")


class ForecastPageTests(FakeEncoderMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.librarian = account("fp-data-lib@example.com", ROLE_LIBRARIAN)
        cls.readers = [account(f"fp-reader-{i}@example.com") for i in range(4)]
        cls.long_loans = Book.objects.create(name="Long loans", count=1)
        for reader, day in zip(cls.readers, (7, 9, 11), strict=False):
            loan(
                reader, cls.long_loans, kyiv(2026, 10, day), returned=kyiv(2026, 11, 3)
            )
        cls.quick = Book.objects.create(name="Quick read", count=2)
        loan(cls.readers[3], cls.quick, kyiv(2026, 10, 30), returned=kyiv(2026, 11, 2))
        view(cls.quick.pk, kyiv(2026, 11, 1), cls.readers[0])

    def setUp(self):
        self.client.force_login(self.librarian)
        patcher = patch("events.forecast.timezone.now", return_value=NOW)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_rows_rank_books_and_recommend_purchases(self):
        response = self.client.get(URL)
        rows = response.context["rows"]
        self.assertEqual([row["title"] for row in rows], ["Long loans", "Quick read"])
        self.assertEqual(rows[0]["recommendation"], "Buy 2")
        self.assertEqual(rows[1]["recommendation"], "Enough")
        self.assertEqual(rows[0]["trend_text"], "No earlier activity")
        self.assertContains(response, "Buy 2")
        self.assertContains(response, f'href="/book/{self.long_loans.pk}/"')

    def test_tiles_sum_up_the_purchases(self):
        tiles = dict(self.client.get(URL).context["tiles"])
        self.assertEqual(
            tiles, {"Books to buy": 1, "Copies to buy": 2, "Rising demand": 0}
        )

    def test_each_row_explains_its_scores_behind_a_disclosure(self):
        page = self.client.get(URL).content.decode()
        self.assertIn("How the forecast for Long loans is made", page)
        self.assertIn("Loans 3 (previous window 0): 3 issued, 0 on loan", page)
        self.assertIn("Stock pressure 0 (now)", page)
        self.assertIn("Loans last 25 days on average", page)
        self.assertIn("3 copies needed for 3 forecast loans.", page)

    def test_the_recipe_shows_the_weights_in_use(self):
        response = self.client.get(URL)
        self.assertContains(response, "0.4 × loans + 0.25 × reservations")
        self.assertContains(response, "0.6 × “Reserve” presses")

    def test_the_page_holds_no_reader_data(self):
        page = self.client.get(URL).content.decode()
        for reader in self.readers:
            self.assertNotIn(reader.email, page)
        self.assertNotIn("Forecast Visitor", page)


class ForecastQueryTests(FakeEncoderMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.librarian = account("fp-query-lib@example.com", ROLE_LIBRARIAN)
        cls.reader = account("fp-query-reader@example.com")

    def add_books(self, count):
        for _ in range(count):
            book = Book.objects.create(name=f"Counted {Book.objects.count()}", count=2)
            loan(self.reader, book, timezone.now() - timedelta(days=3))
            view(book.pk, timezone.now() - timedelta(days=1), self.reader)

    def test_the_page_uses_a_fixed_number_of_queries(self):
        self.client.force_login(self.librarian)
        response = assert_same_query_count(self, self.client, URL, self.add_books)
        self.assertEqual(len(response.context["rows"]), 25)
