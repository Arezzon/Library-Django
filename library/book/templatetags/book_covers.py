"""Resolve bundled covers without network requests or database changes."""

import json
from pathlib import Path

from django import template

register = template.Library()
COVERS = json.loads(
    (Path(__file__).resolve().parents[1] / "covers.json").read_text(encoding="utf-8")
)


@register.simple_tag
def book_cover(book):
    """Match catalog titles independently of IDs; unknown titles get a placeholder."""
    return COVERS.get(book.name.strip().casefold(), {}).get(
        "file", "book/covers/placeholder.svg"
    )
