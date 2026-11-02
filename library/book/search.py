"""Bounded semantic retrieval with the configured embedding model and pgvector."""

import logging

from pgvector.django import CosineDistance

from . import embeddings
from .embedding_config import resolve
from .embeddings import EmbeddingGenerationError, normalized_vector

MAX_QUERY_LENGTH = 512
RESULT_LIMIT = 20

# Embedding failures share one logger (research R18).
logger = logging.getLogger("book.embeddings")


def validate_query(value):
    query = value.strip()
    if not query or len(query) > MAX_QUERY_LENGTH:
        raise ValueError(f"Provide q with 1–{MAX_QUERY_LENGTH} characters.")
    return query


def search_books(books, query):
    query = validate_query(query)
    spec = resolve()
    try:
        vector = normalized_vector(
            next(
                iter(
                    embeddings.load_embedding_model().embed(
                        [spec.query_prefix + query], batch_size=1
                    )
                )
            )
        )
    except Exception as error:
        # The cause, never the query: it is a person's search (FR-039).
        logger.exception("Could not encode a search query")
        raise EmbeddingGenerationError(
            "Search is temporarily unavailable. Please retry."
        ) from error
    # Rank in PostgreSQL; never load the catalog vectors into web-process memory.
    return (
        books.filter(
            embedding__model=spec.repository,
            embedding__model_revision=spec.tag,
        )
        .annotate(
            similarity=1.0 - CosineDistance("embedding__vector", vector),
        )
        .order_by("-similarity", "id")[:RESULT_LIMIT]
    )
