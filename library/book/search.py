"""Bounded semantic retrieval using the existing int8 E5 encoder and pgvector."""
from pgvector.django import CosineDistance

from . import embeddings
from .embeddings import (normalized_vector,
                         MODEL_NAME, MODEL_REVISION, EmbeddingGenerationError)

MAX_QUERY_LENGTH = 512
RESULT_LIMIT = 20


def validate_query(value):
    query = value.strip()
    if not query or len(query) > MAX_QUERY_LENGTH:
        raise ValueError(f'Provide q with 1–{MAX_QUERY_LENGTH} characters.')
    return query


def search_books(books, query):
    query = validate_query(query)
    try:
        vector = normalized_vector(next(iter(
            embeddings.load_embedding_model(offline=False).embed(['query: ' + query], batch_size=1)
        )))
    except Exception as error:
        raise EmbeddingGenerationError('Search is temporarily unavailable. Please retry.') from error
    # Rank in PostgreSQL; never load the catalog vectors into web-process memory.
    return books.filter(
        embedding__model=MODEL_NAME, embedding__model_revision=MODEL_REVISION,
    ).annotate(
        similarity=1.0 - CosineDistance('embedding__vector', vector),
    ).order_by('-similarity', 'id')[:RESULT_LIMIT]
