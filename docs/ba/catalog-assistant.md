# Natural-language catalog assistant (KAN-52 / KAN-53)

The reader can ask supported library questions in Ukrainian or English without
commands or selecting an intent. This is a bounded catalog assistant, not an LLM
chatbot. No GPU, external API, new model, model training or migration is required.

## Request interpretation

`ai.language.parse_query` identifies title, author, availability and topic requests.
It removes recognized request wrappers such as “find me” and “знайди”, understands
quoted titles, and keeps the existing explicit intents and `автор:`/`book:` syntax.
A real title containing a colon remains searchable. Unknown names/titles are never
silently replaced with semantic neighbors. Mutation requests ask for clarification;
the assistant cannot reserve, issue, return or delete a book.

| Reader question | Lookup |
| --- | --- |
| знайди твори Шевченка | author, Ukrainian case stem and Latin transliteration |
| Find books by Taras Shevchenko | author, all name tokens |
| Знайди книгу Кобзаря | title, literal first then normalized tokens |
| Is 1984 available? | named title with fresh counts, including zero |
| Show available books by Shevchenko | author collection filtered by current stock |
| Порадь книги про програмування | topic using the existing CPU semantic encoder |

`book.catalog_matching` applies conservative Ukrainian ending removal to query
tokens and equivalent Cyrillic/Latin folding in SQL: case, transliteration,
punctuation and repeated letters. This supports Shevchenka → Shevchenko and
Лесі Українки → Lesya Ukrainka. It is not a full morphological analyzer or a
translation dictionary for every international name. Exact catalog lookup wins;
multiple matching authors require clarification rather than inventing an identity.

The database evaluates normalized title/name expressions; the application does not
load the complete catalog or author list into process memory. Literal matches keep
the existing two/three-query fast path and need no model inference.

## Topic search and CPU resources

Only explicit topic/recommendation wording invokes `book.search.search_books`,
reusing the existing process-local quantized ONNX encoder and pgvector cosine
ranking. There is no second resident model. Existing thread/token controls apply.
At most 20 database-ranked neighbors are inspected; the assistant returns at most
five whose similarity is at least `max(0.45, best_similarity - 0.08)`.

The gate is a transparent baseline heuristic, not calibrated relevance confidence.
The UI labels these as related catalog matches. An unrelated named book/author
never uses this path. No acceptable matches produce an explicit empty result;
encoder/database failure gives 503, no partial facts and `Retry-After: 5`.
Topic lookup needs the already configured embedding artifacts; ordinary title,
author and availability questions continue to work without inference.

## Catalog gateway and grounding

`ai.services.catalog_assistant(user, query, intent)` calls the read-only
`book.catalog_data.lookup_catalog` gateway. Core catalog code imports no `ai`
module. Neither layer calls booking/issuance write services. Every book, author,
link and count comes from current records; titles are never generated or translated.

`Book.objects.with_availability(now)` counts active loans and unexpired active
reservations. A request for available books applies the same `count > loans + holds`
rule in SQL. Named-title availability still reports an existing out-of-stock book
with zero copies. Borrower identities and loan/hold records are never returned.
Booking rechecks availability atomically; an assistant answer does not hold stock.

Author/title collections are capped at 10 with stable case-insensitive name/title
and primary-key ordering. Partial title matches or multiple authors ask for
clarification. An author without books is reported without fabricating books.

## API and reader interface

`GET /api/v1/assistant/?q=<text>&intent=auto` requires an active signed-in account.
The API is stateless; `intent` accepts `auto`, `title`, `author`, `availability`.
`topic` is an inferred response intent, not a new client-controlled selector.
Responses retain `status`, `intent`, Ukrainian plain-text `answer`, `books`,
`authors`, `checked_at`, `truncated`, and `availability_notice`. Interface labels
are English and catalog data remains in its stored language. Browsable HTML works.
Unknown/repeated parameters, ownership selectors and text over 256 characters are
refused. POST/PATCH/DELETE API operations are refused. Responses are private/no-store.

The CSRF-protected POST page `/assistant/` uses automatic interpretation by default;
manual intent selection remains under Search options. It supports follow-ups such
as “А які з них доступні?” and “Which of these are available?”. For ten minutes the
session retains only the previous result's at most ten book IDs, account ID and
timestamp. It saves no question, answer, title or chat history. IDs are bound to
the signed-in account, and stock is queried again. Singular “Is it available?”
requires one preceding book; missing/expired/ambiguous context asks for clarification.
Clear/new GET, sign-out and empty results withdraw references. API callers do not
receive or inject this browser context.

## Verified demonstration and regression checks

`ai/control/questions_natural.json` contains 16 questions with exact expected
catalog titles for the standard seeded catalog. `scripts/smoke_catalog_assistant.py`
checks every case over HTTP with the real CPU encoder; these same cases are listed
in the PR. Availability counts can change with live loans/reservations, so checks
verify fresh non-negative counts instead of promising a fixed number of copies.

`ai.test_natural_language` covers grammar, declensions/transliteration, current
stock, ambiguous/missing entities, confidence gating with controlled vectors,
model failure, no-inference paths, context isolation/expiry/clear, HTML API and
permissions. Existing assistant and all other app suites remain enabled.
Chrome tests submit Ukrainian and English questions, follow sources, exercise
follow-ups and keyboard controls, run axe, simulate source failure in a disposable
DB, and verify private-log handling and unchanged loan/reservation row counts.
