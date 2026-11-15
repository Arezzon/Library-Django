"""Bundled cover matching and the detail page's compact, accessible presentation."""

from pathlib import Path
from types import SimpleNamespace

from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.test import SimpleTestCase

from .templatetags.book_covers import COVERS, book_cover


class BookCoverTests(SimpleTestCase):
    def test_every_curated_cover_exists_and_has_provenance(self):
        self.assertEqual(len(COVERS), 9)
        for title, cover in COVERS.items():
            with self.subTest(title=title):
                self.assertEqual(book_cover(SimpleNamespace(name=title)), cover["file"])
                self.assertTrue(Path(finders.find(cover["file"])).is_file())
                self.assertTrue(
                    cover["source"].startswith("https://openlibrary.org/works/")
                )

    def test_normalized_title_and_unknown_or_blank_title(self):
        self.assertEqual(
            book_cover(SimpleNamespace(name="  KOBZAR  ")), COVERS["kobzar"]["file"]
        )
        for title in ("A newly added book", "", "<script>alert(1)</script>"):
            path = book_cover(SimpleNamespace(name=title))
            self.assertEqual(path, "book/covers/placeholder.svg")
            self.assertIsNotNone(finders.find(path))

    def test_detail_uses_local_cover_without_distortion_and_escapes_title(self):
        for title in ("Kobzar", 'A <new> "book"'):
            html = render_to_string(
                "book/book_detail.html",
                {
                    "book": SimpleNamespace(
                        name=title, id=12, available_count=1, count=1
                    )
                },
            )
            self.assertIn("object-contain", html)
            self.assertIn('width="80" height="120"', html)
            self.assertIn(static(book_cover(SimpleNamespace(name=title))), html)
            self.assertNotIn('alt="Cover of A <new>', html)
            self.assertIn("Back to Catalog", html)
