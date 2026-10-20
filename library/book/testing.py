"""Test helpers: a deterministic stand-in for the embedding model.

Default test runs must not execute the real model (constitution, Principle III),
including in setUpTestData, which runs inside setUpClass.
"""

from unittest.mock import patch

from .embedding_config import resolve


def fake_vectors(texts, **kwargs):
    return [[1.0] + [0.0] * (resolve().dimensions - 1) for _ in texts]


class FakeEncoderMixin:
    """Mock book.embeddings.load_embedding_model for the whole test class."""

    @classmethod
    def setUpClass(cls):
        patcher = patch("book.embeddings.load_embedding_model")
        patcher.start().return_value.embed.side_effect = fake_vectors
        cls.addClassCleanup(patcher.stop)
        super().setUpClass()
