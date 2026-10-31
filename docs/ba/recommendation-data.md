# Recommendation data contract v1 (KAN-50)

KAN-31 consumes this internal Python interface from `book.recommendation_data`.
The interface separates data preparation from vector encoding and ranking. It is
not a public history API and never offers a client-selected target account.

## Interface and examples

```python
from book.recommendation_data import (
    read_history, available_candidates, fallback_candidates,
)

# Always use the authenticated session account, not an ID from query parameters.
history = read_history(request.user)
candidates = available_candidates(request.user)
fallback = list(fallback_candidates(request.user)[:10])
```

`read_history(user, *, now=None)` returns an immutable `RecommendationHistory`:

| Field | Type | Meaning |
| --- | --- | --- |
| `books` | tuple of `BookSignal` | Strongest usable action per existing book, ordered by book ID |
| `books[].book_id` | int | Catalog identifier, never another account's identifier |
| `books[].event_type` | str | Recorded supported action, not an inferred rating |
| `books[].weight` | int | Existing KAN-31 baseline intent weight |
| `searches` | tuple of str | Latest distinct usable search texts, newest first |

For example, a reader who viewed book 17 and searched for physics has the following
illustrative snapshot (IDs depend on the catalog):

```python
RecommendationHistory(
    books=(BookSignal(book_id=17, event_type="book_view", weight=1),),
    searches=("physics",),
)
```

A new reader, or a reader with only unusable events, gets:

```python
RecommendationHistory(books=(), searches=())
```

KAN-31 now calls these helpers directly. It turns valid configured embeddings and
search vectors into a profile, or falls back when no usable profile can be built.
Book history does not need an embedding to enter the data snapshot; missing or
incompatible vectors are handled by the consumer without inventing a signal.

## Signal policy and missing data

This version carries forward KAN-31's baseline rules. It does not introduce a new
rating scale or redefine likes as ratings.

| Source | Storage / owner | v1 processing |
| --- | --- | --- |
| Book viewed | KAN-30 `UserEvent`, server | weight 1 |
| Book clicked | KAN-30 `UserEvent`, server or validated client | weight 2 |
| Borrow intent | KAN-30 `UserEvent`, server or validated client | weight 3 |
| Book borrowed / returned | KAN-30 `UserEvent`, server | weight 4; loan owner must not contradict the session account |
| Text searched | KAN-30 server `search` event, `properties.query` | up to 3 distinct texts, at most 200 characters each; ranking uses weight 1 |
| Favorites / likes | KAN-51 models, not present in this base | unavailable, not fabricated from clicks; future adapter reads current owned state and removes withdrawn choices |
| Explicit rating | KAN-59 model/scale, not present in this base | unavailable, not zero or dislike; KAN-61 connects changed/deleted ratings separately after CRUD/UI exist |

Selection uses at most the 200 latest eligible events from the past 90 days,
including the exact lower boundary and excluding future events. Repeats on one
book keep the strongest action; equal weights keep the latest timestamp/UUID.
Book IDs without a current catalog entry are ignored. Only approved client event
kinds (click and borrow intent) are accepted; client-origin loans/views/searches
cannot become stronger trusted history.

Search text is trimmed, truncated and deduplicated case-insensitively. Empty text,
author-only searches, non-string text and malformed payloads are ignored. Unsupported
events such as login, logout and loan reassignment establish no preference.
A librarian processing another reader's loan must not acquire that reader's interest:
if a loan event's `properties.reader_id` contradicts the event owner, it is dropped,
not reassigned by looking through another account's events.

There is no extra profile table, duplicate event storage, cross-account popularity
query, private text cache or model inference in this module. KAN-30 remains the
source of event persistence and queue behavior. The 90-day rule is a read window,
not a purge of historical analytics or a new retention job. A queue failure or
missing source can leave history incomplete; the consumer still has book signals
or the safe fallback. Do not log the raw private search snapshot.

V1 exposes only `books` and `searches`. Optional future feedback adapters must add
distinct typed fields and document scale, update/delete and ownership semantics;
they must not smuggle ratings through arbitrary event JSON or treat absence as a
negative value. No feedback models or API are created by KAN-50.

## Ownership and minimization

All three helpers require an active, authenticated, persisted account and raise
`PermissionDenied` otherwise, before querying history. A librarian has the same
own-history scope as a reader. The snapshot carries no user IDs, event UUIDs,
raw properties, `issued_by`, other readers' IDs or timestamps. Search text belongs
only to the requesting account. The recommendation API continues to reject account
selectors; this internal data snapshot is not exposed as a new API. Trusted server callers must pass `request.user`.

## One availability rule

`available_candidates(user, *, now=None)` returns a lazy book queryset, with availability
annotations and prefetched authors. It delegates stock arithmetic to
`Book.objects.with_availability(now)`:

```text
available = max(0, copies - unreturned loans - active unexpired reservations)
candidate requires available > 0
```

Reservations hold a copy only while `state == active` and `expires_at > now`.
Exactly at expiry they release it, even if Celery beat has not recorded expiry yet.
Overdue but unreturned loans still occupy a copy. The caller's own current loans
and holds are omitted even when another copy remains. Returns, cancellations,
expiry and stock changes affect the next query without a result cache. Availability
is a request-time snapshot, not a promise or a reservation of a copy.

`fallback_candidates(user, *, now=None, exclude_book_ids=())` applies the same
eligibility rule, then orders by case-insensitive title and ID. Slice it to Top-N;
KAN-31 retains its default 10 / maximum 20 response limit. The exclusion list allows
padding without duplicates or reintroducing profile books. No history, no ratings,
missing embeddings and an empty catalog all work without an error. Missing history
is not replaced with another reader's interests.

## Control scenarios

The following run in `book.test_recommendation_data` through the existing full
Docker Build Django suite against PostgreSQL. The existing KAN-31 ranking tests
also run against this adapter.

| Scenario | Expected result |
| --- | --- |
| New reader / absent ratings or embeddings | empty snapshot; stable available fallback; API 200 |
| Own views, search, repeats and stronger action | minimized own fields; strongest per-book action and bounded search texts |
| Other reader's events or a staff return for another reader | no foreign signals in the snapshot |
| Anonymous, inactive or unpersisted account | refused before data queries |
| Empty/malformed searches, client-forged server actions, old/future events | ignored; no guessed preference |
| One copy held by an active loan or reservation | not a candidate |
| Loan plus reservation exhaust the stock | not a candidate; counts are combined |
| Return, cancellation or stock edit | next candidate query reflects the new state |
| Exact reservation expiry, worker not running | copy becomes eligible immediately |
| Own current loan/hold with spare stock | omitted for that reader |
| Equal title sorting / fallback padding | stable ID tiebreak and exclusions; no duplicates |
