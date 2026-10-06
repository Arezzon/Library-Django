from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import CustomUser
from author.models import Author
from order.models import Order

from .models import Book
from .serializers import BookSerializer
from .views import _filter_books


class BookAvailabilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reader = CustomUser.objects.create_user(
            email='availability@example.com', password='test-password',
            first_name='Test', middle_name='', last_name='Reader', is_active=True,
        )
        cls.book = Book.objects.create(name='Borrowed book', count=3)
        cls.empty_book = Book.objects.create(name='No orders', count=2)
        cls.author = Author.objects.create(name='First', surname='Author')
        second_author = Author.objects.create(name='Second', surname='Author')
        cls.book.authors.add(cls.author, second_author)
        now = timezone.now()
        cls.active_order = Order.objects.create(
            book=cls.book, user=cls.reader, plated_end_at=now + timedelta(days=14),
        )
        # An overdue but unreturned order still occupies a copy.
        Order.objects.create(
            book=cls.book, user=cls.reader, plated_end_at=now - timedelta(days=1),
        )
        Order.objects.create(
            book=cls.book, user=cls.reader, plated_end_at=now, end_at=now,
        )

    def test_only_unreturned_orders_reduce_availability(self):
        annotated = Book.objects.with_availability().get(pk=self.book.pk)
        self.assertEqual(annotated.active_order_count, 2)
        with self.assertNumQueries(0):
            self.assertEqual(annotated.available_count, 1)
        with self.assertNumQueries(1):
            self.assertEqual(self.book.available_count, 1)

    def test_books_without_orders_and_unsaved_books(self):
        book = Book.objects.with_availability().get(pk=self.empty_book.pk)
        self.assertEqual(book.active_order_count, 0)
        self.assertEqual(book.available_count, 2)
        with self.assertNumQueries(0):
            self.assertEqual(Book(count=4).available_count, 4)

    def test_availability_is_never_negative(self):
        Book.objects.filter(pk=self.book.pk).update(count=1)
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_count, 0)
        self.assertEqual(Book.objects.with_availability().get(pk=self.book.pk).available_count, 0)

    def test_author_joins_do_not_multiply_active_orders(self):
        queryset = Book.objects.with_availability().filter(authors__surname='Author')
        self.assertEqual(queryset.get(pk=self.book.pk).available_count, 1)
        filtered = _filter_books('Borrowed', str(self.author.pk))
        self.assertEqual(filtered.get(pk=self.book.pk).available_count, 1)

    def test_returned_order_restores_availability_on_refetch(self):
        self.active_order.end_at = timezone.now()
        self.active_order.save(update_fields=['end_at'])
        self.assertEqual(self.book.available_count, 2)
        self.assertEqual(Book.objects.with_availability().get(pk=self.book.pk).available_count, 2)

    def test_serializing_list_has_constant_query_count(self):
        Book.objects.bulk_create([Book(name=f'Book {i}', count=5) for i in range(8)])
        queryset = Book.objects.with_availability().prefetch_related('authors').order_by('id')
        with self.assertNumQueries(2):
            data = BookSerializer(queryset, many=True).data
        self.assertEqual(len(data), 10)
        self.assertEqual(data[0]['available_count'], 1)
        self.assertEqual(data[-1]['available_count'], 5)

    def test_api_list_and_detail_include_availability(self):
        client = APIClient()
        with self.assertNumQueries(2):
            response = client.get('/api/v1/book/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]['available_count'], 1)
        response = client.get(f'/api/v1/book/{self.book.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['available_count'], 1)

    def test_api_availability_is_read_only_on_create_and_update(self):
        client = APIClient()
        response = client.post('/api/v1/book/', {
            'name': 'New book', 'count': 4, 'available_count': 999,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['available_count'], 4)
        response = client.patch(f'/api/v1/book/{self.book.pk}/', {
            'count': 5, 'available_count': 999,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['available_count'], 3)
