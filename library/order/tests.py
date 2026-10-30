from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from queue import Queue
from threading import Barrier
from time import monotonic, sleep

from django.contrib.messages import get_messages
from django.db import close_old_connections, connection, connections, transaction
from django.test import Client, TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import ROLE_LIBRARIAN, CustomUser
from book.models import Book
from book.testing import FakeEncoderMixin

from .models import BookUnavailableError, Order


def reader(email, role=0):
    return CustomUser.objects.create_user(
        email=email,
        password="test-password",
        first_name="Test",
        middle_name="",
        last_name="Reader",
        is_active=True,
        role=role,
    )


class AtomicIssuanceTests(FakeEncoderMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = reader("reader@example.com")
        cls.book = Book.objects.create(name="Single copy", count=1)

    def issue(self, **kwargs):
        return Order.objects.create(
            user=self.user,
            book=kwargs.pop("book", self.book),
            plated_end_at=timezone.now() + timedelta(days=14),
            **kwargs,
        )

    def test_bulk_writes_that_skip_the_copy_check_and_the_audit_are_refused(self):
        loan = self.issue()
        other = reader("guard-other@example.com")
        other_book = Book.objects.create(name="Other copy", count=1)
        loans = Order.objects.filter(pk=loan.pk)
        changes = (
            {"end_at": timezone.now()},
            {"book": other_book},
            {"book_id": other_book.pk},
            {"user": other},
            {"user_id": other.pk},
        )
        for change in changes:
            with self.subTest(change=list(change)), self.assertRaises(ValueError):
                loans.update(**change)
        with self.assertRaises(ValueError):
            Order.objects.bulk_create(
                [Order(user=other, book=other_book, plated_end_at=timezone.now())]
            )
        for fields in (["end_at"], ["book"], ["user"]):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                Order.objects.bulk_update([loan], fields)
        self.assertEqual(loans.update(plated_end_at=timezone.now()), 1)
        loan.plated_end_at = timezone.now() + timedelta(days=3)
        self.assertEqual(Order.objects.bulk_update([loan], ["plated_end_at"]), 1)
        loan.refresh_from_db()
        self.assertEqual(
            (loan.book, loan.user, loan.end_at), (self.book, self.user, None)
        )
        self.assertEqual(Order.objects.count(), 1)

    def test_issue_consumes_derived_availability_without_changing_total(self):
        self.issue()
        self.book.refresh_from_db()
        self.assertEqual(self.book.count, 1)
        self.assertEqual(self.book.available_count, 0)

    def test_stale_book_is_rechecked_under_lock(self):
        stale = Book.objects.get(pk=self.book.pk)
        self.assertEqual(stale.available_count, 1)
        self.issue()
        self.assertIsNone(Order.create(self.user, stale, timezone.now()))
        self.assertEqual(Order.objects.count(), 1)

    def test_zero_stock_and_exhausted_multi_copy_books_are_rejected(self):
        for count in (0, 2):
            with self.subTest(count=count):
                book = Book.objects.create(name="Limited", count=count)
                for _ in range(count):
                    self.issue(book=book)
                with self.assertRaises(BookUnavailableError):
                    self.issue(book=book)
                self.assertEqual(book.order_set.count(), count)

    def test_return_releases_a_copy_and_closed_history_does_not_consume_stock(self):
        order = self.issue()
        order.end_at = timezone.now()
        order.save(update_fields=["end_at"])
        self.issue(end_at=timezone.now())
        self.assertEqual(self.book.available_count, 1)
        self.issue()
        self.assertEqual(self.book.available_count, 0)

    def test_outer_transaction_rolls_back_issue(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.issue()
                raise RuntimeError("Cancel issuance")
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.book.available_count, 1)

    def test_existing_active_order_can_be_edited_without_consuming_another_copy(self):
        order = self.issue()
        order.plated_end_at += timedelta(days=1)
        order.save(update_fields=["plated_end_at"])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(self.book.available_count, 0)

    def test_reopening_and_reassignment_cannot_bypass_stock_check(self):
        closed = self.issue(end_at=timezone.now())
        self.issue()
        closed.end_at = None
        with self.assertRaises(BookUnavailableError):
            closed.save(update_fields=["end_at"])
        closed.refresh_from_db()
        self.assertIsNotNone(closed.end_at)
        other_book = Book.objects.create(name="Other", count=1)
        other_order = self.issue(book=other_book)
        other_order.book = self.book
        with self.assertRaises(BookUnavailableError):
            other_order.save(update_fields=["book"])
        other_order.refresh_from_db()
        self.assertEqual(other_order.book_id, other_book.pk)

    def test_partial_update_uses_persisted_occupancy_fields(self):
        closed = self.issue(end_at=timezone.now())
        self.issue()
        closed.end_at = None  # Not part of this partial update.
        closed.plated_end_at += timedelta(days=1)
        closed.save(update_fields=["plated_end_at"])
        closed.refresh_from_db()
        self.assertIsNotNone(closed.end_at)

    def test_both_api_create_routes_reject_exhausted_stock(self):
        client = APIClient()
        client.force_login(reader("api-lender@example.com", ROLE_LIBRARIAN))
        second = reader("api-second@example.com")
        payload = {
            "user": self.user.pk,
            "book": self.book.pk,
            "plated_end_at": (timezone.now() + timedelta(days=14)).isoformat(),
        }
        response = client.post("/api/v1/order/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        for url in ("/api/v1/order/", f"/api/v1/user/{second.pk}/order/"):
            with self.subTest(url=url):
                response = client.post(
                    url, {**payload, "user": second.pk}, format="json"
                )
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["code"], "no_copy_available")
        self.assertEqual(Order.objects.count(), 1)

    def test_api_reopening_is_rejected_without_changing_history(self):
        closed = self.issue(end_at=timezone.now())
        self.issue()
        client = APIClient()
        client.force_login(reader("api-librarian@example.com", ROLE_LIBRARIAN))
        response = client.patch(
            f"/api/v1/order/{closed.pk}/", {"end_at": None}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        closed.refresh_from_db()
        self.assertIsNotNone(closed.end_at)

    def test_web_form_issues_one_copy(self):
        self.client.force_login(reader("web-lender@example.com", ROLE_LIBRARIAN))
        form = {"reader": self.user.pk, "book": self.book.pk, "days": 14}
        self.assertRedirects(self.client.post("/order/lend/", form), "/order/all/")
        second = reader("web-second@example.com")
        response = self.client.post("/order/lend/", {**form, "reader": second.pk})
        self.assertContains(response, "No copy of “Single copy” is available.")
        self.assertEqual(Order.objects.count(), 1)

    def test_admin_rejects_unavailable_book_with_message(self):
        self.issue()
        librarian = reader("librarian@example.com", ROLE_LIBRARIAN)
        self.client.force_login(librarian)
        response = self.client.post(
            "/admin/order/order/add/",
            {
                "user": reader("admin-second@example.com").pk,
                "book": self.book.pk,
                "plated_end_at_0": "2026-10-20",
                "plated_end_at_1": "12:00:00",
                "end_at_0": "",
                "end_at_1": "",
                "_save": "Save",
            },
        )
        self.assertRedirects(
            response, "/admin/order/order/add/", fetch_redirect_response=False
        )
        # The desk's rules and message, as on the lend page (FR-012).
        self.assertIn(
            "No copy of “Single copy” is available. A reservation may be holding the "
            "last one.",
            [str(message) for message in get_messages(response.wsgi_request)],
        )
        self.assertEqual(Order.objects.count(), 1)


@skipUnlessDBFeature("has_select_for_update")
class ConcurrentIssuanceTests(FakeEncoderMixin, TransactionTestCase):
    def setUp(self):
        self.book = Book.objects.create(name="Last copy", count=1)
        self.users = [reader(f"reader{i}@example.com") for i in range(2)]
        self.librarian = reader("lender@example.com", ROLE_LIBRARIAN)

    def worker(self, user_id, barrier=None, backend_queue=None, api=False):
        close_old_connections()
        try:
            book = Book.objects.get(pk=self.book.pk)
            client = None
            if api:
                # Each request signs in before the barrier, so both requests race;
                # only librarians start loans (FR-015).
                client = APIClient()
                client.force_login(self.librarian)
            if backend_queue is not None:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    backend_queue.put(cursor.fetchone()[0])
            if barrier is not None:
                barrier.wait(timeout=10)
            if client is not None:
                return client.post(
                    "/api/v1/order/",
                    {
                        "user": user_id,
                        "book": book.pk,
                        "plated_end_at": timezone.now().isoformat(),
                    },
                    format="json",
                ).status_code
            order = Order.create(
                CustomUser.objects.get(pk=user_id), book, timezone.now()
            )
            return order is not None
        finally:
            connections.close_all()

    def test_parallel_issuance_creates_only_one_active_order(self):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self.worker, user.pk, barrier) for user in self.users
            ]
            results = [future.result(timeout=15) for future in futures]
        self.assertCountEqual(results, [True, False])
        self.assertEqual(
            Order.objects.filter(book=self.book, end_at__isnull=True).count(), 1
        )
        self.assertEqual(self.book.available_count, 0)

    def test_parallel_api_requests_return_created_and_conflict(self):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self.worker, user.pk, barrier, api=True)
                for user in self.users
            ]
            self.assertCountEqual(
                [future.result(timeout=15) for future in futures], [201, 409]
            )
        self.assertEqual(Order.objects.count(), 1)

    def test_second_borrower_waits_for_book_lock_and_rechecks_stock(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL lock observation is required")
        backend_queue = Queue()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Book.objects.select_for_update().get(pk=self.book.pk)
                future = pool.submit(
                    self.worker, self.users[1].pk, backend_queue=backend_queue
                )
                worker_pid = backend_queue.get(timeout=10)
                deadline = monotonic() + 5
                blocked = False
                while monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_blocking_pids(%s)", [worker_pid])
                        blocked = bool(cursor.fetchone()[0])
                    if blocked:
                        break
                    sleep(0.02)
                self.assertTrue(
                    blocked, "Second borrower did not wait for the Book row lock"
                )
                self.assertIsNotNone(
                    Order.create(self.users[0], self.book, timezone.now())
                )
            self.assertFalse(future.result(timeout=10))
        self.assertEqual(Order.objects.count(), 1)


class LoanChangeTests(FakeEncoderMixin, TestCase):
    """Every change of a loan in each channel that offers it, with a permitted and a
    refused caller (research R9). The web edit form changes the dates only, so
    reassigning happens through the API and the admin site."""

    @classmethod
    def setUpTestData(cls):
        cls.borrower = reader("loans-reader@example.com")
        cls.other = reader("loans-other@example.com")
        cls.librarian = reader("loans-librarian@example.com", ROLE_LIBRARIAN)
        cls.book = Book.objects.create(name="Kobzar", count=5)
        cls.other_book = Book.objects.create(name="Haidamaky", count=5)
        due = timezone.now() + timedelta(days=14)
        cls.loan = Order.objects.create(
            user=cls.borrower, book=cls.book, plated_end_at=due
        )
        cls.returned = Order.objects.create(
            user=cls.borrower, book=cls.book, plated_end_at=due, end_at=timezone.now()
        )

    def signed_in(self, user=None):
        client = Client()
        if user is not None:
            client.force_login(user)
        return client

    def api(self, user, method, path, body=None):
        return getattr(self.signed_in(user), method)(
            path, body, content_type="application/json"
        )

    def admin_form(self, **changes):
        return {
            "user": self.borrower.pk,
            "book": self.book.pk,
            "plated_end_at_0": "2030-01-15",
            "plated_end_at_1": "12:00:00",
            "end_at_0": "",
            "end_at_1": "",
            "_save": "Save",
            **changes,
        }

    def assertAdminSignIn(self, response, url):
        self.assertRedirects(
            response, f"/admin/login/?next={url}", fetch_redirect_response=False
        )

    def fresh(self, loan):
        return Order.objects.filter(pk=loan.pk).first()

    # Start

    def test_start_on_the_web(self):
        url = reverse("order_lend")
        form = {"reader": self.borrower.pk, "book": self.other_book.pk, "days": 14}
        refused = self.signed_in().post(url, form)
        self.assertRedirects(
            refused,
            f"/authentication/login/?next={url}",
            fetch_redirect_response=False,
        )
        self.assertEqual(self.signed_in(self.borrower).post(url, form).status_code, 403)
        self.assertFalse(Order.objects.filter(book=self.other_book).exists())
        response = self.signed_in(self.librarian).post(url, form)
        self.assertRedirects(response, reverse("order_all"))
        loan = Order.objects.get(book=self.other_book)
        self.assertEqual((loan.user, loan.end_at), (self.borrower, None))

    def test_start_through_the_api(self):
        due = (timezone.now() + timedelta(days=7)).isoformat()
        body = {"book": self.other_book.pk, "plated_end_at": due}
        own_route = f"/api/v1/user/{self.borrower.pk}/order/"
        other_route = f"/api/v1/user/{self.other.pk}/order/"
        refused = [
            self.api(
                self.borrower,
                "post",
                "/api/v1/order/",
                {**body, "user": self.borrower.pk},
            ),
            self.api(
                self.borrower, "post", "/api/v1/order/", {**body, "user": self.other.pk}
            ),
            self.api(self.borrower, "post", own_route, body),
            self.api(self.borrower, "post", other_route, body),
        ]
        self.assertEqual(
            [response.status_code for response in refused], [403, 403, 403, 404]
        )
        self.assertFalse(Order.objects.filter(book=self.other_book).exists())
        started = [
            self.api(
                self.librarian,
                "post",
                "/api/v1/order/",
                {**body, "user": self.borrower.pk},
            ),
            self.api(self.librarian, "post", other_route, body),
        ]
        self.assertEqual([response.status_code for response in started], [201, 201])
        loans = Order.objects.filter(book=self.other_book)
        self.assertCountEqual(
            [loan.user for loan in loans], [self.borrower, self.other]
        )

    def test_start_in_the_admin_site(self):
        url = "/admin/order/order/add/"
        form = self.admin_form(book=self.other_book.pk)
        self.assertAdminSignIn(self.signed_in(self.borrower).post(url, form), url)
        self.assertFalse(Order.objects.filter(book=self.other_book).exists())
        response = self.signed_in(self.librarian).post(url, form)
        self.assertEqual(response.status_code, 302)
        loan = Order.objects.get(book=self.other_book)
        self.assertEqual((loan.user, loan.end_at), (self.borrower, None))

    def test_a_new_loan_through_the_api_needs_its_due_date(self):
        body = {"user": self.borrower.pk, "book": self.other_book.pk}
        for path in ("/api/v1/order/", f"/api/v1/user/{self.borrower.pk}/order/"):
            with self.subTest(path=path):
                response = self.api(self.librarian, "post", path, body)
                self.assertEqual(response.status_code, 400)
                self.assertIn("plated_end_at", response.json())
        self.assertFalse(Order.objects.filter(book=self.other_book).exists())

    def test_a_loan_recorded_as_returned_is_saved_as_given(self):
        # A record of a loan that already ended takes no copy, so no rule applies.
        ended = timezone.now() - timedelta(days=1)
        response = self.api(
            self.librarian,
            "post",
            "/api/v1/order/",
            {
                "user": self.borrower.pk,
                "book": self.other_book.pk,
                "plated_end_at": (ended - timedelta(days=13)).isoformat(),
                "end_at": ended.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            self.fresh(Order.objects.get(pk=response.json()["id"])).end_at, ended
        )
        url = "/admin/order/order/add/"
        form = self.admin_form(
            book=self.other_book.pk, end_at_0="2030-01-20", end_at_1="12:00:00"
        )
        self.assertEqual(
            self.signed_in(self.librarian).post(url, form).status_code, 302
        )
        self.assertEqual(
            Order.objects.filter(book=self.other_book, end_at__isnull=False).count(), 2
        )

    # Return

    def test_return_on_the_web(self):
        url = reverse("order_close", args=[self.loan.pk])
        self.assertEqual(self.signed_in(self.borrower).post(url).status_code, 403)
        self.assertIsNone(self.fresh(self.loan).end_at)
        response = self.signed_in(self.librarian).post(url)
        self.assertRedirects(response, reverse("order_all"))
        self.assertIsNotNone(self.fresh(self.loan).end_at)

    def test_return_through_the_api(self):
        path = f"/api/v1/order/{self.loan.pk}/"
        body = {"end_at": timezone.now().isoformat()}
        self.assertEqual(self.api(self.borrower, "patch", path, body).status_code, 403)
        self.assertIsNone(self.fresh(self.loan).end_at)
        self.assertEqual(self.api(self.librarian, "patch", path, body).status_code, 200)
        self.assertIsNotNone(self.fresh(self.loan).end_at)

    def test_return_in_the_admin_site(self):
        url = f"/admin/order/order/{self.loan.pk}/change/"
        form = self.admin_form(end_at_0="2030-01-10", end_at_1="10:00:00")
        self.assertAdminSignIn(self.signed_in(self.borrower).post(url, form), url)
        self.assertIsNone(self.fresh(self.loan).end_at)
        response = self.signed_in(self.librarian).post(url, form)
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(self.fresh(self.loan).end_at)

    # Reopen

    def test_reopen_on_the_web(self):
        url = reverse("order_update", args=[self.returned.pk])
        form = {"plated_end_at": "2030-01-15T12:00", "end_at": ""}
        self.assertEqual(self.signed_in(self.borrower).post(url, form).status_code, 403)
        self.assertIsNotNone(self.fresh(self.returned).end_at)
        response = self.signed_in(self.librarian).post(url, form)
        self.assertRedirects(response, reverse("order_all"))
        self.assertIsNone(self.fresh(self.returned).end_at)

    def test_reopen_through_the_api(self):
        path = f"/api/v1/order/{self.returned.pk}/"
        body = {"end_at": None}
        self.assertEqual(self.api(self.borrower, "patch", path, body).status_code, 403)
        self.assertIsNotNone(self.fresh(self.returned).end_at)
        self.assertEqual(self.api(self.librarian, "patch", path, body).status_code, 200)
        self.assertIsNone(self.fresh(self.returned).end_at)

    def test_reopen_in_the_admin_site(self):
        url = f"/admin/order/order/{self.returned.pk}/change/"
        form = self.admin_form()
        self.assertAdminSignIn(self.signed_in(self.borrower).post(url, form), url)
        self.assertIsNotNone(self.fresh(self.returned).end_at)
        response = self.signed_in(self.librarian).post(url, form)
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.fresh(self.returned).end_at)

    # Reassign

    def test_reassign_through_the_api(self):
        path = f"/api/v1/order/{self.loan.pk}/"
        changes = ({"book": self.other_book.pk}, {"user": self.other.pk})
        for change in changes:
            with self.subTest(change=change):
                response = self.api(self.borrower, "patch", path, change)
                self.assertEqual(response.status_code, 403)
        loan = self.fresh(self.loan)
        self.assertEqual((loan.book, loan.user), (self.book, self.borrower))
        for change in changes:
            response = self.api(self.librarian, "patch", path, change)
            self.assertEqual(response.status_code, 200)
        loan = self.fresh(self.loan)
        self.assertEqual((loan.book, loan.user), (self.other_book, self.other))

    def test_reassign_in_the_admin_site(self):
        url = f"/admin/order/order/{self.loan.pk}/change/"
        form = self.admin_form(user=self.other.pk, book=self.other_book.pk)
        self.assertAdminSignIn(self.signed_in(self.borrower).post(url, form), url)
        loan = self.fresh(self.loan)
        self.assertEqual((loan.book, loan.user), (self.book, self.borrower))
        response = self.signed_in(self.librarian).post(url, form)
        self.assertEqual(response.status_code, 302)
        loan = self.fresh(self.loan)
        self.assertEqual((loan.book, loan.user), (self.other_book, self.other))

    # Delete

    def test_delete_through_the_api(self):
        path = f"/api/v1/order/{self.loan.pk}/"
        self.assertEqual(self.api(self.borrower, "delete", path).status_code, 403)
        self.assertIsNotNone(self.fresh(self.loan))
        self.assertEqual(self.api(self.librarian, "delete", path).status_code, 204)
        self.assertIsNone(self.fresh(self.loan))

    def test_delete_in_the_admin_site(self):
        url = f"/admin/order/order/{self.loan.pk}/delete/"
        refused = self.signed_in(self.borrower).post(url, {"post": "yes"})
        self.assertAdminSignIn(refused, url)
        self.assertIsNotNone(self.fresh(self.loan))
        response = self.signed_in(self.librarian).post(url, {"post": "yes"})
        self.assertRedirects(
            response, "/admin/order/order/", fetch_redirect_response=False
        )
        self.assertIsNone(self.fresh(self.loan))
