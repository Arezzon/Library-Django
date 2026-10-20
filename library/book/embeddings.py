"""Local ONNX encoding for the configured model, shared by book saves, search and
the backfill command. The model itself is defined in embedding_config.py."""

import hashlib
import math
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from . import embedding_config
from .embedding_config import resolve


class EmbeddingGenerationError(ValueError):
    """Book text and its vector could not be saved together."""


def document_text(name, description):
    """The model's document prefix, then the title and description."""
    return resolve().document_prefix + "\n".join(
        part for part in (name.strip(), description.strip()) if part
    )


def input_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalized_vector(values):
    dimensions = resolve().dimensions
    vector = [float(value) for value in values]
    if len(vector) != dimensions or not all(math.isfinite(value) for value in vector):
        raise ValueError(f"Expected {dimensions} finite embedding values.")
    norm = math.sqrt(sum(value * value for value in vector))
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("Embedding must have a finite, nonzero norm.")
    return [value / norm for value in vector]


class OnnxEncoder:
    """One document at a time through ONNX Runtime on CPU, per the model spec."""

    def __init__(self, snapshot, spec, threads):
        import onnxruntime as ort
        from sentencepiece import SentencePieceProcessor

        self.spec = spec
        self.tokenizer = SentencePieceProcessor(
            model_file=str(snapshot / spec.tokenizer_file)
        )
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        # Arenas trade memory for speed; the server stack has a fixed budget.
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            str(snapshot / spec.model_file),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )

    def embed(self, texts, batch_size=1):
        import numpy as np

        for text in texts:
            # XLM-R vocabulary offset: BOS=0, EOS=2, unknown=3.
            pieces = self.tokenizer.encode(text, out_type=int)
            pieces = pieces[: self.spec.max_tokens - 2]
            ids = [0] + [piece + 1 if piece else 3 for piece in pieces] + [2]
            inputs = {
                "input_ids": np.asarray([ids], dtype=np.int64),
                "attention_mask": np.asarray([[1] * len(ids)], dtype=np.int64),
                "token_type_ids": np.asarray([[0] * len(ids)], dtype=np.int64),
            }
            inputs = {
                item.name: inputs[item.name] for item in self.session.get_inputs()
            }
            hidden = self.session.run(None, inputs)[0]
            if self.spec.pooling == "cls":
                pooled = hidden[0, 0]
            else:
                mask = np.asarray([1] * len(ids), dtype=np.float32)[None, :, None]
                pooled = ((hidden * mask).sum(axis=1) / mask.sum(axis=1))[0]
            yield normalized_vector(pooled)


@lru_cache(maxsize=2)
def _load_encoder(threads):
    cache_dir = settings.BOOK_EMBEDDING_CACHE_DIR
    manifest = embedding_config.read_manifest(cache_dir)
    if manifest is None:
        raise RuntimeError(
            f"No embedding model found in {cache_dir}; "
            "run python scripts/fetch_embedding_model.py."
        )
    spec = resolve()
    if manifest["tag"] != spec.tag:
        raise RuntimeError(
            "The embedding model setting does not match the model in "
            f"{cache_dir}; see the book.E001 system check."
        )
    return OnnxEncoder(Path(manifest["snapshot_path"]), spec, threads)


def load_embedding_model(offline=True, threads=None):
    """The process's model copy, loaded from the manifest's local snapshot.

    Images ship with their model, so this never contacts the hub; ``offline``
    is accepted for existing callers and has no effect. Callers share one copy
    per thread count.
    """
    return _load_encoder(threads or embedding_config.threads())


def regenerate_book_embedding(book, database):
    """Called within the book save transaction, with its row locked.

    Failure propagates so the caller rolls back both the text and vector.
    A book without a description is encoded from its title.
    """
    from .models import BookEmbedding

    spec = resolve()
    text = document_text(book.name, book.description)
    try:
        vectors = list(load_embedding_model().embed([text], batch_size=1))
        if len(vectors) != 1:
            raise ValueError("Expected one embedding.")
        vector = normalized_vector(vectors[0])
    except Exception as error:
        raise EmbeddingGenerationError(
            "Could not generate the book embedding. The book was not saved; please retry."
        ) from error
    BookEmbedding.objects.using(database).update_or_create(
        book_id=book.pk,
        defaults={
            "vector": vector,
            "input_hash": input_hash(text),
            "model": spec.repository,
            "model_revision": spec.tag,
        },
    )
