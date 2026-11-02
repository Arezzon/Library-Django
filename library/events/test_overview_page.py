"""The library overview page (KAN-54, docs/ba/analytics-dashboard.md)."""

import re
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from authentication.models import ROLE_ADMINISTRATOR, ROLE_LIBRARIAN, CustomUser
from book.models import Book
from book.testing import FakeEncoderMixin
from library.testing import assert_same_query_count
from order.models import Order

from .models import EventType, UserEvent
from .test_overview import NOW, kyiv, loan, view

URL = "/events/"


def account(email, role=0):
    return CustomUser.objects.create_user(
        email=email,
        password="overview-page-password",
        first_name="Page",
        middle_name="",
        last_name="Reader",
        is_active=True,
        role=role,
    )


class OverviewAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reader = account("page-reader@example.com")
        cls.librarian = account("page-lib@example.com", ROLE_LIBRARIAN)
        cls.administrator = account("page-admin@example.com", ROLE_ADMINISTRATOR)

    def test_anonymous_is_sent_to_sign_in(self):
        self.assertRedirects(
            self.client.get(URL),
            "/authentication/login/?next=/events/",
            fetch_redirect_response=False,
        )

    def test_a_reader_gets_the_forbidden_page_without_figures(self):
        self.client.force_login(self.reader)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, "Library overview", status_code=403)

    def test_librarians_and_administrators_see_the_overview_and_its_tabs(self):
        for user in (self.librarian, self.administrator):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                response = self.client.get(URL)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "<h1", count=1)
                self.assertContains(response, "Library overview")
                self.assertContains(response, f'href="{reverse("events_activity")}"')
                self.assertContains(response, 'aria-current="page">Overview')

    def test_the_activity_log_is_the_second_tab(self):
        self.client.force_login(self.librarian)
        response = self.client.get(reverse("events_activity"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Activity Analytics")
        self.assertContains(response, 'aria-current="page">Activity log')
        self.assertContains(response, f'href="{URL}"')


class EmptyOverviewPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.librarian = account("empty-lib@example.com", ROLE_LIBRARIAN)

    def test_an_empty_library_says_so_instead_of_showing_a_chart(self):
        self.client.force_login(self.librarian)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No loans, reservations or tracked activity yet.")
        self.assertContains(response, "No loans in this period.", count=2)
        self.assertContains(response, "No tracked book views in this period.")
        self.assertContains(response, "No comparison with the previous 30 days")

    def test_every_period_can_be_chosen_and_an_unknown_one_falls_back(self):
        self.client.force_login(self.librarian)
        for key in ("7d", "30d", "90d", "12m"):
            with self.subTest(period=key):
                response = self.client.get(URL, {"period": key})
                self.assertEqual(response.context["period"]["key"], key)
                self.assertContains(
                    response, f'<option value="{key}" selected>', html=False
                )
        response = self.client.get(URL, {"period": "1y"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["period"]["key"], "30d")


class OverviewPageTests(FakeEncoderMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.librarian = account("data-lib@example.com", ROLE_LIBRARIAN)
        cls.reader = account("data-reader@example.com")
        cls.book = Book.objects.create(name="Borrowed classic", count=3)
        loan(cls.reader, cls.book, kyiv(2026, 10, 20), returned=kyiv(2026, 10, 25))
        loan(cls.reader, cls.book, kyiv(2026, 11, 2))
        view(cls.book.pk, kyiv(2026, 11, 2), cls.reader)
        view(424_242, kyiv(2026, 11, 3), cls.reader)
        UserEvent.objects.create(
            user=cls.reader,
            event_type=EventType.SEARCH,
            source="server",
            properties={"query": "secret search text"},
            occurred_at=kyiv(2026, 11, 3),
        )

    def setUp(self):
        self.client.force_login(self.librarian)
        patcher = patch("events.overview.timezone.now", return_value=NOW)
        patcher.start()
        self.addCleanup(patcher.stop)

    def get(self, **query):
        return self.client.get(URL, query)

    def test_tiles_show_values_and_hide_details_behind_an_info_control(self):
        page = self.get(period="7d").content.decode()
        self.assertIn("Loans issued", page)
        self.assertIn("<summary", page)
        self.assertIn("About loans issued", page)
        # Loans started 20 Oct, so the previous 7 days (22–28 Oct) are covered:
        # one loan now against none then, and no return now against one then.
        self.assertIn("+1 against the previous 7 days, which had none.", page)
        self.assertIn("−1 (−100%)", page)
        self.assertIn("−1 (−100%) against the previous 7 days, which had 1.", page)

    def test_the_notice_names_where_each_history_starts(self):
        response = self.get(period="30d")
        self.assertContains(response, "Book views are tracked from 2 Nov 2026")
        self.assertContains(response, "Reservations: none yet")
        self.assertNotContains(self.get(period="7d"), "Loan history starts")
        self.assertContains(self.get(period="12m"), "Loan history starts 20 Oct 2026")

    def test_the_chart_has_a_table_with_the_same_numbers(self):
        response = self.get(period="12m")
        page = response.content.decode()
        table = re.search(
            r"<caption[^>]*>Loans and returns per month</caption>(.*?)</table>",
            page,
            re.S,
        )
        self.assertIsNotNone(table)
        rows = re.findall(r"<tr>(.*?)</tr>", table.group(1), re.S)
        self.assertEqual(len(rows), 13)  # the header and 12 months
        self.assertIn("Aug 2026", table.group(1))
        self.assertIn("No data", table.group(1))
        october = re.search(r"Oct 2026</th><td>(\d+)</td><td>(\d+)</td>", page)
        self.assertEqual(october.groups(), ("1", "1"))

    def test_top_lists_link_existing_books_and_name_deleted_ones(self):
        response = self.get(period="7d")
        self.assertContains(response, f'href="/book/{self.book.pk}/"', count=2)
        self.assertContains(response, "Deleted book #424242")
        self.assertNotContains(response, 'href="/book/424242/"')
        self.assertContains(response, "2 / 3")  # copies available / total

    def test_the_page_holds_no_reader_data(self):
        page = self.get(period="12m").content.decode()
        self.assertNotIn(self.reader.email, page)
        self.assertNotIn("Page Reader", page)
        self.assertNotIn("secret search text", page)


class OverviewQueryTests(FakeEncoderMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.librarian = account("query-lib@example.com", ROLE_LIBRARIAN)
        cls.reader = account("query-reader@example.com")

    def add_loans(self, count):
        for index in range(count):
            book = Book.objects.create(name=f"Counted {Book.objects.count()}", count=1)
            Order.create(self.reader, book, timezone.now() + timedelta(days=14))
            view(book.pk, timezone.now() - timedelta(days=index % 5), self.reader)

    def test_the_overview_uses_a_fixed_number_of_queries(self):
        self.client.force_login(self.librarian)
        response = assert_same_query_count(
            self, self.client, URL + "?period=30d", self.add_loans
        )
        self.assertEqual(len(response.context["top_borrowed"]), 10)
