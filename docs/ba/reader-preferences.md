# Private reader preferences (KAN-51)

Likes and favorites are independent boolean states, not numerical ratings. Each
reader/book pair has at most one row in each table (`BookLike`, `FavoriteBook`).
Removing a state deletes its row. Book/account deletion cascades; these rows do not
protect a book from deletion. No other reader's preferences or counts are exposed.

## Interface

All routes require an active signed-in account. The server derives ownership from
the session, never a caller-supplied reader identifier. Session writes require CSRF.

- `GET /api/v1/books/<id>/preferences/`: `{book_id, liked, favorite}`.
- `PATCH /api/v1/books/<id>/preferences/`: JSON `{"liked": true}` and/or
  `{"favorite": true}`. Only strict booleans are accepted. Omitted flags are
  unchanged; explicit desired states make repeated requests safe.
- `DELETE /api/v1/books/<id>/preferences/`: reset both states; harmless to repeat.
- `GET /api/v1/me/book-preferences/?kind=all|likes|favorites`: own saved books with
  availability and both flags, in stable case-insensitive title/id order. Unavailable
  books stay saved; availability filtering belongs to the recommendation service.
- `/book/preferences/` lists own saved books. Book details and the list have CSRF
  protected POST actions to add/remove states. GET never changes preference state.

Unknown owner selectors and rating fields are rejected. Personal success responses
have `Cache-Control: private, no-store`. Librarians also access only their own state.

`book.preferences.read_book_preferences(user)` returns an immutable tuple of
`BookPreferenceSignal(book_id, liked, favorite)` for the authenticated account.
Ranking reads at most the latest 200 rows per source; the saved-books list is not
truncated. No user IDs, timestamps or other readers' data enter this interface.
Two fixed preference queries avoid a query per book.

## Recommendation rule

A like OR favorite gives its book weight 5 in the existing content-based profile.
Both flags together still give weight 5, avoiding double counting. Explicit state
outweighs behavioral book events (weights 1–4). Explanations say the reader liked or
saved the actual source book; they never claim it was read. Removing a preference
removes that explicit signal on the next request; independent behavioral history
can still contribute. Existing availability rules, stable Top-N and alphabetical
cold-start fallback remain in force. Missing preferences are a valid empty tuple.
Numerical ratings are reserved for KAN-59–61.

## Search events and failure handling

The catalog and semantic-search API record one `SEARCH` event for each successful
search action. Failed validation/inference and anonymous requests create no event.
The web form includes `search_id`, a UUID refreshed for each new submission.
Refreshing its submitted URL reuses the same identity. API callers should generate
a UUID per action and reuse it for network retries:

`GET /api/v1/books/search/?q=detective&search_id=<uuid>`

The response echoes `X-Search-Event-ID`. Without a supplied identity each request
is a new action. Identical text with a new identity is intentionally a new search.
A user-scoped, search-specific UUID is the durable event primary key; worker
redelivery/retries use `get_or_create` and cannot count the same action twice.
Only trimmed query text (max 200 characters), optional author ID and the existing
allowlisted path/metadata are retained. Request query strings, credentials and
arbitrary fields are not stored or logged. Existing event retention applies.

Search delivery uses the existing persistent Redis/Celery queue. A publish failure
returns 503, `Retry-After: 5` and the same identity; callers must retry with that
`search_id`. The catalog still shows results and a retry message, retaining the
identity in its form. Accepted events are asynchronous and become recommendation
signals after worker persistence. There is no claim that an HTTP 200 means the
worker already committed. Ordinary book-view tracking retains its existing
best-effort behavior. Preference writes commit directly in PostgreSQL independently
of Redis, with account/book locks and database uniqueness constraints.

## Control scenarios

`book.test_preferences` covers independent states, idempotency, session persistence,
queue independence, uniqueness/cascade, owned lists, strict validation, inactive
accounts, CSRF, web actions and ranking/removal/fallback. The two readers have
separate states and only one receives the matching recommendation.
`events.test_search_persistence` covers web/API single publication, redelivery,
owner-bound identities, separate new actions, minimized properties, queue failure
and retry, invalid/failed/anonymous searches and private recommendation input.
CI runs these with all existing app suites against PostgreSQL in the Docker image.
