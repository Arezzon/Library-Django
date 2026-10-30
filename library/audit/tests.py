"""The audit trail: one entry per critical change, written with it (FR-037 to FR-040).

Each change runs in a savepoint that is rolled back after its entry is checked, so the
cases stay independent. The channels and the entries' contents follow
contracts/logs-and-audit.md and data-model.md §5.
"""

from datetime import timedelta
from unittest.mock import patch

from django.db import transaction
from django.test import Client, TestCase
from django.urls import get_resolver
from django.utils import timezone

from authentication.models import ROLE_LIBRARIAN, ROLE_VISITOR, CustomUser
from book.models import Book
from book.testing import FakeEncoderMixin
from order.models import Order

from .models import AuditEntry

REQUEST_IDS = {
    "web": "audit-web-00001",
    "api": "audit-api-00001",
    "admin": "audit-adm-00001",
}
CHANNELS = ("web", "api", "admin", "command")


def account(email, role=ROLE_VISITOR, is_active=True):
    return CustomUser.objects.create_user(
        email=email,
        password="audit-password-1",
        first_name="Audit",
        middle_name="M",
        last_name=email.split("@")[0].title(),
        role=role,
        is_active=is_active,
    )


def label(user):
    return f"{user.first_name} {user.last_name} (#{user.pk})"


