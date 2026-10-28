"""Each account list loads in a fixed number of queries (research R8, FR-047)."""

from itertools import count

from django.test import TestCase
from django.urls import reverse

from library.testing import assert_same_query_count

from .models import ROLE_LIBRARIAN, CustomUser


class AccountListQueryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.librarian = CustomUser.objects.create_user(
            email="queries-librarian@example.com",
            password="queries-password",
            first_name="Query",
            middle_name="",
            last_name="Librarian",
            role=ROLE_LIBRARIAN,
            is_active=True,
        )

    def setUp(self):
        self.client.force_login(self.librarian)
        self.numbers = count()

    def add_accounts(self, total):
        for _ in range(total):
            account = CustomUser(
                email=f"counted-{next(self.numbers)}@example.com",
                first_name="Counted",
                middle_name="",
                last_name="Reader",
            )
            account.set_unusable_password()  # hashing 50 passwords is slow
            account.save()

    def test_the_user_list(self):
        response = assert_same_query_count(
            self, self.client, reverse("user_list"), self.add_accounts
        )
        self.assertEqual(len(response.context["users"]), 51)  # the librarian too

    def test_the_api_user_list(self):
        response = assert_same_query_count(
            self, self.client, "/api/v1/user/", self.add_accounts
        )
        self.assertEqual(len(response.json()), 51)
