# Semantic book search

`GET /api/v1/books/search/?q=...` returns up to 20 books ordered by descending
cosine similarity, with book ID breaking ties. The response uses the existing
book fields, including availability and authors, plus a `similarity` score
(`1 - cosine distance`, higher is closer). The existing `/api/v1/book/`
CRUD routes remain available. The catalog search uses the same retrieval and
preserves the author filter; an empty catalog query lists all books.

Queries are trimmed and must contain 1–512 characters (HTTP 400 otherwise).
Encoder failure returns HTTP 503; the catalog displays an error. Missing vectors
and vectors from another model are excluded. Backfill them with
`python manage.py generate_book_embeddings` from `library/`.

## Model

Search uses `BAAI/bge-m3` dense embeddings from the int8 ONNX export in
`Xenova/bge-m3` (`onnx/model_int8.onnx`, pinned revision). It serves English and
Ukrainian, including Ukrainian queries against English descriptions. Pooling takes
the first (CLS) token and normalizes it; queries and documents need no prefixes;
input is truncated to 512 tokens, and vectors have 1024 dimensions. The weights
are quantized per channel to signed int8, which runs unchanged on amd64 and arm64.
Inference runs in process on ONNX Runtime with `BOOK_EMBEDDING_THREADS` threads
(default 2); each Gunicorn worker holds one model copy (about 0.6 GB), loaded
before it takes requests. PostgreSQL computes cosine distances without loading
catalog vectors into the web process. Retrieval is an exact scan, suitable for a
catalog of up to about 1,000 books; it returns the nearest books without a
relevance cutoff.

## One model setting

The model is defined in exactly one place, `library/book/embedding_config.py`: its
repository, pinned revision, model and tokenizer files, vector size, pooling,
prefixes and token limit. Each value can be overridden at build time with a
`BOOK_EMBEDDING_*` variable (`docker build --build-arg BOOK_EMBEDDING_MODEL=...`);
empty means the default. The image build fetches the model with
`scripts/fetch_embedding_model.py`, which writes a `manifest.json`, and running
containers never download one. Changing the model means rebuilding the images.
If a runtime override differs from the image's model, startup stops with the
`book.E001` check instead of mixing vectors.

## Stored vectors

Vectors live in an untyped pgvector column, so their size follows the model.
Each vector records the model repository and a tag derived from the whole
setting; search compares only vectors with the current tag. On startup, after
migrations, the web container re-encodes every book whose vector is missing,
stale or from another model, before serving traffic. Books that already match
are skipped, so a normal start runs no inference. A failure stops startup; the
next start resumes with the remaining books.

## Quality and budget checks

An evaluation set of 18 queries (9 English, 9 Ukrainian against the English
seed catalog) lives in `library/book/search_evaluation.json`. With
`RUN_BOOK_EMBEDDING_MODEL_TESTS=1`, CI runs it with the real model on amd64 and
arm64, and every query must rank its expected book first.

The site runs on a Raspberry Pi 5 within a 4 GB memory budget for the whole
stack. `scripts/smoke_stack_budget.py` measures peak stack memory, search and
book-save latency, and checks that every vector carries the current model tag.
CI enforces the 4 GiB memory limit on both architectures; the operator runs it
on the Pi with the latency targets (95% of searches under 500 ms, saves under
2 s), as described in `docs/deployment/raspberry-pi-portainer.md`.
