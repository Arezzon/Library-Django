"""The embedding model setting: the only place the project names its model.

Every value can be overridden by a ``BOOK_EMBEDDING_*`` environment variable; an
empty value means the default below. The image build reads the same variables
(``scripts/fetch_embedding_model.py``), so build time and runtime agree.

Standard library only: the fetch script loads this file without Django.
"""

import dataclasses
import hashlib
import json
import os
import re
from pathlib import Path

DEFAULTS = {
    "repository": "Xenova/bge-m3",
    "revision": "4de13258303883538bd53b696b452bf8099f0858",
    "model_file": "onnx/model_int8.onnx",
    "tokenizer_file": "sentencepiece.bpe.model",
    "dimensions": 1024,
    "pooling": "cls",
    "query_prefix": "",
    "document_prefix": "",
    "max_tokens": 512,
}

VARIABLES = {
    "repository": "BOOK_EMBEDDING_MODEL",
    "revision": "BOOK_EMBEDDING_MODEL_REVISION",
    "model_file": "BOOK_EMBEDDING_MODEL_FILE",
    "tokenizer_file": "BOOK_EMBEDDING_TOKENIZER_FILE",
    "dimensions": "BOOK_EMBEDDING_DIMENSIONS",
    "pooling": "BOOK_EMBEDDING_POOLING",
    "query_prefix": "BOOK_EMBEDDING_QUERY_PREFIX",
    "document_prefix": "BOOK_EMBEDDING_DOCUMENT_PREFIX",
    "max_tokens": "BOOK_EMBEDDING_MAX_TOKENS",
}

THREADS_VARIABLE = "BOOK_EMBEDDING_THREADS"
DEFAULT_THREADS = 2
POOLING = ("cls", "mean")
# Files quantized for one instruction set are not portable across amd64 and arm64.
INSTRUCTION_SETS = re.compile(r"avx2|avx512|vnni", re.IGNORECASE)


@dataclasses.dataclass(frozen=True)
class EmbeddingSpec:
    repository: str
    revision: str
    model_file: str
    tokenizer_file: str
    dimensions: int
    pooling: str
    query_prefix: str
    document_prefix: str
    max_tokens: int

    @property
    def tag(self):
        """40-hex identity of the whole spec, stored with every vector."""
        canonical = json.dumps(dataclasses.asdict(self), sort_keys=True)
        return hashlib.sha1(canonical.encode()).hexdigest()


def _integer(field, raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError(
            f"{VARIABLES[field]} must be an integer, got {raw!r}."
        ) from None


def resolve():
    """Read the spec from the environment, falling back to the defaults."""
    values = {}
    for field, variable in VARIABLES.items():
        raw = os.getenv(variable, "")
        values[field] = raw if raw != "" else DEFAULTS[field]
    values["dimensions"] = _integer("dimensions", values["dimensions"])
    values["max_tokens"] = _integer("max_tokens", values["max_tokens"])

    def invalid(field, rule):
        raise ValueError(f"{VARIABLES[field]} {rule}, got {values[field]!r}.")

    if not re.fullmatch(r"[\w.-]+/[\w.-]+", values["repository"]):
        invalid("repository", "must be a repository id of the form owner/name")
    if not re.fullmatch(r"[0-9a-f]{40}", values["revision"]):
        invalid("revision", "must be a pinned 40-character hex commit")
    if INSTRUCTION_SETS.search(values["model_file"]):
        invalid("model_file", "must not name a CPU instruction set")
    if values["pooling"] not in POOLING:
        invalid("pooling", "must be one of " + ", ".join(POOLING))
    if values["dimensions"] <= 0:
        invalid("dimensions", "must be greater than 0")
    if not 8 <= values["max_tokens"] <= 8192:
        invalid("max_tokens", "must be from 8 to 8192")
    return EmbeddingSpec(**values)


def threads():
    """ONNX Runtime threads per model copy; runtime tuning, not part of the tag."""
    raw = os.getenv(THREADS_VARIABLE, "")
    if raw == "":
        return DEFAULT_THREADS
    try:
        return max(1, int(raw))
    except ValueError:
        raise ValueError(
            f"{THREADS_VARIABLE} must be an integer, got {raw!r}."
        ) from None


def read_manifest(cache_dir):
    """The image's manifest.json written by the fetch script, or None."""
    path = Path(cache_dir) / "manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
