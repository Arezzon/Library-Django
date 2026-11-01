# Explicit book ratings (KAN-59)

The initial scale is integer **1–5**, separate from likes and favorites. A reader
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

The following stages add the reader UI and aggregate summary (KAN-60), then owned
rating signals in recommendations (KAN-61). Individual votes remain private;
aggregate display will contain only mean/count, never identities or vote records.

Verification: `book.test_ratings` covers CRUD, retries/timestamps, direct model and
DB constraints, strict validation, active accounts/CSRF, ownership, queue independence,
concurrent writes and an actual 0006→0007 migration with an existing catalog row.
The full Docker regression suites remain enabled; `scripts/smoke_ratings.py` checks
real authenticated HTTP requests and a new login session in the disposable stack.
