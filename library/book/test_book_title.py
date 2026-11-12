"""Every book has a title, in every channel (KAN-81, TD-29, GitHub issue #62)."""

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from authentication.models import ROLE_LIBRARIAN, CustomUser

from .models import Book
from .testing import FakeEncoderMixin

# An empty title, and one that is empty once its spaces are trimmed.
BLANK_TITLES = ["", "   "]


class BookTitleTests(FakeEncoderMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.librarian = CustomUser.objects.create_user(
            email="title-librarian@example.com",
            password="test-password",
            first_name="Title",
            middle_name="",
            last_name="Librarian",
            role=ROLE_LIBRARIAN,
            is_active=True,
        )
        cls.book = Book.objects.create(name="Kobzar", description="Poems", count=3)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.librarian)

    def assertUnchanged(self):
        self.assertEqual(Book.objects.count(), 1)
        self.assertEqual(Book.objects.get(pk=self.book.pk).name, "Kobzar")

    def api(self, method, path, body):
        return getattr(self.client, method)(path, body, content_type="application/json")

    # The web form

    def test_the_web_form_refuses_a_blank_title(self):
        for name in BLANK_TITLES:
            with self.subTest(name=name):
                response = self.client.post(
                    reverse("book_create"),
                    {"name": name, "description": "", "count": 1},
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("name", response.context["form"].errors)
        self.assertUnchanged()

    def test_the_web_form_marks_the_title_required(self):
        response = self.client.get(reverse("book_create"))
        self.assertTrue(response.context["form"].fields["name"].required)

    def test_the_web_form_still_creates_a_titled_book(self):
        response = self.client.post(
            reverse("book_create"), {"name": "Lisova pisnia", "count": 1}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Book.objects.filter(name="Lisova pisnia").exists())

    def test_editing_on_the_web_cannot_clear_the_title(self):
        for name in BLANK_TITLES:
            with self.subTest(name=name):
                response = self.client.post(
                    reverse("book_update", args=[self.book.pk]),
                    {"name": name, "description": "Poems", "count": 3},
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("name", response.context["form"].errors)
        self.assertUnchanged()

    # The API

    def test_the_api_refuses_a_blank_or_missing_title(self):
        for body in ({"name": ""}, {"name": "   "}, {}):
            with self.subTest(body=body):
                response = self.api(
                    "post", "/api/v1/book/", {"description": "", "count": 1, **body}
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("name", response.json())
        self.assertUnchanged()

    def test_the_api_still_creates_a_titled_book(self):
        response = self.api("post", "/api/v1/book/", {"name": "Zakhar Berkut"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["name"], "Zakhar Berkut")

    def test_editing_through_the_api_cannot_clear_the_title(self):
        path = f"/api/v1/book/{self.book.pk}/"
        for method in ("put", "patch"):
            for name in BLANK_TITLES:
                with self.subTest(method=method, name=name):
                    body = {"name": name, "description": "Poems", "count": 3}
                    response = self.api(method, path, body)
                    self.assertEqual(response.status_code, 400)
                    self.assertIn("name", response.json())
        self.assertUnchanged()

    def test_a_patch_without_a_title_keeps_it(self):
        response = self.api("patch", f"/api/v1/book/{self.book.pk}/", {"count": 4})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Book.objects.get(pk=self.book.pk).name, "Kobzar")

    # The admin site

    def test_the_admin_site_refuses_a_blank_title(self):
        response = self.client.post(
            "/admin/book/book/add/",
            {
                "name": "",
                "description": "",
                "count": 1,
                "order_set-TOTAL_FORMS": "0",
                "order_set-INITIAL_FORMS": "0",
                "order_set-MIN_NUM_FORMS": "0",
                "order_set-MAX_NUM_FORMS": "1000",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("name", response.context["adminform"].form.errors)
        self.assertUnchanged()

    # Code and the database

    def test_book_create_refuses_a_blank_title(self):
        for name in BLANK_TITLES:
            with self.subTest(name=name):
                self.assertIsNone(Book.create(name, "Description"))
        self.assertUnchanged()

    def test_the_database_refuses_a_blank_title(self):
        for name in BLANK_TITLES:
            with self.subTest(name=name):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Book.objects.create(name=name, count=1)
        self.assertUnchanged()

    def test_the_database_refuses_clearing_a_title(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.book.update(name="")
        self.assertUnchanged()


class BookTitleMigrationTests(TransactionTestCase):
    BEFORE = [("book", "0007_book_rating")]

    def test_books_already_without_a_title_get_one(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(self.BEFORE)
        try:
            old = executor.loader.project_state(self.BEFORE).apps
            OldBook = old.get_model("book", "Book")
            blank = OldBook.objects.create(name="", count=1)
            spaces = OldBook.objects.create(name="  ", count=1)
            titled = OldBook.objects.create(name="Kobzar", count=1)
            MigrationExecutor(connection).migrate(latest)
            names = dict(Book.objects.values_list("pk", "name"))
            self.assertEqual(names[blank.pk], f"Untitled book #{blank.pk}")
            self.assertEqual(names[spaces.pk], f"Untitled book #{spaces.pk}")
            self.assertEqual(names[titled.pk], "Kobzar")
        finally:
            MigrationExecutor(connection).migrate(latest)
