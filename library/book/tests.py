from datetime import timedelta
import math
import os
from io import StringIO
from unittest import skipUnless
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.messages import get_messages
from django.db import connection, models
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import CustomUser, ROLE_LIBRARIAN
from author.models import Author
from order.models import Order

from .models import Book, BookEmbedding
from .embeddings import (
    DIMENSIONS, MODEL_NAME, MODEL_REVISION, EmbeddingGenerationError,
    document_text, input_hash,
)
from .serializers import BookSerializer
from .views import _filter_books


class BookAvailabilityTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        patcher = patch('book.embeddings.load_embedding_model')
        loader = patcher.start()
        cls.addClassCleanup(patcher.stop)
        loader.return_value.embed.side_effect = lambda texts, **kwargs: [[1.0] * DIMENSIONS for _ in texts]

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
        models.QuerySet(model=Book, using='default').bulk_create([Book(name=f'Book {i}', count=5) for i in range(8)])
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


@skipUnless(connection.vendor == 'postgresql', 'pgvector requires PostgreSQL')
class BookEmbeddingCommandTests(TestCase):
    def setUp(self):
        # Simulate pre-existing/bulk-imported books that need backfilling.
        self.book = Book(name='Кобзар', description='Збірка української поезії.')
        models.QuerySet(model=Book, using='default').bulk_create([self.book])
        self.output = StringIO()
        self.model = MagicMock()
        self.model.embed.side_effect = lambda texts, **kwargs: [[1.0] * DIMENSIONS for _ in texts]
        self.loader = patch(
            'book.management.commands.generate_book_embeddings.load_embedding_model',
            return_value=self.model,
        ).start()
        self.addCleanup(patch.stopall)

    def generate(self, **options):
        call_command('generate_book_embeddings', stdout=self.output, stderr=StringIO(), **options)

    def test_generation_persists_normalized_vector_and_provenance(self):
        self.generate()
        embedding = BookEmbedding.objects.get(book=self.book)
        self.assertEqual(len(embedding.vector), DIMENSIONS)
        self.assertAlmostEqual(sum(float(x) ** 2 for x in embedding.vector), 1, places=5)
        self.assertEqual(embedding.model, MODEL_NAME)
        self.assertEqual(embedding.model_revision, MODEL_REVISION)
        self.assertEqual(embedding.input_hash, input_hash(document_text(self.book.name, self.book.description)))
        self.assertEqual(self.model.embed.call_args.args[0], ['passage: Кобзар\nЗбірка української поезії.'])
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_typeof(vector)::text, vector_dims(vector) FROM book_bookembedding')
            self.assertEqual(cursor.fetchone(), ('vector', DIMENSIONS))

    def test_unchanged_books_do_not_reload_model_or_update_record(self):
        self.generate()
        timestamp = BookEmbedding.objects.get(book=self.book).updated_at
        self.loader.reset_mock()
        self.generate(offline=True)
        self.loader.assert_not_called()
        self.assertEqual(BookEmbedding.objects.get(book=self.book).updated_at, timestamp)

    def test_changed_description_and_title_are_regenerated(self):
        self.generate()
        for field in ('description', 'name'):
            with self.subTest(field=field):
                old_hash = BookEmbedding.objects.get(book=self.book).input_hash
                setattr(self.book, field, getattr(self.book, field) + ' новий текст')
                models.QuerySet(model=Book, using='default').filter(pk=self.book.pk).update(**{field: getattr(self.book, field)})
                self.generate()
                self.assertNotEqual(BookEmbedding.objects.get(book=self.book).input_hash, old_hash)

    def test_model_revision_change_is_regenerated(self):
        self.generate()
        BookEmbedding.objects.filter(book=self.book).update(model_revision='0' * 40)
        self.loader.reset_mock()
        self.generate()
        self.loader.assert_called_once()
        self.assertEqual(BookEmbedding.objects.get(book=self.book).model_revision, MODEL_REVISION)

    def test_force_regenerates_unchanged_embeddings(self):
        self.generate()
        self.loader.reset_mock()
        self.generate(force=True, offline=True)
        self.loader.assert_called_once_with(offline=True)
        self.assertEqual(BookEmbedding.objects.count(), 1)

    def test_empty_descriptions_generate_title_embeddings(self):
        self.generate()
        models.QuerySet(model=Book, using='default').filter(pk=self.book.pk).update(description='  ')
        self.loader.reset_mock()
        self.generate()
        self.loader.assert_called_once()
        self.assertEqual(self.model.embed.call_args.args[0], ['passage: Кобзар'])
        self.assertTrue(BookEmbedding.objects.exists())

    def test_batch_size_and_book_selection(self):
        books = [Book(name=str(i), description='A book description') for i in range(4)]
        models.QuerySet(model=Book, using='default').bulk_create(books)
        self.generate(batch_size=2)
        self.assertEqual([len(call.args[0]) for call in self.model.embed.call_args_list], [2, 2, 1])
        self.assertEqual(BookEmbedding.objects.count(), 5)
        BookEmbedding.objects.all().delete()
        self.generate(book_ids=[books[0].pk])
        self.assertEqual(list(BookEmbedding.objects.values_list('book_id', flat=True)), [books[0].pk])

    def test_invalid_vectors_and_missing_output_are_not_saved(self):
        for output in ([[0.0] * DIMENSIONS], [[float('nan')] * DIMENSIONS], [[1.0] * 3], []):
            with self.subTest(length=len(output)):
                self.model.embed.side_effect = None
                self.model.embed.return_value = output
                with self.assertRaises(CommandError):
                    self.generate()
                self.assertFalse(BookEmbedding.objects.exists())

    def test_failure_preserves_previously_generated_embedding(self):
        self.generate()
        timestamp = BookEmbedding.objects.get(book=self.book).updated_at
        self.model.embed.side_effect = RuntimeError('Inference failed')
        with self.assertRaisesMessage(CommandError, 'Embedding generation failed'):
            self.generate(force=True)
        self.assertEqual(BookEmbedding.objects.get(book=self.book).updated_at, timestamp)

    def test_download_failure_is_actionable_and_does_not_write(self):
        self.loader.side_effect = RuntimeError('Model unavailable')
        with self.assertRaisesMessage(CommandError, 'Cannot load embedding model'):
            self.generate()
        self.assertFalse(BookEmbedding.objects.exists())

    def test_description_changed_during_inference_is_not_saved(self):
        def encode(texts, **kwargs):
            models.QuerySet(model=Book, using='default').filter(pk=self.book.pk).update(description='Changed during inference')
            return [[1.0] * DIMENSIONS]
        self.model.embed.side_effect = encode
        self.generate()
        self.assertFalse(BookEmbedding.objects.exists())
        self.assertIn('changed during inference: 1', self.output.getvalue())

    def test_deleted_book_is_not_recreated_during_inference(self):
        def encode(texts, **kwargs):
            self.book.delete()
            return [[1.0] * DIMENSIONS]
        self.model.embed.side_effect = encode
        self.generate()
        self.assertFalse(BookEmbedding.objects.exists())

    def test_invalid_arguments_do_not_load_model(self):
        for options in ({'batch_size': 0}, {'batch_size': -1}, {'book_ids': [999999]}, {'database': 'missing'}):
            with self.subTest(options=options), self.assertRaises(CommandError):
                self.generate(**options)
        self.loader.assert_not_called()

    def test_non_postgresql_database_is_rejected(self):
        with patch.object(connection, 'vendor', 'sqlite'):
            with self.assertRaisesMessage(CommandError, 'require PostgreSQL'):
                self.generate()
        self.loader.assert_not_called()


