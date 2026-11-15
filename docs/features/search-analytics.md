# Search analytics

## Search result measurements (KAN-105)

Each successful authenticated web/API search event keeps its existing minimized
`query` (first 200 characters) and `author_id`, plus:

- `best_similarity`: the first displayed book's raw cosine similarity, without
  rounding or a new relevance threshold; `null` for no results or author-only search.
- `result_count`: the number of books actually shown, not the catalog size.
  Semantic search stays limited to 20; author-only browsing keeps its current behavior.

Zero and negative similarities are real measurements, not missing values. Existing
rows are not backfilled. Recommendations continue to read `query`, and the activity
log accepts both older and enriched events. No new query text or personal data is
stored. Search identities, retries, worker deduplication, failure responses and
ranking remain unchanged. Both channels reuse the materialized result list; no
additional embedding computation or result query is needed for these measurements.
