"""The site's own "not found" page, also for staff pages a reader opens (KAN-79, KAN-80).

The test runner always runs with DEBUG off, as production does, so Django renders
404.html instead of its debug page.
"""

from django.test import Client, TestCase

from book.testing import FakeEncoderMixin

from .models import ROLE_LIBRARIAN
from .test_access import account

UNKNOWN = "/no-such-page/"
DESK = "/order/reservations/desk/"
HEADING = "We can't find this page."


class NotFoundPageTests(FakeEncoderMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reader = account("lost-reader@example.com")
        cls.librarian = account("lost-librarian@example.com", ROLE_LIBRARIAN)

    def signed_in(self, user=None):
        client = Client()
        if user is not None:
            client.force_login(user)
        return client

    def assertNotFoundPage(self, response):
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")
        self.assertContains(
            response, "<title>Page Not Found | LibrarySys</title>", status_code=404
        )
        self.assertContains(response, HEADING, status_code=404)
        self.assertContains(
            response,
            '<a href="/" class="btn-primary mt-6">Go to the home page</a>',
            status_code=404,
        )

    def test_an_unknown_address_gets_the_sites_page_for_everyone(self):
        for user in (None, self.reader, self.librarian):
            with self.subTest(user=user and user.email):
                response = self.signed_in(user).get(UNKNOWN)
                self.assertNotFoundPage(response)
                # The address is not echoed, so a hidden page looks the same.
                self.assertNotContains(response, "no-such-page", status_code=404)

    def test_each_caller_keeps_their_navigation(self):
        anonymous = self.signed_in().get(UNKNOWN)
        self.assertContains(anonymous, ">Log In</a>", status_code=404)
        reader = self.signed_in(self.reader).get(UNKNOWN)
        self.assertContains(reader, self.reader.email, status_code=404)
        self.assertNotContains(reader, f'href="{DESK}"', status_code=404)
        librarian = self.signed_in(self.librarian).get(UNKNOWN)
        self.assertContains(librarian, f'href="{DESK}"', status_code=404)

    def test_a_reader_on_a_staff_page_gets_the_same_page(self):
        # KAN-80, option 1: the page does not confirm that the address exists.
        self.assertNotFoundPage(self.signed_in(self.reader).get(DESK))

    def test_an_anonymous_caller_is_still_sent_to_sign_in(self):
        self.assertRedirects(
            self.signed_in().get(DESK),
            f"/authentication/login/?next={DESK}",
            fetch_redirect_response=False,
        )

    def test_a_librarian_still_opens_the_staff_page(self):
        self.assertEqual(self.signed_in(self.librarian).get(DESK).status_code, 200)
