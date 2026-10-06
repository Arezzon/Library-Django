"""Local multilingual E5 encoding, shared by book saves and the backfill command."""
import hashlib
import math
from functools import lru_cache

from django.conf import settings

MODEL_NAME = 'intfloat/multilingual-e5-small'
MODEL_REVISION = '614241f622f53c4eeff9890bdc4f31cfecc418b3'
DIMENSIONS = 384


class EmbeddingGenerationError(ValueError):
    """Book text and its vector could not be saved together."""


def document_text(name, description):
    """E5 requires a passage prefix, including for non-English documents."""
    return 'passage: ' + '\n'.join(part for part in (name.strip(), description.strip()) if part)


def input_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def normalized_vector(values):
    vector = [float(value) for value in values]
    if len(vector) != DIMENSIONS or not all(math.isfinite(value) for value in vector):
        raise ValueError(f'Expected {DIMENSIONS} finite embedding values.')
    norm = math.sqrt(sum(value * value for value in vector))
    if not math.isfinite(norm) or norm == 0:
        raise ValueError('Embedding must have a finite, nonzero norm.')
    return [value / norm for value in vector]


@lru_cache(maxsize=2)
def load_embedding_model(offline=False):
    # Lazy initialization and per-process caching avoid loading on every save.
    from fastembed import TextEmbedding
    from fastembed.common.model_description import ModelSource, PoolingType
    from huggingface_hub import snapshot_download

    snapshot = snapshot_download(
        repo_id=MODEL_NAME, revision=MODEL_REVISION,
        cache_dir=str(settings.BOOK_EMBEDDING_CACHE_DIR), local_files_only=offline,
        allow_patterns=[
            'config.json', 'tokenizer.json', 'tokenizer_config.json',
            'special_tokens_map.json', 'onnx/model.onnx',
        ],
    )
    if MODEL_NAME not in {model['model'] for model in TextEmbedding.list_supported_models()}:
        TextEmbedding.add_custom_model(
            model=MODEL_NAME, pooling=PoolingType.MEAN, normalization=True,
            sources=ModelSource(hf=MODEL_NAME), dim=DIMENSIONS,
            model_file='onnx/model.onnx',
        )
    return TextEmbedding(
        model_name=MODEL_NAME, specific_model_path=snapshot,
        threads=2, providers=['CPUExecutionProvider'],
    )


def regenerate_book_embedding(book, database):
    """Called within the book save transaction, with its row locked.

    Failure propagates so the caller rolls back both the text and vector.
    A book without a description is encoded from its title.
    """
    from .models import BookEmbedding

    text = document_text(book.name, book.description)
    try:
        vectors = list(load_embedding_model(offline=False).embed([text], batch_size=1))
        if len(vectors) != 1:
            raise ValueError('Expected one embedding.')
        vector = normalized_vector(vectors[0])
    except Exception as error:
        raise EmbeddingGenerationError(
            'Could not generate the book embedding. The book was not saved; please retry.'
        ) from error
    BookEmbedding.objects.using(database).update_or_create(
        book_id=book.pk, defaults={
            'vector': vector, 'input_hash': input_hash(text),
            'model': MODEL_NAME, 'model_revision': MODEL_REVISION,
        },
    )
