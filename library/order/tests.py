from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from queue import Queue
from threading import Barrier
from time import monotonic, sleep

from django.contrib.messages import get_messages
from django.db import close_old_connections, connection, connections, transaction
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import CustomUser, ROLE_LIBRARIAN
from book.models import Book
from .models import BookUnavailableError, Order


def reader(email, role=0):
    return CustomUser.objects.create_user(
        email=email, password='test-password', first_name='Test',
        middle_name='', last_name='Reader', is_active=True, role=role,
    )


class AtomicIssuanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = reader('reader@example.com')
        cls.book = Book.objects.create(name='Single copy', count=1)

    def issue(self, **kwargs):
        return Order.objects.create(
            user=self.user, book=kwargs.pop('book', self.book),
            plated_end_at=timezone.now() + timedelta(days=14), **kwargs,
        )

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
                book = Book.objects.create(name='Limited', count=count)
                for _ in range(count):
                    self.issue(book=book)
                with self.assertRaises(BookUnavailableError):
                    self.issue(book=book)
                self.assertEqual(book.order_set.count(), count)

    def test_return_releases_a_copy_and_closed_history_does_not_consume_stock(self):
        order = self.issue()
        order.end_at = timezone.now()
        order.save(update_fields=['end_at'])
        self.issue(end_at=timezone.now())
        self.assertEqual(self.book.available_count, 1)
        self.issue()
        self.assertEqual(self.book.available_count, 0)

    def test_outer_transaction_rolls_back_issue(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.issue()
                raise RuntimeError('Cancel issuance')
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.book.available_count, 1)

    def test_existing_active_order_can_be_edited_without_consuming_another_copy(self):
        order = self.issue()
        order.plated_end_at += timedelta(days=1)
        order.save(update_fields=['plated_end_at'])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(self.book.available_count, 0)

    def test_reopening_and_reassignment_cannot_bypass_stock_check(self):
        closed = self.issue(end_at=timezone.now())
        self.issue()
        closed.end_at = None
        with self.assertRaises(BookUnavailableError):
            closed.save(update_fields=['end_at'])
        closed.refresh_from_db()
        self.assertIsNotNone(closed.end_at)
        other_book = Book.objects.create(name='Other', count=1)
        other_order = self.issue(book=other_book)
        other_order.book = self.book
        with self.assertRaises(BookUnavailableError):
            other_order.save(update_fields=['book'])
        other_order.refresh_from_db()
        self.assertEqual(other_order.book_id, other_book.pk)

    def test_partial_update_uses_persisted_occupancy_fields(self):
        closed = self.issue(end_at=timezone.now())
        self.issue()
        closed.end_at = None  # Not part of this partial update.
        closed.plated_end_at += timedelta(days=1)
        closed.save(update_fields=['plated_end_at'])
        closed.refresh_from_db()
        self.assertIsNotNone(closed.end_at)

    def test_both_api_create_routes_reject_exhausted_stock(self):
        client = APIClient()
        payload = {'user': self.user.pk, 'book': self.book.pk,
                   'plated_end_at': (timezone.now() + timedelta(days=14)).isoformat()}
        response = client.post('/api/v1/order/', payload, format='json')
        self.assertEqual(response.status_code, 201)
        for url in ('/api/v1/order/', f'/api/v1/user/{self.user.pk}/order/'):
            with self.subTest(url=url):
                response = client.post(url, payload, format='json')
                self.assertEqual(response.status_code, 400)
                self.assertIn('book', response.json())
        self.assertEqual(Order.objects.count(), 1)

    def test_api_reopening_is_rejected_without_changing_history(self):
        closed = self.issue(end_at=timezone.now())
        self.issue()
        response = APIClient().patch(f'/api/v1/order/{closed.pk}/', {'end_at': None}, format='json')
        self.assertEqual(response.status_code, 400)
        closed.refresh_from_db()
        self.assertIsNotNone(closed.end_at)

    def test_web_form_issues_one_copy(self):
        self.client.force_login(self.user)
        url = f'/order/create/{self.book.pk}/'
        self.assertRedirects(self.client.post(url, {'days': 14}), '/order/my/')
        response = self.client.post(url, {'days': 14})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 1)

    def test_admin_rejects_unavailable_book_with_message(self):
        self.issue()
        librarian = reader('librarian@example.com', ROLE_LIBRARIAN)
        self.client.force_login(librarian)
        response = self.client.post('/admin/order/order/add/', {
            'user': self.user.pk, 'book': self.book.pk,
            'plated_end_at_0': '2026-10-20', 'plated_end_at_1': '12:00:00',
            'end_at_0': '', 'end_at_1': '', '_save': 'Save',
        })
        self.assertRedirects(response, '/admin/order/order/add/', fetch_redirect_response=False)
        self.assertIn(
            'No copies of this book are currently available.',
            [str(message) for message in get_messages(response.wsgi_request)],
        )
        self.assertEqual(Order.objects.count(), 1)


@skipUnlessDBFeature('has_select_for_update')
class ConcurrentIssuanceTests(TransactionTestCase):
    def setUp(self):
        self.book = Book.objects.create(name='Last copy', count=1)
        self.users = [reader(f'reader{i}@example.com') for i in range(2)]

    def worker(self, user_id, barrier=None, backend_queue=None, api=False):
        close_old_connections()
        try:
            book = Book.objects.get(pk=self.book.pk)
            if backend_queue is not None:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()')
                    backend_queue.put(cursor.fetchone()[0])
            if barrier is not None:
                barrier.wait(timeout=10)
            if api:
                return APIClient().post('/api/v1/order/', {
                    'user': user_id, 'book': book.pk,
                    'plated_end_at': timezone.now().isoformat(),
                }, format='json').status_code
            order = Order.create(CustomUser.objects.get(pk=user_id), book, timezone.now())
            return order is not None
        finally:
            connections.close_all()

    def test_parallel_issuance_creates_only_one_active_order(self):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.worker, user.pk, barrier) for user in self.users]
            results = [future.result(timeout=15) for future in futures]
        self.assertCountEqual(results, [True, False])
        self.assertEqual(Order.objects.filter(book=self.book, end_at__isnull=True).count(), 1)
        self.assertEqual(self.book.available_count, 0)

    def test_parallel_api_requests_return_created_and_bad_request(self):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.worker, user.pk, barrier, api=True) for user in self.users]
            self.assertCountEqual([future.result(timeout=15) for future in futures], [201, 400])
        self.assertEqual(Order.objects.count(), 1)

    def test_second_borrower_waits_for_book_lock_and_rechecks_stock(self):
        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL lock observation is required')
        backend_queue = Queue()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Book.objects.select_for_update().get(pk=self.book.pk)
                future = pool.submit(self.worker, self.users[1].pk, backend_queue=backend_queue)
                worker_pid = backend_queue.get(timeout=10)
                deadline = monotonic() + 5
                blocked = False
                while monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT pg_blocking_pids(%s)', [worker_pid])
                        blocked = bool(cursor.fetchone()[0])
                    if blocked:
                        break
                    sleep(0.02)
                self.assertTrue(blocked, 'Second borrower did not wait for the Book row lock')
                self.assertIsNotNone(Order.create(self.users[0], self.book, timezone.now()))
            self.assertFalse(future.result(timeout=10))
        self.assertEqual(Order.objects.count(), 1)