@skipUnless(
    connection.vendor == 'postgresql' and os.getenv('RUN_BOOK_EMBEDDING_MODEL_TESTS') == '1',
    'Set RUN_BOOK_EMBEDDING_MODEL_TESTS=1 for real ONNX inference (enabled in Docker CI)',
)
class RealBookEmbeddingTests(TestCase):
    def test_compact_tokenizer_matches_reference_xlm_roberta_ids(self):
        from .embeddings import load_embedding_model
        model = load_embedding_model(offline=True)
        # Golden IDs from the pinned Hugging Face tokenizer.json artifact.
        for text, expected in [
            ('passage: Книга про історію України', [0, 46692, 12, 136429, 591, 169293, 2513, 2]),
            ('passage: A book about Ukraine', [0, 46692, 12, 62, 12877, 1672, 82739, 2]),
            ('', [0, 2]),
        ]:
            pieces = model.tokenizer.encode(text, out_type=int)
            self.assertEqual([0] + [piece + 1 if piece else 3 for piece in pieces] + [2], expected)

    def test_int8_encoder_handles_multilingual_and_truncated_documents(self):
        from .embeddings import load_embedding_model, normalized_vector
        model = load_embedding_model(offline=True)
        texts = ['passage: Книга про історію України',
                 'passage: A book about the history of Ukraine',
                 'passage: ' + 'довгий текст ' * 600]
        vectors = list(model.embed(texts, batch_size=3))
        self.assertEqual(len(vectors), 3)
        for vector in vectors:
            self.assertEqual(len(vector), DIMENSIONS)
            self.assertAlmostEqual(sum(value * value for value in vector), 1, places=5)
            self.assertEqual(len(normalized_vector(vector)), DIMENSIONS)
        self.assertNotEqual(vectors[0], vectors[1])

    def test_real_multilingual_model_and_pgvector_distance_query(self):
        from pgvector.django import CosineDistance
        for name, description in [
            ('Кобзар', 'Збірка української поезії Тараса Шевченка.'),
            ('1984', 'A dystopian novel about surveillance and totalitarian government.'),
        ]:
            Book.objects.create(name=name, description=description)
        # The initial vectors must already exist, without running the command.
        self.assertEqual(BookEmbedding.objects.count(), 2)
        call_command('generate_book_embeddings', batch_size=2, force=True, stdout=StringIO())
        embeddings = list(BookEmbedding.objects.order_by('book_id'))
        self.assertEqual(len(embeddings), 2)
        for embedding in embeddings:
            self.assertEqual(len(embedding.vector), DIMENSIONS)
            self.assertTrue(all(math.isfinite(float(x)) for x in embedding.vector))
            self.assertAlmostEqual(sum(float(x) ** 2 for x in embedding.vector), 1, places=4)
        distances = list(BookEmbedding.objects.annotate(
            distance=CosineDistance('vector', embeddings[0].vector),
        ).order_by('distance').values_list('distance', flat=True))
        self.assertAlmostEqual(distances[0], 0, places=5)
        self.assertTrue(all(math.isfinite(distance) for distance in distances))


