# Contract: Embedding model setting

**Covers**: FR-026, FR-030, FR-031, FR-033, FR-034, and the edge case where the runtime setting
differs from the image's model.
**Single source**: `library/book/embedding_config.py`. The model is named nowhere else; the
default values below are copied from that file and are shown here for reference only.

## Environment variables

These are read at **build time** by the image build and at **runtime** by the app. An empty
value means "use the default".

| Variable | Default | Part of the model tag? |
|---|---|---|
| `BOOK_EMBEDDING_MODEL` | `Xenova/bge-m3` | yes |
| `BOOK_EMBEDDING_MODEL_REVISION` | `4de13258303883538bd53b696b452bf8099f0858` | yes |
| `BOOK_EMBEDDING_MODEL_FILE` | `onnx/model_int8.onnx` | yes |
| `BOOK_EMBEDDING_TOKENIZER_FILE` | `sentencepiece.bpe.model` | yes |
| `BOOK_EMBEDDING_DIMENSIONS` | `1024` | yes |
| `BOOK_EMBEDDING_POOLING` | `cls` (`cls` or `mean`) | yes |
| `BOOK_EMBEDDING_QUERY_PREFIX` | empty | yes |
| `BOOK_EMBEDDING_DOCUMENT_PREFIX` | empty | yes |
| `BOOK_EMBEDDING_MAX_TOKENS` | `512` | yes |
| `BOOK_EMBEDDING_THREADS` | `2` | no (runtime tuning) |
| `BOOK_EMBEDDING_CACHE_DIR` | `/app/.cache/book-embeddings` in the image | no |

Invalid values make spec resolution raise an error that names the variable. Invalid values
include a non-hex revision, an unknown pooling, a non-positive dimension, and a model file
named for one instruction set.

## Python interface (`book.embedding_config`)

This module imports only the standard library, so it can be imported without Django.

- `resolve() -> EmbeddingSpec` returns a frozen dataclass with the fields above, except the
  tuning fields, plus a `.tag` property: a 40-hex SHA-1 of `json.dumps(fields, sort_keys=True)`.
- `read_manifest(cache_dir) -> dict | None` returns the parsed `manifest.json`, or `None` if it
  doesn't exist.

Consumers, all of which import the spec rather than repeating any value:
- `book.embeddings`: encoding, pooling, prefixes and length validation.
- `book.search`: the query prefix and the tag filter.
- `book.models`: the save-time refresh check.
- The `generate_book_embeddings` command.
- `scripts/fetch_embedding_model.py`.
- The tests.

## Script: `scripts/fetch_embedding_model.py`

```text
python scripts/fetch_embedding_model.py [--cache-dir DIR] [--print]
```

- It resolves the spec, then calls `snapshot_download` with only `model_file` and
  `tokenizer_file` at the pinned revision.
- It writes `manifest.json` into the cache directory, holding the spec, tag and snapshot path,
  and exits 0.
- `--print` writes the resolved spec and tag as JSON to stdout without downloading anything.
- **Exit codes**:
  - 0: success;
  - 2: invalid setting;
  - 3: download failed, which also fails the image build so no image ships without its model.
- **Image build**: the Dockerfile copies only `library/book/embedding_config.py` and this script,
  declares every `BOOK_EMBEDDING_*` name above as an `ARG` without a value, mirrors it into
  `ENV`, and runs the script. The Dockerfile contains no model name.

## Startup checks (system checks in the `book` app)

| ID | Level | When | Message (shape) |
|---|---|---|---|
| `book.E001` | Error | The manifest exists and its tag differs from `resolve().tag` | "Embedding model setting `<repo>@<rev>` does not match the model in this image `<repo>@<rev>`. Rebuild the image with the new setting or remove the override." |
| `book.W001` | Warning | No manifest exists, as in a local `venv` before fetching | "No embedding model found in `<cache dir>`; run `python scripts/fetch_embedding_model.py`." |

`migrate` runs these checks, and the entrypoint runs `migrate` before anything else, so a
mismatch stops the web container before it serves traffic.

## Startup re-encoding

The entrypoint, after `migrate` and optional seeding, runs:

```text
python manage.py generate_book_embeddings --offline --threads <min(cpu_count, 4)>
```

- **Re-encodes** every book whose `model != spec.repository`, whose
  `model_revision != spec.tag`, whose text hash changed, or that has no vector.
- **Skips** everything else, so a normal start adds about one indexed query and no inference.
- **Commits** each book in its own transaction. A failure exits non-zero, stopping startup with
  the container unhealthy; progress so far is kept.
