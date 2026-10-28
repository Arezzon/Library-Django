"""Authors through the web, the API and the admin site (research R9, FR-049)."""

from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse

from authentication.models import ROLE_LIBRARIAN, CustomUser
from book.models import Book
from book.testing import FakeEncoderMixin

from .models import Author

TOO_LONG = "x" * 21  # name, surname and patronymic each allow 20 characters
NAME_FIELDS = ("name", "surname", "patronymic")


def account(email, role=CustomUser.ROLE_VISITOR):
    return CustomUser.objects.create_user(
        email=email,
        password="authors-password",
        first_name="Author",
        middle_name="",
        last_name="Test",
        role=role,
        is_active=True,
    )


def messages_of(response):
    return [str(message) for message in get_messages(response.wsgi_request)]


class AuthorTestCase(FakeEncoderMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.librarian = account("authors-librarian@example.com", ROLE_LIBRARIAN)
        cls.reader = account("authors-reader@example.com")
        cls.kobzar = Book.objects.create(name="Kobzar", count=1)
        cls.haidamaky = Book.objects.create(name="Haidamaky", count=1)
        cls.author = Author.objects.create(
            name="Taras", surname="Shevchenko", patronymic="Hryhorovych"
        )
        cls.author.books.add(cls.kobzar)
        cls.unattached = Author.objects.create(
            name="Lesya", surname="Ukrainka", patronymic="Petrivna"
        )

    def signed_in(self, user):
        client = Client()
        client.force_login(user)
        return client

    def assertUnchanged(self, author):
        fresh = Author.objects.filter(pk=author.pk).first()
        self.assertIsNotNone(fresh, f"{author} was deleted")
        self.assertEqual(
            (fresh.name, fresh.surname, fresh.patronymic),
            (author.name, author.surname, author.patronymic),
        )
        self.assertEqual(set(fresh.books.all()), set(author.books.all()))


class AuthorWebTests(AuthorTestCase):
    def form(self, **changes):
        return {
            "name": "Ivan",
            "surname": "Franko",
            "patronymic": "Yakovych",
            "books": [self.haidamaky.pk],
            **changes,
        }

    def test_librarian_creates_an_author_with_books(self):
        response = self.signed_in(self.librarian).post(
            reverse("author_create"), self.form()
        )
        self.assertRedirects(response, reverse("author_list"))
        author = Author.objects.get(surname="Franko")
        self.assertEqual(list(author.books.all()), [self.haidamaky])

    def test_librarian_edits_an_author_and_their_books(self):
        url = reverse("author_update", args=[self.author.pk])
        form = self.form(name="Taras", surname="Shevchenko", patronymic="H")
        response = self.signed_in(self.librarian).post(url, form)
        self.assertRedirects(response, reverse("author_list"))
        self.author.refresh_from_db()
        self.assertEqual(self.author.patronymic, "H")
        self.assertEqual(list(self.author.books.all()), [self.haidamaky])

    def test_librarian_deletes_an_author_without_books(self):
        url = reverse("author_delete", args=[self.unattached.pk])
        response = self.signed_in(self.librarian).post(url)
        self.assertRedirects(response, reverse("author_list"))
        self.assertFalse(Author.objects.filter(pk=self.unattached.pk).exists())
        self.assertIn(
            'Author "Lesya Ukrainka" was successfully deleted.',
            messages_of(response),
        )

    def test_an_author_with_books_is_not_deleted_and_the_page_says_why(self):
        url = reverse("author_delete", args=[self.author.pk])
        response = self.signed_in(self.librarian).post(url)
        self.assertRedirects(response, reverse("author_list"))
        self.assertUnchanged(self.author)
        self.assertIn(
            'Cannot delete author "Taras Shevchenko" because they are attached to '
            "one or more books.",
            messages_of(response),
        )

    def test_names_longer_than_20_characters_are_refused(self):
        client = self.signed_in(self.librarian)
        for field in NAME_FIELDS:
            with self.subTest(field=field):
                response = client.post(
                    reverse("author_create"), self.form(**{field: TOO_LONG})
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
                self.assertFalse(Author.objects.filter(surname="Franko").exists())
        self.assertFalse(Author.objects.filter(**{"name": TOO_LONG}).exists())

    def test_a_reader_changes_no_author(self):
        client = self.signed_in(self.reader)
        attempts = [
            (reverse("author_create"), self.form()),
            (reverse("author_update", args=[self.author.pk]), self.form()),
            (reverse("author_delete", args=[self.unattached.pk]), {}),
        ]
        for url, data in attempts:
            with self.subTest(url=url):
                self.assertEqual(client.post(url, data).status_code, 403)
        self.assertFalse(Author.objects.filter(surname="Franko").exists())
        self.assertUnchanged(self.author)
        self.assertTrue(Author.objects.filter(pk=self.unattached.pk).exists())


class AuthorApiTests(AuthorTestCase):
    def body(self, **changes):
        return {
            "name": "Ivan",
            "surname": "Franko",
            "patronymic": "Yakovych",
            "books": [self.haidamaky.pk],
            **changes,
        }

    def test_librarian_creates_an_author_with_books(self):
        response = self.signed_in(self.librarian).post(
            "/api/v1/author/", self.body(), content_type="application/json"
        )
        self.assertEqual(response.status_code, 201)
        author = Author.objects.get(pk=response.json()["id"])
        self.assertEqual(list(author.books.all()), [self.haidamaky])

    def test_librarian_edits_an_author_and_their_books(self):
        response = self.signed_in(self.librarian).patch(
            f"/api/v1/author/{self.author.pk}/",
            {"patronymic": "H", "books": [self.kobzar.pk, self.haidamaky.pk]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            sorted(response.json()["books"]), [self.kobzar.pk, self.haidamaky.pk]
        )
        self.author.refresh_from_db()
        self.assertEqual(self.author.patronymic, "H")

    def test_librarian_deletes_an_author_without_books(self):
        response = self.signed_in(self.librarian).delete(
            f"/api/v1/author/{self.unattached.pk}/"
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Author.objects.filter(pk=self.unattached.pk).exists())

    def test_an_author_with_books_is_not_deleted(self):
        response = self.signed_in(self.librarian).delete(
            f"/api/v1/author/{self.author.pk}/"
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"],
            'Cannot delete author "Taras Shevchenko" because they are attached to '
            "one or more books.",
        )
        self.assertUnchanged(self.author)

    def test_the_schema_documents_the_refusal_to_delete(self):
        schema = self.client.get("/api/schema/?format=json").json()
        refusal = schema["paths"]["/api/v1/author/{id}/"]["delete"]["responses"]["409"]
        self.assertEqual(
            refusal["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/Refusal"},
        )

    def test_each_author_lists_the_books_they_are_linked_to(self):
        response = self.signed_in(self.reader).get(f"/api/v1/author/{self.author.pk}/")
        self.assertEqual(response.json()["books"], [self.kobzar.pk])

    def test_names_longer_than_20_characters_are_refused(self):
        client = self.signed_in(self.librarian)
        for field in NAME_FIELDS:
            with self.subTest(field=field):
                response = client.post(
                    "/api/v1/author/",
                    self.body(**{field: TOO_LONG}),
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json())
        self.assertFalse(Author.objects.filter(surname="Franko").exists())

    def test_a_reader_changes_no_author(self):
        client = self.signed_in(self.reader)
        url = f"/api/v1/author/{self.author.pk}/"
        attempts = [
            client.post(
                "/api/v1/author/", self.body(), content_type="application/json"
            ),
            client.put(url, self.body(), content_type="application/json"),
            client.patch(url, {"name": "Ivan"}, content_type="application/json"),
            client.delete(f"/api/v1/author/{self.unattached.pk}/"),
        ]
        self.assertEqual([response.status_code for response in attempts], [403] * 4)
        self.assertFalse(Author.objects.filter(surname="Franko").exists())
        self.assertUnchanged(self.author)
        self.assertTrue(Author.objects.filter(pk=self.unattached.pk).exists())


class AuthorAdminTests(AuthorTestCase):
    def form(self, **changes):
        return {
            "name": "Ivan",
            "surname": "Franko",
            "patronymic": "Yakovych",
            "books": [self.haidamaky.pk],
            "_save": "Save",
            **changes,
        }

    def test_librarian_creates_edits_and_deletes_an_author(self):
        client = self.signed_in(self.librarian)
        response = client.post("/admin/author/author/add/", self.form())
        self.assertEqual(response.status_code, 302)
        author = Author.objects.get(surname="Franko")
        self.assertEqual(list(author.books.all()), [self.haidamaky])
        response = client.post(
            f"/admin/author/author/{author.pk}/change/",
            self.form(patronymic="Ya", books=[self.kobzar.pk]),
        )
        self.assertEqual(response.status_code, 302)
        author.refresh_from_db()
        self.assertEqual(author.patronymic, "Ya")
        self.assertEqual(list(author.books.all()), [self.kobzar])
        author.books.clear()
        response = client.post(
            f"/admin/author/author/{author.pk}/delete/", {"post": "yes"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Author.objects.filter(pk=author.pk).exists())

    def test_an_author_with_books_is_not_deleted(self):
        response = self.signed_in(self.librarian).post(
            f"/admin/author/author/{self.author.pk}/delete/", {"post": "yes"}
        )
        self.assertContains(response, "Kobzar")
        self.assertUnchanged(self.author)

    def test_the_bulk_delete_action_keeps_an_author_with_books(self):
        response = self.signed_in(self.librarian).post(
            "/admin/author/author/",
            {
                "action": "delete_selected",
                "_selected_action": [self.author.pk, self.unattached.pk],
                "post": "yes",
            },
        )
        self.assertContains(response, "Kobzar")
        self.assertUnchanged(self.author)
        self.assertTrue(Author.objects.filter(pk=self.unattached.pk).exists())

    def test_names_longer_than_20_characters_are_refused(self):
        client = self.signed_in(self.librarian)
        for field in NAME_FIELDS:
            with self.subTest(field=field):
                response = client.post(
                    "/admin/author/author/add/", self.form(**{field: TOO_LONG})
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["adminform"].form.errors)
        self.assertFalse(Author.objects.filter(surname="Franko").exists())

    def test_a_reader_changes_no_author(self):
        client = self.signed_in(self.reader)
        attempts = [
            ("/admin/author/author/add/", self.form()),
            (f"/admin/author/author/{self.author.pk}/change/", self.form()),
            (f"/admin/author/author/{self.unattached.pk}/delete/", {"post": "yes"}),
        ]
        for url, data in attempts:
            with self.subTest(url=url):
                response = client.post(url, data)
                self.assertRedirects(
                    response, f"/admin/login/?next={url}", fetch_redirect_response=False
                )
        self.assertFalse(Author.objects.filter(surname="Franko").exists())
        self.assertUnchanged(self.author)
        self.assertTrue(Author.objects.filter(pk=self.unattached.pk).exists())
