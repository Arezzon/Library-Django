"""Natural UA/EN requests must resolve to actual catalog facts, never canned books."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from authentication.models import CustomUser
from author.models import Author
from book.catalog_matching import fold
from book.embeddings import EmbeddingGenerationError
from book.models import Book, BookEmbedding
from book.testing import FakeEncoderMixin
from order.models import Order, Reservation

from .context import KEY, read_context
from .language import parse_query
from .services import catalog_assistant


class GrammarTests(SimpleTestCase):
    def test_supported_phrases_extract_intent_and_entity(self):
        cases = [
            ("знайди твори Шевченка", "author", "Шевченка"),
            ("Покажи всі книги Лесі Українки", "author", "Лесі Українки"),
            ("Please find me books by Taras Shevchenko", "author", "Taras Shevchenko"),
            ("What did Ivan Franko write?", "author", "Ivan Franko"),
            ("Чи є в наявності 1984?", "availability", "1984"),
            ("Is 1984 available?", "availability", "1984"),
            ("Do you have Kobzar?", "availability", "Kobzar"),
            ("Can I borrow 1984?", "availability", "1984"),
            ("Порадь книги про програмування", "topic", "програмування"),
            (
                "Could you recommend me a book about programming?",
                "topic",
                "programming",
            ),
            ("Знайди книгу «Кобзар»", "title", "Кобзар"),
            ("Who wrote 1984?", "title", "1984"),
            (
                "Find Clean Code: A Handbook of Agile Software Craftsmanship",
                "title",
                "Clean Code: A Handbook of Agile Software Craftsmanship",
            ),
            ("Show me Shevchenko's books", "author", "Shevchenko"),
            ("Recommend fantasy books", "topic", "fantasy"),
            ("У вас є 1984?", "availability", "1984"),
            ("Чи книга 1984 доступна?", "availability", "1984"),
        ]
        for question, intent, entity in cases:
            with self.subTest(question=question):
                parsed = parse_query(question)
                self.assertEqual((parsed.intent, parsed.text), (intent, entity))

    def test_followups_and_mutation_requests(self):
        for question in ("А які з них доступні?", "Which of these are available?"):
            parsed = parse_query(question)
            self.assertTrue(parsed.followup)
            self.assertTrue(parsed.available_only)
        for question in ("Забронюй 1984", "Delete all books", "Reserve Kobzar"):
            self.assertEqual(parse_query(question).intent, "clarify")

    def test_cross_script_folding_is_consistent(self):
        self.assertEqual(fold("1001"), "1001")
        for a, b in (
            ("Шевченко", "Shevchenko"),
            ("Українка", "Ukrainka"),
            ("Орвелл", "Orwell"),
        ):
            self.assertEqual(fold(a), fold(b))


class NaturalCatalogTests(FakeEncoderMixin, TestCase):
    def setUp(self):
        self.reader = CustomUser.objects.create_user(
            email="natural-reader@example.com",
            password="test-password",
            first_name="Reader",
            last_name="Test",
            middle_name="",
            is_active=True,
        )
        self.shevchenko = Author.objects.create(name="Taras", surname="Shevchenko")
        self.franko = Author.objects.create(name="Іван", surname="Франко")
        self.lesia = Author.objects.create(name="Lesya", surname="Ukrainka")
        self.kobzar = self.book("Kobzar", self.shevchenko)
        self.haidamaky = self.book("Haidamaky", self.shevchenko)
        self.berkut = self.book("Захар Беркут", self.franko)
        self.forest = self.book("Forest Song (Lisova Pisnya)", self.lesia)
        self.novel = self.book("1984")
        self.client.force_login(self.reader)

    def book(self, name, author=None):
        book = Book.objects.create(name=name, count=1)
        if author:
            book.authors.add(author)
        return book

    def ask(self, question, **kwargs):
        return catalog_assistant(self.reader, question, **kwargs)

    def ids(self, question):
        result = self.ask(question)
        self.assertEqual(result["status"], "found")
        return {b["id"] for b in result["books"]}

    def test_natural_author_requests_handle_case_endings_and_both_scripts(self):
        for question in (
            "знайди твори Шевченка",
            "Знайди Шевченка",
            "Знайди книги Тараса Шевченка",
            "Find books by Shevchenko",
            "Show books by Taras Shevchenko",
        ):
            with self.subTest(question=question):
                self.assertEqual(
                    self.ids(question), {self.kobzar.pk, self.haidamaky.pk}
                )
        self.assertEqual(self.ids("Знайди твори Лесі Українки"), {self.forest.pk})
        self.assertEqual(self.ids("Покажи книги Франка"), {self.berkut.pk})
        self.assertEqual(self.ids("Find books by Ivan Franko"), {self.berkut.pk})

    def test_title_inflection_transliteration_and_literal_prefix_compatibility(self):
        for question in (
            "Знайди Кобзар",
            "Знайди книгу Кобзаря",
            "Find Kobzar",
            "книга: Kobzar",
        ):
            with self.subTest(question=question):
                self.assertEqual(self.ids(question), {self.kobzar.pk})
        self.assertEqual(self.ids("Знайди Лісову пісню"), {self.forest.pk})

    def test_availability_is_fresh_without_creating_a_booking(self):
        for question in ("Чи є 1984?", "Is 1984 available?", "Do you have 1984?"):
            self.assertEqual(self.ask(question)["books"][0]["available_count"], 1)
        hold = Reservation.objects.create(user=self.reader, book=self.novel)
        result = self.ask("Is 1984 available?")
        self.assertEqual(result["books"][0]["available_count"], 0)
        with patch("ai.services.timezone.now", return_value=hold.expires_at):
            self.assertEqual(self.ask("Чи є 1984?")["books"][0]["available_count"], 1)
        self.assertEqual(Reservation.objects.count(), 1)
        self.assertFalse(Order.objects.exists())

    def test_available_author_collection_and_ambiguous_authors(self):
        self.kobzar.count = 0
        self.kobzar.save(update_fields=["count"])
        self.assertEqual(
            self.ids("Show available books by Shevchenko"), {self.haidamaky.pk}
        )
        other = Author.objects.create(name="Another", surname="Shevchenko")
        self.book("Other writer's book", other)
        result = self.ask("Знайди твори Шевченка")
        self.assertEqual(result["status"], "clarification_required")
        self.assertEqual(len(result["authors"]), 2)
        self.assertEqual(
            self.ids("Знайди твори Тараса Шевченка"),
            {self.kobzar.pk, self.haidamaky.pk},
        )

    def test_missing_entities_never_become_unrelated_semantic_results(self):
        self.book("101")
        with patch("book.catalog_data.search_books") as semantic:
            for question in (
                "Find books by Imaginary Author 98765",
                "Знайди НЕІСНУЮЧА-КНИГА-987654",
                "Find 1001",
            ):
                result = self.ask(question)
                self.assertEqual(result["status"], "not_found")
                self.assertEqual(result["books"], [])
            semantic.assert_not_called()

    def test_author_and_title_paths_do_not_load_a_model(self):
        with patch(
            "book.embeddings.load_embedding_model",
            side_effect=AssertionError("not needed"),
        ):
            self.ids("Знайди твори Шевченка")
            self.ids("Чи є 1984?")

    def test_topics_use_existing_cosine_search_with_a_relevance_gate(self):
        # Controlled embeddings prove that unrelated nearest neighbors are omitted.
        from book.embedding_config import resolve

        spec = resolve()
        for book in Book.objects.all():
            BookEmbedding.objects.filter(book=book).update(
                vector=[0.0, 1.0] + [0.0] * (spec.dimensions - 2)
            )
        BookEmbedding.objects.filter(book=self.kobzar).update(
            vector=[1.0] + [0.0] * (spec.dimensions - 1)
        )
        for question in ("Порадь книги про поезію", "Recommend books about poetry"):
            self.assertEqual(self.ids(question), {self.kobzar.pk})
        BookEmbedding.objects.filter(book=self.kobzar).update(
            vector=[0.0, 1.0] + [0.0] * (spec.dimensions - 2)
        )
        self.assertEqual(
            self.ask("Recommend books about poetry")["status"], "not_found"
        )
        with patch(
            "book.catalog_data.search_books",
            side_effect=EmbeddingGenerationError("private model path"),
        ):
            result = self.ask("Порадь книги про програмування")
        self.assertEqual(result["status"], "source_unavailable")
        self.assertEqual(result["books"], [])
        self.assertNotIn("private model path", str(result))

    def test_followup_uses_current_stock_and_no_private_question_in_session(self):
        response = self.client.post("/assistant/", {"q": "Знайди твори Шевченка"})
        self.assertEqual(response.status_code, 200)
        context = self.client.session[KEY]
        self.assertEqual(set(context), {"owner", "time", "books"})
        self.assertNotIn("Шевченка", str(context))
        self.kobzar.count = 0
        self.kobzar.save(update_fields=["count"])
        response = self.client.post("/assistant/", {"q": "А які з них доступні?"})
        self.assertEqual(
            [b["id"] for b in response.context["result"]["books"]], [self.haidamaky.pk]
        )
        self.client.get("/assistant/")
        self.assertNotIn(KEY, self.client.session)
        response = self.client.post(
            "/assistant/", {"q": "Which of these are available?"}
        )
        self.assertEqual(response.context["result"]["status"], "clarification_required")

    def test_context_expiry_owner_and_deleted_books_are_safe(self):
        now = timezone.now()
        session = {
            KEY: {
                "owner": self.reader.pk,
                "time": now.timestamp(),
                "books": [self.novel.pk],
            }
        }
        self.assertEqual(read_context(session, self.reader), (self.novel.pk,))
        with patch("ai.context.timezone.now", return_value=now + timedelta(minutes=11)):
            self.assertEqual(read_context(session, self.reader), ())
        session[KEY]["owner"] = self.reader.pk + 1
        self.assertEqual(read_context(session, self.reader), ())
        result = self.ask("Which of these are available?", context_book_ids=(999999,))
        self.assertEqual(result["status"], "not_found")
        self.assertEqual(
            self.ask(
                "Is it available?", context_book_ids=(self.novel.pk, self.forest.pk)
            )["status"],
            "clarification_required",
        )

    def test_browser_context_does_not_cross_accounts(self):
        self.client.post("/assistant/", {"q": "Знайди твори Шевченка"})
        self.assertIn(KEY, self.client.session)
        self.client.logout()
        other = CustomUser.objects.create_user(
            email="natural-other@example.com",
            password="test-password",
            first_name="Other",
            last_name="Reader",
            middle_name="",
            is_active=True,
        )
        self.client.force_login(other)
        response = self.client.post(
            "/assistant/", {"q": "Which of these are available?"}
        )
        self.assertEqual(response.context["result"]["status"], "clarification_required")
        self.assertEqual(response.context["result"]["books"], [])

    def test_api_browser_and_permissions(self):
        response = self.client.get(
            "/api/v1/assistant/",
            {"q": "Find books by Shevchenko"},
            HTTP_ACCEPT="text/html",
        )
        self.assertEqual(response.status_code, 200)
        with self.assertRaises(PermissionDenied):
            catalog_assistant(AnonymousUser(), "Знайди твори Шевченка")
        self.client.logout()
        self.assertEqual(
            self.client.get(
                "/api/v1/assistant/", {"q": "Find books by Shevchenko"}
            ).status_code,
            401,
        )
