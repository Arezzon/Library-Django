"""Semantic API and catalog regressions, including the real seeded catalog."""

import json
import os
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from authentication.models import CustomUser

from .embedding_config import resolve
from .models import Book, BookEmbedding
from .search import search_books
from .views import _filter_books


class SemanticSearchTests(TestCase):
    def setUp(self):
        self.patcher = patch("book.embeddings.load_embedding_model")
        self.encoder = self.patcher.start().return_value
        self.addCleanup(self.patcher.stop)
        self.spec = resolve()
        dimensions = self.spec.dimensions
        self.encoder.embed.side_effect = lambda texts, **kwargs: [
            [1.0] + [0.0] * (dimensions - 1) for _ in texts
        ]
        self.first = Book.objects.create(name="Different words", count=3)
        self.second = Book.objects.create(name="Second")
        BookEmbedding.objects.filter(book=self.second).update(
            vector=[0.0, 1.0] + [0.0] * (dimensions - 2)
        )
        for book in (self.first, self.second):
            embedding = BookEmbedding.objects.get(book=book)
            self.assertEqual(embedding.model, self.spec.repository)
            self.assertEqual(embedding.model_revision, self.spec.tag)
        self.client = APIClient()
        self.client.force_login(
            CustomUser.objects.create_user(
                email="semantic-reader@example.com",
                password="test-password",
                first_name="Test",
                middle_name="",
                last_name="Reader",
                is_active=True,
            )
        )

    def test_cosine_order_prefix_and_availability(self):
        response = self.client.get("/api/v1/books/search/", {"q": "  concept  "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [b["id"] for b in response.json()], [self.first.pk, self.second.pk]
        )
        self.assertEqual(response.json()[0]["available_count"], 3)
        self.assertAlmostEqual(response.json()[0]["similarity"], 1)
        self.assertAlmostEqual(response.json()[1]["similarity"], 0)
        self.encoder.embed.assert_called_with(
            [self.spec.query_prefix + "concept"], batch_size=1
        )
        books = list(search_books(Book.objects.all(), "concept"))
        self.assertAlmostEqual(books[0].similarity, 1)
        self.assertAlmostEqual(books[1].similarity, 0)

    def test_invalid_queries_do_not_encode(self):
        self.encoder.reset_mock()
        for q in ("", "   ", "x" * 513):
            self.assertEqual(
                self.client.get("/api/v1/books/search/", {"q": q}).status_code, 400
            )
        self.assertEqual(self.client.get("/api/v1/books/search/").status_code, 400)
        self.encoder.embed.assert_not_called()

    def test_encoder_failure_is_service_unavailable(self):
        self.encoder.embed.side_effect = RuntimeError("unavailable")
        self.assertEqual(
            self.client.get("/api/v1/books/search/", {"q": "topic"}).status_code, 503
        )

    def test_missing_and_incompatible_vectors_are_excluded(self):
        BookEmbedding.objects.filter(book=self.first).delete()
        BookEmbedding.objects.filter(book=self.second).update(model_revision="old")
        self.assertEqual(
            self.client.get("/api/v1/books/search/", {"q": "topic"}).json(), []
        )

    def test_catalog_page_renders_results_and_errors(self):
        user = CustomUser.objects.create_user(
            email="search@example.com",
            password="test-password",
            first_name="Test",
            middle_name="",
            last_name="Reader",
            is_active=True,
        )
        self.client.force_login(user)
        with patch("events.middleware.capture"):
            response = self.client.get("/book/", {"q": "concept"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(list(response.context["books"])[0], self.first)
            self.encoder.embed.side_effect = RuntimeError("offline")
            response = self.client.get("/book/", {"q": "concept"})
        self.assertContains(response, "Search is temporarily unavailable.")
        self.assertEqual(list(response.context["books"]), [])

    def test_catalog_preserves_author_filter(self):
        from author.models import Author

        author = Author.objects.create(name="Test", surname="Writer")
        self.second.authors.add(author)
        self.assertEqual(list(_filter_books("topic", str(author.pk))), [self.second])

    def test_ties_limit_and_catalog_integration(self):
        for i in range(22):
            Book.objects.create(name=f"Item {i}")
        data = self.client.get("/api/v1/books/search/", {"q": "topic"}).json()
        self.assertEqual(len(data), 20)
        self.assertEqual([b["id"] for b in data], sorted(b["id"] for b in data))
        self.assertEqual(
            list(_filter_books("topic", "").values_list("id", flat=True)),
            [b["id"] for b in data],
        )
        self.assertEqual(_filter_books("", "").count(), 24)


EVALUATION_SET = Path(__file__).with_name("search_evaluation.json")


@skipUnless(
    os.getenv("RUN_BOOK_EMBEDDING_MODEL_TESTS") == "1",
    "Real model test enabled in Docker CI",
)
class SearchEvaluationTests(TestCase):
    """FR-032 / SC-013: English and Ukrainian queries rank the expected seed book first."""

    def test_every_evaluation_query_ranks_its_expected_book_first(self):
        from seed_db import seed_data

        seed_data()
        cases = json.loads(EVALUATION_SET.read_text(encoding="utf-8"))
        self.assertEqual(len(cases), 18)
        client = APIClient()
        client.force_login(CustomUser.objects.get(email="reader@library.com"))
        for case in cases:
            with self.subTest(query=case["query"]):
                response = client.get("/api/v1/books/search/", {"q": case["query"]})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()[0]["name"], case["expected"])
