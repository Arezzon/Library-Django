# Explicit book ratings (KAN-59–61)

The agreed scale is integer **1–5**, separate from likes and favorites. A reader
has one current `BookRating` per book, can replace its value or delete it. Identical
PUT retries preserve the row and timestamp; a real change updates `updated_at`.
There is no rating history, queue dependency, inferred vote or automatic like.

`GET/PUT/PATCH/DELETE /api/v1/books/<id>/rating/` requires an active signed-in
account. The server takes ownership from the session, including for librarians.
GET returns `{book_id, value}` with null for no current vote. PUT creates or
replaces; PATCH has the same one-field contract; DELETE is idempotent. JSON writes
accept only `{"value": <integer 1–5>}`. Floats, booleans, strings, null, unknown
fields and query selectors are refused. Missing books return 404. Session writes
require CSRF. Responses, including errors, use private/no-store cache control.
No endpoint lists other readers' ratings or accepts an owner ID.

The unique reader/book key and range check are PostgreSQL constraints, not just
serializer validation. The service locks account then book, matching existing
preference/loan ordering, so concurrent retries/deletes serialize. Book/account
deletion cascades; rating rows do not introduce catalog deletion protection.
Migration 0007 adds a new table without modifying existing catalog/embedding data.

KAN-60 adds the reader UI and aggregate summary; KAN-61 consumes owned current
rating signals in recommendations. Individual votes remain private; aggregate
display contains only mean/count, never identities or vote records.

Verification: `book.test_ratings` covers CRUD, retries/timestamps, direct model and
DB constraints, strict validation, active accounts/CSRF, ownership, queue independence,
concurrent writes and an actual 0006→0007 migration with an existing catalog row.
The full Docker regression suites remain enabled; `scripts/smoke_ratings.py` checks
real authenticated HTTP requests and a new login session in the disposable stack.

## Reader UI and aggregate summary (KAN-60)

Book details show only the current account's score in a labeled native select,
with Save/Remove actions, empty states and accessible error feedback. CSRF-protected
POST `/book/<id>/rating/` derives the owner from the session; duplicate/unknown
fields, owner selectors and unsupported actions are refused before writes. Both
successful changes and repeated removals redirect to the book rating section.

`GET /api/v1/books/<id>/rating-summary/` returns only `{book_id, average, count}`
for signed-in catalog readers. Mean is rounded to two decimals; an empty aggregate
is null/count 0, never an inferred zero score. Neither rater identifiers nor
individual votes are exposed. This is aggregate display, not a claim of statistical
anonymity for small samples. The owned value and aggregate are read in one SQL
snapshot using a current-user scalar subquery; there is no cross-reader vote list.

The browser smoke check exercises keyboard save/update/remove, a fresh session,
aggregate-only response keys, axe on the rating section, an invalid submitted
value, and unchanged loan/hold counts. Browser tooling is development-only and uses
the same pinned dependencies as the assistant check. Unit/integration tests are
`book.test_rating_interface`; CI retains every established suite.

## Recommendation signals and control results (KAN-61)

`book.ratings.read_rating_signals(user)` returns immutable `(book_id, value)`
records for the active account only, at most the latest 200 by actual change time
and book ID. Repeated identical writes do not move a vote into the recent window.
Ratings are current state, not inferred events or duplicated likes.

The signed centroid uses the following explicit rule:

| Value | Weight | Meaning |
| --- | --- | --- |
| 1 | -12 | strongest reduction for similar content |
| 2 | -6 | reduction for similar content |
| 3 | 0 | no directional rating signal; independent history/likes remain |
| 4 | +6 | positive direction, stronger than a like/favorite (5) |
| 5 | +12 | strongest positive direction |

A non-neutral rating overrides the weaker behavioral/like weight for the same
book. It never edits the underlying like/favorite. Changing to 3 or deleting the
rating withdraws the explicit direction; independent signals can still contribute.
The profile is normalized, so changing 4→5 need not change ordering when there is
only one source; it changes its strength against competing signals.

All currently rated books, including neutral or older-than-window votes and
missing-vector records, are excluded from candidates and fallback via an owned
subquery. Other readers' ratings and the public aggregate are never ranking input.
The existing current availability/own-loan/own-hold rules remain authoritative.
Personalized recommendation responses use private/no-store cache control.
Deletion/stock/return/hold expiry is visible on the next request without a cache.
If signed directions cancel or vectors are absent, the stable available fallback
works. Explanations quote only the caller's contributing source; they never call
a low score a high one. If no individual positive contribution explains a result,
the existing generic profile explanation remains truthful.

Controlled vector fixtures in `book.test_rating_recommendations` establish these
observable outcomes (not a measured human relevance/accuracy percentage):

| Control | Expected first result |
| --- | --- |
| Science seed rated 4/5; no competing signals | A Science candidate |
| Same seed rated 1/2 | Z Art candidate |
| Low rating deleted; no other signals | A Science candidate, alphabetical fallback |
| Same seed rated 3 | neutral direction; fallback or independent positive signals |
| Two art preferences (total 10), science rated 4 (6) | Z Art candidate |
| Same competing case, science changed to 5 (12) | A Science candidate |

The 11 integration tests additionally cover ownership, API changes/deletion,
no inference/new embeddings, availability updates, all-rated empty results,
missing vectors, capped signal reads with complete rated-book exclusion, and
faithful reasons. The recommendation path adds one fixed query, not one query per
candidate. CI's `smoke_ratings.py --recommendations` checks live API exclusion of
an actually recommended book after voting and restored eligibility after deletion.
