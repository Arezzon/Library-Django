# Semantic book search

`GET /api/v1/books/search/?q=...` returns up to 20 books ordered by descending
cosine similarity, with book ID breaking ties. The response uses the existing
book fields, including availability and authors, plus a `similarity` score
(`1 - cosine distance`, higher is closer). The existing `/api/v1/book/`
CRUD routes remain available. The catalog search uses the same retrieval and
preserves the author filter; an empty catalog query lists all books.

Queries are trimmed and must contain 1–512 characters (HTTP 400 otherwise).
Encoder failure returns HTTP 503; the catalog displays an error. Missing vectors
and vectors from incompatible model revisions are excluded. Backfill them with
`python manage.py generate_book_embeddings` from `library/`.

E5 uses `query: ` for queries and the existing `passage: ` document embeddings.
The pinned int8 model is shared with book creation, uses one CPU inference thread,
and is baked into the Docker image. PostgreSQL computes cosine distances without
loading catalog vectors into the web process. Retrieval is an exact scan, suitable
for the demo catalog; it returns the nearest books without a relevance cutoff.
No additional model, vector service or dependency is introduced for Render Free.

CI runs `book.test_search` through the existing Django book suite, including real
English/Ukrainian queries against the seed catalog. `scripts/smoke_render_free.py`
checks real HTTP inference with the Render web/worker command under a hard 512 MiB
memory limit and 0.1 CPU quota, and reports latency and peak container memory.
