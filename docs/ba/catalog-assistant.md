# Catalog assistant (KAN-52)

P1 uses deterministic catalog queries and templates. It needs neither P2 semantic
search (KAN-28), embedding inference nor an external LLM. This module sits beside
catalog reads; it has no calls into reservation/issuance services and stores no
conversation, private reader history or assistant requests. The service/API boundary
follows the current Django architecture; the reader UI can consume the same
structured response without access to business write services.

## Architecture (KAN-26)

The installed `ai` Django app owns request interpretation, response templates and
its API route. It calls the read-only `book.catalog_data.lookup_catalog` gateway
for linked catalog facts. Core catalog code imports no `ai` modules; AI code calls
no booking/issuance services. Existing embedding, search and recommendation
implementations are unchanged; moving those older modules behind AI facades is
separate from this assistant ticket. No AI models or migrations are introduced.

CI and coverage include the new `ai` app alongside every existing suite.

## Reader interface contract

`GET /api/v1/assistant/?q=<text>&intent=auto` requires an active signed-in account,
including for librarians. Responses are private and not cached. POST/PATCH/DELETE
are refused. Ownership selectors and repeated/unknown parameters return 400.

`ai.services.catalog_assistant(user, query, intent)` is the reusable service.
The API is ready for a reader interface; this ticket does not add a chat UI.

Supported intents:

| Intent | Input | Behavior |
| --- | --- | --- |
| `title` | literal title fragment | case-insensitive substring on Book.name |
| `author` | literal name/surname/patronymic tokens | every token matches an author name field; returns author records and linked books |
| `availability` | literal title fragment | same title lookup with current copy counts |
| `auto` (default) | bare title or a recognized prefix | maps the prefix; otherwise treats the text as a literal title |

Prefixes: `книга:`, `назва:`, `book:`, `title:`, `автор:`, `author:`, `наявність:`,
`доступність:`, `availability:`. Prefix matching ignores case. With an explicit
intent, q is literal, so a title containing a colon remains searchable.
Empty/one-character text, an empty prefix value or an unsupported prefix returns
`clarification_required` without querying the catalog. Unknown intent or text over
256 characters returns 400. This is a documented command grammar, not arbitrary
natural-language understanding, fuzzy matching or semantic inference.

## Grounding and failures

A response includes `status`, resolved `intent`, plain-text Ukrainian `answer`,
`books`, `authors`, `checked_at`, `truncated` and `availability_notice`.

Book records contain their exact title, ID, web detail URL, linked author records,
`available_count` and `total_count`. Authors include exact catalog names, API record
URLs and a filtered book-list URL. Relative URLs are generated from Django routes,
never from user text. Clients must render answer/title/name as text, not trusted HTML.
An absent author is stated explicitly. Existing authors without books are still
confirmed with links; the assistant never fills missing relationships with guesses.

Multiple matching books (or authors for author intent) return
`clarification_required` with confirmed candidates and an invitation to refine the
full name/title or open a linked record. Results are ordered by case-insensitive
title (authors by surname/name), then ID. Each top-level list is capped at 10;
`truncated=true` makes the bound explicit. Query count is fixed (2 for title/copy
queries, 3 for author lookup), rather than one stock/author query per book.

No matches return `not_found`, empty records and a statement that the catalog has
no confirmed matches. Catalog database failures return HTTP 503,
`source_unavailable`, empty records, no checked_at, a static explanation and
`Retry-After: 5`. All lazy queries/materialization are inside the failure boundary:
partial records and exception/credential text are never returned. Authentication
uses the existing session/database infrastructure; an infrastructure-wide outage
can prevent authentication before the assistant is reached.

## Availability is informational

Each lookup uses `Book.objects.with_availability(now)`: total copies minus active
unreturned loans and active reservations expiring strictly after now, clamped at
zero. Readers' names, loan records and hold owners are never included. Returned
loans, expired/cancelled holds and stock changes affect the next request without
cache invalidation or beat. Book authors cannot multiply the counted loans/holds.

`checked_at` is the lookup instant, not a reservation or transaction-wide promise.
A concurrent issue/hold can change stock immediately after the answer. The response
always includes a notice that booking rechecks stock. The assistant neither locks
nor holds copies; existing reservation/issuance services remain responsible for
atomic eligibility/stock checks. No migration, new queue or model download is needed.

## Verification

`ai.test_assistant` covers title/author links, missing records/authors, Ukrainian
case-insensitive input, refinement, limits/stability, live loan/hold/expiry/return
changes, source/prefetch failures, active-account access, parameter validation,
read-only SQL, absent embeddings and no inference. The existing access matrix
includes the endpoint. Docker Build runs these with all established app suites;
HTTP smoke checks verify seeded catalog answers and clarification/missing states.
