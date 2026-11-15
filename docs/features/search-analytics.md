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

## Search-to-click attribution (KAN-106)

A successfully recorded web search renders its current action UUID on every book
link (`data-search-id`), including desktop/mobile title and detail links. The
hidden form UUID still belongs to the next search. A normal catalog visit or a
failed search publication does not render a current-search reference.

The tracking client sends optional `search_id` only for `book_click`. It is the
current action UUID, also returned in `X-Search-Event-ID`, not the next form UUID.
`ClientEventSerializer` requires a valid UUID, refuses it for other event types,
and continues to reject unknown fields. Existing clicks omit it as before.

The server derives the owner-bound event UUID using the same namespace as search
publication and saves that UUID as `book_click.properties.search_id`. Resolve the
search with `UserEvent(id=click.properties["search_id"], user=click.user,
event_type="search")`. Client input cannot point to another reader's event. There
is no existence check because the asynchronous worker may persist the click before
the search; the reference resolves once the search is saved. Retries keep the same
client event UUID and remain idempotent. This is correlation, not a foreign key;
old events and unattributed clicks are unchanged and no query text is duplicated.
