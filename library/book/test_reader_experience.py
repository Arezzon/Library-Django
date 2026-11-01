"""Reader entry points and browser rendering must work with real session auth."""

from django.test import TestCase

from authentication.models import CustomUser

from .models import Book
from .ratings import set_rating
from .testing import FakeEncoderMixin


class ReaderExperienceTests(FakeEncoderMixin, TestCase):
    def setUp(self):
        self.reader = CustomUser.objects.create_user(
            email="reader-experience@example.com",
            password="test-password",
            first_name="Reader",
            last_name="Test",
            middle_name="",
            is_active=True,
        )
        self.book = Book.objects.create(name="Available book", count=1)
        self.unavailable = Book.objects.create(name="Unavailable book", count=0)
        self.client.force_login(self.reader)

    def test_recommendations_page_uses_available_owned_service_and_live_state(self):
        page = self.client.get("/book/recommendations/")
        self.assertContains(page, 'href="/book/recommendations/"')
        self.assertContains(page, 'href="/assistant/" class="nav-link">Assistant')
        self.assertEqual([b.pk for b in page.context["books"]], [self.book.pk])
        self.assertContains(page, "An available pick to help you get started.")
        self.assertNotContains(page, self.unavailable.name)
        self.assertIn("no-store", page["Cache-Control"])
        other = CustomUser.objects.create_user(
            email="other-experience@example.com",
            password="test-password",
            first_name="Other",
            last_name="Reader",
            middle_name="",
            is_active=True,
        )
        set_rating(other, self.book.pk, 1)
        self.assertContains(self.client.get("/book/recommendations/"), self.book.name)
        set_rating(self.reader, self.book.pk, 5)
        self.assertContains(
            self.client.get("/book/recommendations/"),
            "No available recommendations yet",
        )
        set_rating(self.reader, self.book.pk, None)
        self.book.count = 0
        self.book.save(update_fields=["count"])
        self.assertContains(
            self.client.get("/book/recommendations/"),
            "No available recommendations yet",
        )
        self.client.logout()
        self.assertEqual(self.client.get("/book/recommendations/").status_code, 302)

    def test_recommendation_reason_uses_own_rating_in_the_site_language(self):
        seed = Book.objects.create(name="My rated seed", count=1)
        set_rating(self.reader, seed.pk, 5)
        response = self.client.get("/book/recommendations/")
        self.assertContains(response, "Because you rated “My rated seed” highly.")
        self.assertNotIn(seed.pk, [b.pk for b in response.context["books"]])

    def test_service_apis_render_html_for_a_signed_in_browser(self):
        for path in (
            "/api/v1/books/recommendations/?limit=5",
            "/api/v1/books/search/?q=book",
            f"/api/v1/books/{self.book.pk}/rating/",
            f"/api/v1/books/{self.book.pk}/rating-summary/",
            f"/api/v1/books/{self.book.pk}/preferences/",
            "/api/v1/me/book-preferences/",
        ):
            with self.subTest(path=path):
                response = self.client.get(path, HTTP_ACCEPT="text/html")
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response["Content-Type"])