@skipUnless(connection.vendor == 'postgresql', 'pgvector requires PostgreSQL')
class AutomaticBookEmbeddingTests(TestCase):
    def setUp(self):
        self.model = MagicMock()
        self.model.embed.side_effect = lambda texts, **kwargs: [
            [1.0, float(sum(map(ord, text)) % 1000 + 1)] + [0.0] * (DIMENSIONS - 2)
            for text in texts
        ]
        patcher = patch('book.embeddings.load_embedding_model', return_value=self.model)
        self.loader = patcher.start()
        self.addCleanup(patcher.stop)

    def create_book(self):
        return Book.objects.create(name='Кобзар', description='Українська поезія', count=3)

    def librarian(self):
        return CustomUser.objects.create_user(
            email='embedding-librarian@example.com', password='test-password',
            first_name='Test', middle_name='', last_name='Librarian',
            role=ROLE_LIBRARIAN, is_active=True,
        )

    def assert_current(self, book):
        book.refresh_from_db()
        embedding = BookEmbedding.objects.get(book=book)
        self.assertEqual(embedding.input_hash, input_hash(document_text(book.name, book.description)))
        self.assertEqual(len(embedding.vector), DIMENSIONS)
        return embedding

    def test_creation_and_text_changes_generate_without_command(self):
        book = self.create_book()
        previous_hash = book.embedding.input_hash  # Populate reverse relation cache.
        for field, value in [('description', 'Новий опис про історію'), ('name', 'Нова назва')]:
            setattr(book, field, value)
            book.save(update_fields=[field])
            self.assertNotEqual(book.embedding.input_hash, previous_hash)
            previous_hash = self.assert_current(book).input_hash
        self.assertEqual(self.model.embed.call_count, 3)
        self.assertEqual(BookEmbedding.objects.count(), 1)

    def test_count_and_unchanged_saves_do_not_regenerate(self):
        book = self.create_book()
        timestamp = book.embedding.updated_at
        self.loader.reset_mock()
        book.count = 5
        book.save(update_fields=['count'])
        book.save()
        self.loader.assert_not_called()
        self.assertEqual(BookEmbedding.objects.get(book=book).updated_at, timestamp)

    def test_partial_update_does_not_encode_unpersisted_text(self):
        book = self.create_book()
        digest = book.embedding.input_hash
        self.loader.reset_mock()
        book.description = 'Not persisted'
        book.count = 5
        book.save(update_fields=['count'])
        self.loader.assert_not_called()
        book.refresh_from_db()
        self.assertEqual(book.description, 'Українська поезія')
        self.assertEqual(book.embedding.input_hash, digest)

    def test_empty_description_keeps_title_vector_and_restoring_it_regenerates(self):
        book = self.create_book()
        self.loader.reset_mock()
        book.description = ' '
        book.save(update_fields=['description'])
        self.loader.assert_called_once()
        self.assert_current(book)
        self.assertEqual(self.model.embed.call_args.args[0], ['passage: Кобзар'])
        book.description = 'Оновлена анотація'
        book.save(update_fields=['description'])
        self.assert_current(book)

    def test_generation_failure_rolls_back_creation_and_updates(self):
        book = self.create_book()
        old_hash = book.embedding.input_hash
        self.model.embed.side_effect = RuntimeError('Model failed')
        with self.assertRaises(EmbeddingGenerationError):
            Book.objects.create(name='New', description='Description')
        self.assertEqual(Book.objects.count(), 1)
        book.description = 'New text'
        with self.assertRaises(EmbeddingGenerationError):
            book.save(update_fields=['description'])
        book.refresh_from_db()
        self.assertEqual(book.description, 'Українська поезія')
        self.assertEqual(book.embedding.input_hash, old_hash)

    def test_invalid_model_output_rolls_back_the_book(self):
        self.model.embed.side_effect = lambda *args, **kwargs: [[float('nan')] * DIMENSIONS]
        with self.assertRaises(EmbeddingGenerationError):
            self.create_book()
        self.assertFalse(Book.objects.exists())
        self.assertFalse(BookEmbedding.objects.exists())

    def test_outer_transaction_rolls_back_book_and_vector(self):
        from django.db import transaction
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.create_book()
                raise RuntimeError('Cancel book creation')
        self.assertFalse(Book.objects.exists())
        self.assertFalse(BookEmbedding.objects.exists())

    def test_api_create_and_update_generate_automatically(self):
        client = APIClient()
        response = client.post('/api/v1/book/', {
            'name': 'Book', 'description': 'Initial description', 'count': 2,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        book = Book.objects.get(pk=response.json()['id'])
        old_hash = self.assert_current(book).input_hash
        response = client.patch(f'/api/v1/book/{book.pk}/', {
            'description': 'Updated description',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(self.assert_current(book).input_hash, old_hash)

    def test_api_failure_returns_validation_error_and_preserves_text(self):
        book = self.create_book()
        self.model.embed.side_effect = RuntimeError('Model failed')
        response = APIClient().patch(f'/api/v1/book/{book.pk}/', {
            'description': 'Updated description',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('description', response.json())
        book.refresh_from_db()
        self.assertEqual(book.description, 'Українська поезія')

    def test_web_create_and_edit_generate_automatically(self):
        self.client.force_login(self.librarian())
        response = self.client.post('/book/create/', {
            'name': 'Web book', 'description': 'Initial text', 'count': 2,
        })
        self.assertEqual(response.status_code, 302)
        book = Book.objects.get(name='Web book')
        old_hash = self.assert_current(book).input_hash
        response = self.client.post(f'/book/update/{book.pk}/', {
            'name': book.name, 'description': 'Updated text', 'count': 2,
        })
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(self.assert_current(book).input_hash, old_hash)

    def test_web_failure_displays_form_error_without_creating_book(self):
        self.client.force_login(self.librarian())
        self.model.embed.side_effect = RuntimeError('Model failed')
        response = self.client.post('/book/create/', {
            'name': 'Web book', 'description': 'Initial text', 'count': 2,
        })
        self.assertContains(response, 'Could not generate the book embedding')
        self.assertFalse(Book.objects.exists())

    def admin_payload(self, name, description):
        return {
            'name': name, 'description': description, 'count': 2,
            'order_set-TOTAL_FORMS': '0', 'order_set-INITIAL_FORMS': '0',
            'order_set-MIN_NUM_FORMS': '0', 'order_set-MAX_NUM_FORMS': '1000',
            '_save': 'Save',
        }

    def test_admin_create_and_edit_generate_automatically(self):
        self.client.force_login(self.librarian())
        response = self.client.post('/admin/book/book/add/', self.admin_payload('Admin book', 'Initial text'))
        self.assertEqual(response.status_code, 302)
        book = Book.objects.get(name='Admin book')
        old_hash = self.assert_current(book).input_hash
        response = self.client.post(
            f'/admin/book/book/{book.pk}/change/', self.admin_payload(book.name, 'Updated text'),
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(self.assert_current(book).input_hash, old_hash)

    def test_admin_failure_returns_message_without_creating_book(self):
        self.client.force_login(self.librarian())
        self.model.embed.side_effect = RuntimeError('Model failed')
        response = self.client.post('/admin/book/book/add/', self.admin_payload('Admin book', 'Initial text'))
        self.assertRedirects(response, '/admin/book/book/add/', fetch_redirect_response=False)
        self.assertTrue(any('Could not generate' in str(message) for message in get_messages(response.wsgi_request)))
        self.assertFalse(Book.objects.exists())


    def test_creation_without_description_generates_title_vector(self):
        book = Book.objects.create(name='Title only')
        self.assert_current(book)
        self.assertEqual(self.model.embed.call_args.args[0], ['passage: Title only'])

    def test_save_repairs_missing_stale_hash_and_model_metadata(self):
        book = self.create_book()
        for corruption in (None, {'input_hash': '0' * 64}, {'model': 'old-model'}, {'model_revision': '0' * 40}):
            with self.subTest(corruption=corruption):
                if corruption is None:
                    BookEmbedding.objects.filter(book=book).delete()
                else:
                    BookEmbedding.objects.filter(book=book).update(**corruption)
                self.loader.reset_mock()
                book.save(update_fields=['count'])
                self.loader.assert_called_once()
                embedding = self.assert_current(book)
                self.assertEqual(embedding.model, MODEL_NAME)
                self.assertEqual(embedding.model_revision, MODEL_REVISION)

    def test_bulk_text_writes_are_rejected_without_changes(self):
        book = self.create_book()
        book.name = 'Changed'
        operations = (
            lambda: Book.objects.bulk_create([Book(name='Bulk')]),
            lambda: Book.objects.filter(pk=book.pk).update(name='Changed'),
            lambda: Book.objects.filter(pk=book.pk).update(description='Changed'),
            lambda: Book.objects.bulk_update([book], ['name']),
            lambda: Book.objects.bulk_update([book], ['description', 'count']),
        )
        for operation in operations:
            with self.assertRaisesMessage(ValueError, 'bypasses embeddings'):
                operation()
        self.assertEqual(Book.objects.count(), 1)
        self.assert_current(book)
        self.assertEqual(book.name, 'Кобзар')

    def test_bulk_stock_updates_preserve_current_embedding(self):
        book = self.create_book()
        timestamp = book.embedding.updated_at
        self.loader.reset_mock()
        Book.objects.filter(pk=book.pk).update(count=8)
        book.count = 9
        Book.objects.bulk_update([book], ['count'])
        self.loader.assert_not_called()
        self.assertEqual(self.assert_current(book).updated_at, timestamp)
        self.assertEqual(book.count, 9)


class SeedEmbeddingTests(TestCase):
    def setUp(self):
        self.loader = patch('book.embeddings.load_embedding_model').start()
        self.command_loader = patch('book.management.commands.generate_book_embeddings.load_embedding_model').start()
        self.addCleanup(patch.stopall)
        model = self.loader.return_value
        self.command_loader.return_value = model
        model.embed.side_effect = lambda texts, **kwargs: iter(
            [[1.0] + [0.0] * (DIMENSIONS - 1) for _ in texts]
        )

    def test_fresh_seed_creates_embeddings_and_repeat_keeps_timestamps(self):
        from seed_db import seed_data
        seed_data()
        self.assertEqual(Book.objects.count(), 9)
        self.assertEqual(BookEmbedding.objects.count(), 9)
        before = dict(BookEmbedding.objects.values_list('book_id', 'updated_at'))
        seed_data()
        self.assertEqual(before, dict(BookEmbedding.objects.values_list('book_id', 'updated_at')))

    def test_existing_users_do_not_skip_legacy_book_embeddings(self):
        from seed_db import seed_data
        CustomUser.objects.create_user(email='legacy@example.com', password='test-password', first_name='Legacy', middle_name='', last_name='Reader', is_active=True)
        models.QuerySet(model=Book, using='default').bulk_create([Book(name='Legacy', description='Existing description')])
        seed_data()
        book = Book.objects.get(name='Legacy')
        self.assertEqual(book.embedding.input_hash, input_hash(document_text(book.name, book.description)))

    def test_seed_generation_failure_propagates(self):
        from seed_db import seed_data
        CustomUser.objects.create_user(email='legacy@example.com', password='test-password', first_name='Legacy', middle_name='', last_name='Reader', is_active=True)
        models.QuerySet(model=Book, using='default').bulk_create([Book(name='Legacy', description='Existing description')])
        self.command_loader.side_effect = RuntimeError('Model unavailable')
        with self.assertRaises(CommandError):
            seed_data()
        self.assertFalse(BookEmbedding.objects.exists())

    def test_failed_fresh_seed_rolls_back_users_authors_and_books(self):
        from seed_db import seed_data
        self.loader.side_effect = RuntimeError('Model unavailable')
        with self.assertRaises(EmbeddingGenerationError):
            seed_data()
        self.assertFalse(CustomUser.objects.exists())
        self.assertFalse(Author.objects.exists())
        self.assertFalse(Book.objects.exists())
