"""Local multilingual E5 encoding, shared by book saves and the backfill command."""
import hashlib
import math
from functools import lru_cache

from django.conf import settings

MODEL_NAME = 'intfloat/multilingual-e5-small'
SOURCE_REVISION = '614241f622f53c4eeff9890bdc4f31cfecc418b3'
# Artifact-specific identity fits the existing 40-character database field.
MODEL_REVISION = hashlib.sha1((SOURCE_REVISION + ':onnx-int8').encode()).hexdigest()
MODEL_FILE = 'onnx/model_qint8_avx512_vnni.onnx'
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


class SmallE5Encoder:
    """Pinned int8 E5, one document at a time, without the FastEmbed model registry."""
    def __init__(self, snapshot):
        import onnxruntime as ort
        from sentencepiece import SentencePieceProcessor

        self.tokenizer = SentencePieceProcessor(model_file=str(snapshot / 'onnx/sentencepiece.bpe.model'))
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        self.session = ort.InferenceSession(
            str(snapshot / MODEL_FILE), sess_options=options,
            providers=['CPUExecutionProvider'],
        )

    def embed(self, texts, batch_size=1):
        import numpy as np

        for text in texts:
            # XLM-R vocabulary offset: BOS=0, EOS=2, unknown=3.
            pieces = self.tokenizer.encode(text, out_type=int)[:510]
            ids = [0] + [piece + 1 if piece else 3 for piece in pieces] + [2]
            inputs = {
                'input_ids': np.asarray([ids], dtype=np.int64),
                'attention_mask': np.asarray([[1] * len(ids)], dtype=np.int64),
                'token_type_ids': np.asarray([[0] * len(ids)], dtype=np.int64),
            }
            inputs = {item.name: inputs[item.name] for item in self.session.get_inputs()}
            hidden = self.session.run(None, inputs)[0]
            mask = np.asarray([1] * len(ids), dtype=np.float32)[None, :, None]
            pooled = (hidden * mask).sum(axis=1) / mask.sum(axis=1)
            yield normalized_vector(pooled[0])


@lru_cache(maxsize=2)
def load_embedding_model(offline=False):
    from pathlib import Path
    from huggingface_hub import snapshot_download

    snapshot = snapshot_download(
        repo_id=MODEL_NAME, revision=SOURCE_REVISION,
        cache_dir=str(settings.BOOK_EMBEDDING_CACHE_DIR), local_files_only=offline,
        allow_patterns=['onnx/sentencepiece.bpe.model', MODEL_FILE],
    )
    return SmallE5Encoder(Path(snapshot))


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