class AuditTestCase(FakeEncoderMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.librarian = account("librarian@audit.test", ROLE_LIBRARIAN)
        cls.reader = account("reader@audit.test")
        cls.other_reader = account("other@audit.test")
        cls.colleague = account("colleague@audit.test", ROLE_LIBRARIAN)
        cls.inactive = account("inactive@audit.test", is_active=False)
        cls.leaving = account("leaving@audit.test")
        cls.book = Book.objects.create(name="Kobzar", description="Poems", count=5)
        cls.other_book = Book.objects.create(name="Haidamaky", count=5)
        cls.free_book = Book.objects.create(name="Never borrowed", count=1)
        due = timezone.now() + timedelta(days=14)
        cls.loan = Order.objects.create(
            user=cls.reader, book=cls.book, plated_end_at=due
        )
        cls.returned = Order.objects.create(
            user=cls.reader, book=cls.book, plated_end_at=due, end_at=timezone.now()
        )

    def send(self, channel, method, url, data=None, user=None):
        client = Client()
        client.force_login(user or self.librarian)
        headers = {"X-Request-ID": REQUEST_IDS[channel]}
        if channel == "api":
            return getattr(client, method)(
                url, data, content_type="application/json", headers=headers
            )
        return getattr(client, method)(url, data or {}, headers=headers)

    def check(self, action, channel, change, expected, target_id, actor=None):
        """Make the change in a rolled-back savepoint; check its single entry.

        ``expected`` returns ``(before, after)`` once the change is made;
        ``target_id`` may also be a function, for a record the change creates.
        """
        if actor is None and channel != "command":
            actor = self.librarian
        with self.subTest(action=action, channel=channel), transaction.atomic():
            seen = set(AuditEntry.objects.values_list("pk", flat=True))
            response = change()
            entries = [
                entry
                for entry in AuditEntry.objects.filter(action=action)
                if entry.pk not in seen
            ]
            status = getattr(response, "status_code", None)
            self.assertEqual(len(entries), 1, f"entries: {entries}; response: {status}")
            entry = entries[0]
            before, after = expected()
            target = target_id() if callable(target_id) else target_id
            self.assertEqual(
                (entry.channel, entry.target_id, entry.before, entry.after),
                (channel, target, before, after),
            )
            self.assertEqual(entry.actor_id, actor.pk if actor else None)
            self.assertEqual(entry.actor_label, label(actor) if actor else "system")
            self.assertEqual(entry.request_id, REQUEST_IDS.get(channel, ""))
            transaction.set_rollback(True)

    def admin_loan_form(self, loan, **changes):
        return {
            "user": loan.user_id,
            "book": loan.book_id,
            "plated_end_at_0": "2030-01-15",
            "plated_end_at_1": "12:00:00",
            "end_at_0": loan.end_at.strftime("%Y-%m-%d") if loan.end_at else "",
            "end_at_1": loan.end_at.strftime("%H:%M:%S") if loan.end_at else "",
            "_save": "Save",
            **changes,
        }

    def admin_book_form(self, book, **changes):
        return {
            "name": book.name,
            "description": book.description,
            "count": book.count,
            "order_set-TOTAL_FORMS": "0",
            "order_set-INITIAL_FORMS": "0",
            "order_set-MIN_NUM_FORMS": "0",
            "order_set-MAX_NUM_FORMS": "1000",
            "_save": "Save",
            **changes,
        }


class AccountEntryTests(AuditTestCase):
    def changes(self, user, field, value):
        """The same account change through each channel."""
        update_url = f"/authentication/users/{user.pk}/update/"
        admin_url = f"/admin/authentication/customuser/{user.pk}/change/"
        # An unchecked "active" box is absent from the form data.
        form = {
            "first_name": user.first_name,
            "middle_name": user.middle_name,
            "last_name": user.last_name,
            "role": user.role,
            **({"is_active": "on"} if user.is_active else {}),
        }
        if field == "is_active":
            form.pop("is_active", None)
            form.update({"is_active": "on"} if value else {})
        else:
            form[field] = value
        admin_form = {
            **form,
            "email": user.email,
            "password": user.password,
            "_save": "Save",
        }

        def command():
            setattr(user, field, value)
            user.save()

        return {
            "web": lambda: self.send("web", "post", update_url, form),
            "api": lambda: self.send(
                "api", "patch", f"/api/v1/user/{user.pk}/", {field: value}
            ),
            "admin": lambda: self.send("admin", "post", admin_url, admin_form),
            "command": command,
        }

    def test_granting_the_librarian_role(self):
        for channel, change in self.changes(
            self.reader, "role", ROLE_LIBRARIAN
        ).items():
            self.check(
                "role_granted",
                channel,
                change,
                lambda: ({"role": "visitor"}, {"role": "librarian"}),
                self.reader.pk,
            )

    def test_creating_a_librarian_account_grants_the_role(self):
        body = {
            "first_name": "New",
            "middle_name": "M",
            "last_name": "Librarian",
            "email": "new-librarian@audit.test",
            "password": "new-password-1",
            "role": ROLE_LIBRARIAN,
            "is_active": True,
        }
        self.check(
            "role_granted",
            "api",
            lambda: self.send("api", "post", "/api/v1/user/", body),
            lambda: ({}, {"role": "librarian"}),
            lambda: CustomUser.objects.get(email=body["email"]).pk,
        )

    def test_removing_the_librarian_role(self):
        changes = self.changes(self.colleague, "role", ROLE_VISITOR)
        for channel, change in changes.items():
            self.check(
                "role_removed",
                channel,
                change,
                lambda: ({"role": "librarian"}, {"role": "visitor"}),
                self.colleague.pk,
            )

    def test_deactivating_an_account(self):
        for channel, change in self.changes(self.reader, "is_active", False).items():
            self.check(
                "account_deactivated",
                channel,
                change,
                lambda: ({"is_active": True}, {"is_active": False}),
                self.reader.pk,
            )

    def test_activating_an_account(self):
        for channel, change in self.changes(self.inactive, "is_active", True).items():
            self.check(
                "account_activated",
                channel,
                change,
                lambda: ({"is_active": False}, {"is_active": True}),
                self.inactive.pk,
            )

    def test_deleting_an_account(self):
        user = self.leaving
        changes = {
            "api": lambda: self.send("api", "delete", f"/api/v1/user/{user.pk}/"),
            "admin": lambda: self.send(
                "admin",
                "post",
                f"/admin/authentication/customuser/{user.pk}/delete/",
                {"post": "yes"},
            ),
            "command": user.delete,
        }
        for channel, change in changes.items():
            self.check(
                "account_deleted",
                channel,
                change,
                lambda: ({"role": "visitor", "is_active": True}, {}),
                user.pk,
            )


class LoanEntryTests(AuditTestCase):
    def test_starting_a_loan(self):
        due = (timezone.now() + timedelta(days=7)).isoformat()
        book = self.free_book

        def command():
            Order.objects.create(user=self.reader, book=book, plated_end_at=due)

        changes = {
            "web": lambda: self.send(
                "web",
                "post",
                "/order/lend/",
                {"reader": self.reader.pk, "book": book.pk, "days": 14},
            ),
            "api": lambda: self.send(
                "api",
                "post",
                "/api/v1/order/",
                {"user": self.reader.pk, "book": book.pk, "plated_end_at": due},
            ),
            "admin": lambda: self.send(
                "admin",
                "post",
                "/admin/order/order/add/",
                {**self.admin_loan_form(self.loan), "book": book.pk},
            ),
            "command": command,
        }

        def expected():
            loan = Order.objects.get(book=book)
            after = {
                "book": book.pk,
                "user": self.reader.pk,
                "due": loan.plated_end_at.isoformat(),
            }
            return {}, after

        for channel, change in changes.items():
            self.check(
                "loan_started",
                channel,
                change,
                expected,
                lambda: Order.objects.get(book=book).pk,
            )

    def test_returning_a_loan(self):
        loan = self.loan

        def command():
            loan.end_at = timezone.now()
            loan.save()

        changes = {
            "web": lambda: self.send("web", "post", f"/order/close/{loan.pk}/"),
            "api": lambda: self.send(
                "api",
                "patch",
                f"/api/v1/order/{loan.pk}/",
                {"end_at": timezone.now().isoformat()},
            ),
            "admin": lambda: self.send(
                "admin",
                "post",
                f"/admin/order/order/{loan.pk}/change/",
                self.admin_loan_form(loan, end_at_0="2030-01-10", end_at_1="10:00:00"),
            ),
            "command": command,
        }

        def expected():
            end_at = Order.objects.get(pk=loan.pk).end_at
            return {"end_at": None}, {"end_at": end_at.isoformat()}

        for channel, change in changes.items():
            self.check("loan_returned", channel, change, expected, loan.pk)

    def test_reopening_a_loan(self):
        loan = self.returned
        returned_at = loan.end_at.isoformat()

        def command():
            loan.end_at = None
            loan.save()

        changes = {
            "web": lambda: self.send(
                "web",
                "post",
                f"/order/update/{loan.pk}/",
                {"plated_end_at": "2030-01-15T12:00", "end_at": ""},
            ),
            "api": lambda: self.send(
                "api", "patch", f"/api/v1/order/{loan.pk}/", {"end_at": None}
            ),
            "admin": lambda: self.send(
                "admin",
                "post",
                f"/admin/order/order/{loan.pk}/change/",
                self.admin_loan_form(loan, end_at_0="", end_at_1=""),
            ),
            "command": command,
        }
        for channel, change in changes.items():
            self.check(
                "loan_reopened",
                channel,
                change,
                lambda: ({"end_at": returned_at}, {"end_at": None}),
                loan.pk,
            )

    def test_reassigning_a_loan(self):
        loan = self.loan
        new_book = self.other_book

        def command():
            loan.book = new_book
            loan.save()

        changes = {
            "api": lambda: self.send(
                "api", "patch", f"/api/v1/order/{loan.pk}/", {"book": new_book.pk}
            ),
            "admin": lambda: self.send(
                "admin",
                "post",
                f"/admin/order/order/{loan.pk}/change/",
                self.admin_loan_form(loan, book=new_book.pk),
            ),
            "command": command,
        }
        for channel, change in changes.items():
            self.check(
                "loan_reassigned",
                channel,
                change,
                lambda: ({"book": self.book.pk}, {"book": new_book.pk}),
                loan.pk,
            )
        self.check(
            "loan_reassigned",
            "api",
            lambda: self.send(
                "api",
                "patch",
                f"/api/v1/order/{loan.pk}/",
                {"user": self.other_reader.pk},
            ),
            lambda: ({"user": self.reader.pk}, {"user": self.other_reader.pk}),
            loan.pk,
        )

    def test_deleting_a_loan(self):
        loan = self.loan
        changes = {
            "api": lambda: self.send("api", "delete", f"/api/v1/order/{loan.pk}/"),
            "admin": lambda: self.send(
                "admin",
                "post",
                f"/admin/order/order/{loan.pk}/delete/",
                {"post": "yes"},
            ),
            "command": loan.delete,
        }
        before = {"book": self.book.pk, "user": self.reader.pk, "end_at": None}
        for channel, change in changes.items():
            self.check("loan_deleted", channel, change, lambda: (before, {}), loan.pk)

    def test_deleting_an_account_records_its_loans_too(self):
        account_id = self.reader.pk
        loans = set(Order.objects.filter(user=self.reader).values_list("pk", flat=True))
        self.reader.delete()
        deleted = AuditEntry.objects.filter(action="loan_deleted")
        self.assertEqual(set(deleted.values_list("target_id", flat=True)), loans)
        self.assertEqual(
            AuditEntry.objects.filter(
                action="account_deleted", target_id=account_id
            ).count(),
            1,
        )


class BookEntryTests(AuditTestCase):
    def test_changing_the_number_of_copies(self):
        book = self.other_book

        def command():
            book.count = 7
            book.save()

        changes = {
            "web": lambda: self.send(
                "web",
                "post",
                f"/book/update/{book.pk}/",
                {"name": book.name, "description": book.description, "count": 7},
            ),
            "api": lambda: self.send(
                "api", "patch", f"/api/v1/book/{book.pk}/", {"count": 7}
            ),
            "admin": lambda: self.send(
                "admin",
                "post",
                f"/admin/book/book/{book.pk}/change/",
                self.admin_book_form(book, count=7),
            ),
            "command": command,
        }
        for channel, change in changes.items():
            self.check(
                "book_copies_changed",
                channel,
                change,
                lambda: ({"count": 5}, {"count": 7}),
                book.pk,
            )

    def test_deleting_a_book(self):
        book = self.free_book
        changes = {
            "web": lambda: self.send("web", "post", f"/book/delete/{book.pk}/"),
            "api": lambda: self.send("api", "delete", f"/api/v1/book/{book.pk}/"),
            "admin": lambda: self.send(
                "admin", "post", f"/admin/book/book/{book.pk}/delete/", {"post": "yes"}
            ),
            "command": book.delete,
        }
        for channel, change in changes.items():
            self.check(
                "book_deleted",
                channel,
                change,
                lambda: ({"name": "Never borrowed", "count": 1}, {}),
                book.pk,
            )


class AuditGuaranteeTests(AuditTestCase):
    def test_a_change_rolled_back_by_its_caller_leaves_no_entry(self):
        with self.assertRaises(RuntimeError), transaction.atomic():
            self.reader.role = ROLE_LIBRARIAN
            self.reader.save()
            raise RuntimeError("caller rolls back")
        entries = AuditEntry.objects.filter(
            action="role_granted", target_id=self.reader.pk
        )
        self.assertFalse(entries.exists())

    def test_a_change_whose_entry_cannot_be_written_rolls_back(self):
        def grant():
            self.reader.role = ROLE_LIBRARIAN
            self.reader.save()

        def return_loan():
            self.loan.end_at = timezone.now()
            self.loan.save()

        def restock():
            self.book.count = 9
            self.book.save()

        failure = patch.object(
            AuditEntry.objects, "create", side_effect=RuntimeError("audit store down")
        )
        for change in (grant, return_loan, restock):
            with self.subTest(change=change.__name__), failure:
                with self.assertRaises(RuntimeError):
                    change()
        self.assertEqual(CustomUser.objects.get(pk=self.reader.pk).role, ROLE_VISITOR)
        self.assertIsNone(Order.objects.get(pk=self.loan.pk).end_at)
        self.assertEqual(Book.objects.get(pk=self.book.pk).count, 5)

    def test_entries_cannot_be_changed_or_deleted(self):
        self.book.count = 6
        self.book.save()
        entry = AuditEntry.objects.get(action="book_copies_changed")
        attempts = {
            "save": lambda: entry.save(),
            "delete": lambda: entry.delete(),
            "update": lambda: AuditEntry.objects.filter(pk=entry.pk).update(reason="x"),
            "queryset delete": lambda: AuditEntry.objects.filter(pk=entry.pk).delete(),
            "bulk_update": lambda: AuditEntry.objects.bulk_update([entry], ["reason"]),
        }
        for name, attempt in attempts.items():
            with self.subTest(attempt=name), self.assertRaises(ValueError):
                attempt()
        self.assertEqual(AuditEntry.objects.get(pk=entry.pk).after, {"count": 6})

    def test_the_admin_site_shows_entries_but_never_adds_changes_or_deletes(self):
        self.book.count = 6
        self.book.save()
        entry = AuditEntry.objects.get(action="book_copies_changed")
        client = Client()
        client.force_login(self.librarian)
        listing = client.get("/admin/audit/auditentry/")
        self.assertContains(listing, "Kobzar")
        self.assertEqual(client.get("/admin/audit/auditentry/add/").status_code, 403)
        change_url = f"/admin/audit/auditentry/{entry.pk}/change/"
        self.assertEqual(client.post(change_url, {"reason": "x"}).status_code, 403)
        delete_url = f"/admin/audit/auditentry/{entry.pk}/delete/"
        self.assertEqual(client.post(delete_url, {"post": "yes"}).status_code, 403)
        self.assertEqual(AuditEntry.objects.get(pk=entry.pk).reason, "")

    def test_a_reader_cannot_read_the_trail(self):
        client = Client()
        client.force_login(self.reader)
        response = client.get("/admin/audit/auditentry/")
        self.assertRedirects(
            response,
            "/admin/login/?next=/admin/audit/auditentry/",
            fetch_redirect_response=False,
        )

    def test_no_api_route_exposes_entries(self):
        routes = []

        def walk(patterns, prefix):
            for pattern in patterns:
                route = prefix + str(pattern.pattern)
                if hasattr(pattern, "url_patterns"):
                    walk(pattern.url_patterns, route)
                elif route.startswith("api/"):
                    routes.append((route, pattern.callback))

        walk(get_resolver().url_patterns, "")
        self.assertTrue(routes)
        for route, callback in routes:
            view = getattr(callback, "cls", None)
            queryset = getattr(view, "queryset", None)
            with self.subTest(route=route):
                self.assertNotIn("audit", route)
                self.assertIsNot(getattr(queryset, "model", None), AuditEntry)

    def test_entries_outlive_the_account_and_the_book_they_describe(self):
        self.leaving.role = ROLE_LIBRARIAN
        self.leaving.save()
        self.free_book.count = 2
        self.free_book.save()
        target_ids = (self.leaving.pk, self.free_book.pk)
        self.leaving.delete()
        self.free_book.delete()
        granted = AuditEntry.objects.get(action="role_granted", target_id=target_ids[0])
        changed = AuditEntry.objects.get(
            action="book_copies_changed", target_id=target_ids[1]
        )
        self.assertIn(f"(#{target_ids[0]})", granted.target_label)
        self.assertEqual(changed.target_label, "Never borrowed")

    def test_no_entry_holds_a_password_or_a_hash(self):
        client = Client()
        client.force_login(self.librarian)
        client.patch(
            f"/api/v1/user/{self.reader.pk}/",
            {"password": "brand-new-password-7", "role": ROLE_LIBRARIAN},
            content_type="application/json",
        )
        self.colleague.is_active = False
        self.colleague.save()
        self.leaving.delete()
        hashes = CustomUser.objects.values_list("password", flat=True)
        for entry in AuditEntry.objects.all():
            text = f"{entry.before} {entry.after} {entry.target_label}"
            with self.subTest(action=entry.action):
                self.assertNotIn("password", text)
                self.assertNotIn("brand-new-password-7", text)
                self.assertNotIn("pbkdf2", text)
                for value in hashes:
                    self.assertNotIn(value, text)

    def test_bulk_role_and_status_updates_are_refused(self):
        entries = AuditEntry.objects.count()
        accounts = CustomUser.objects.filter(pk=self.reader.pk)
        for change in ({"role": ROLE_LIBRARIAN}, {"is_active": False}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                accounts.update(**change)
        for fields in (["role"], ["is_active"]):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                CustomUser.objects.bulk_update([self.reader], fields)
        self.assertEqual(accounts.update(first_name="Renamed"), 1)
        reader = CustomUser.objects.get(pk=self.reader.pk)
        reader.middle_name = "Bulk"
        self.assertEqual(CustomUser.objects.bulk_update([reader], ["middle_name"]), 1)
        reader = CustomUser.objects.get(pk=self.reader.pk)
        self.assertEqual((reader.role, reader.is_active), (ROLE_VISITOR, True))
        self.assertEqual(AuditEntry.objects.count(), entries)
