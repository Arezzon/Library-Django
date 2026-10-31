# Personalized book recommendations (KAN-31)

`GET /api/v1/books/recommendations/?limit=10` returns an array of existing book
representations (`id`, `name`, `description`, `count`, `available_count`, `authors`) plus a read-only `reason` string.
The session account is the only signal owner, including for librarians. Anonymous
requests receive 401; inactive accounts are refused. Only `limit` is accepted;
account selectors such as `user_id` receive 400. `limit` defaults to 10 and must
be an integer from 1 to 20. No raw event records, reader IDs or vectors are returned. A reason may quote only
the current account's contributing book title or search text.
The reader interface may also call `book.recommendations.recommend_books(user, limit)`.

## Baseline ranking

1. Read at most the 200 most recent eligible events from the current account within
   the last 90 days: supported book actions and server-recorded KAN-30 searches.
   Ignore future, deleted-resource and unsupported events. Authentication and loan
   reassignment do not establish a book preference. Author-only searches without
   text, malformed payloads and client-origin search events are ignored.
2. Use the strongest action per book: view **1**, click **2**, borrow intent **3**,
   borrowed or returned **4**. Repeated actions on a book do not accumulate weight.
   Current likes/favorites (KAN-51) override the behavioral weight with **5**,
   once per book even if both flags are set. These weights express intent; they
   are not learned or calibrated ratings.
3. Take up to the three latest distinct nonempty search texts (case-insensitive
   deduplication; at most 200 characters each). Encode them with the existing shared
   model and its configured query prefix; each has weight **1**. No separate model,
   training, new query storage or private text cache is introduced. If inference
   fails, keep valid book signals or use the fallback.
4. Normalize compatible persisted book embeddings and search vectors, then build a
   weighted mean direction. Rank candidates by cosine distance to that direction,
   breaking ties by book ID. Do not recommend books used to construct the profile.
5. For an empty or unusable profile, return available books ordered by case-insensitive
   title and ID. Fill short personalized lists from the same alphabetical order without
   duplicates. Missing embeddings do not prevent a book from appearing in this fallback.

The baseline fallback uses no other reader's history, popularity, random sampling or
personal data. Ranking is stable for unchanged catalog, events, model and availability.
The ranking needs no new ML model or persisted profile. KAN-51 adds preference
tables; search events reuse the existing queue. Book-only
profiles need no inference; search profiles reuse the existing process-local encoder.
Only compatible model/revision vectors contribute to the profile and cosine ranking.

## Availability and dependencies

Every request uses the current time with `Book.objects.with_availability(now)`: total
copies minus unreturned loans and active reservations whose expiry is strictly later
than now. Candidates must have at least one remaining copy. Exclude the reader's own
active loans and holds even when other copies remain. Returns, cancellations, stock
changes and expiry affect the next request without a result cache or waiting for beat.
Results describe availability at request time and do not reserve a copy.

KAN-30 and the KAN-55–58 reservation models are present. The baseline input contract, to be aligned with KAN-50, is `UserEvent` restricted to the caller, configured compatible
`BookEmbedding` vectors, and the shared `Book.objects.with_availability(now)` stock
rule. The public service is `recommend_books(user, limit)`; its output contains no
raw personal signal records. KAN-32 adds a reason based on the caller's own signal.
KAN-51 adds durable current likes/favorites through `read_book_preferences(user)`
and records successful catalog/API searches with retry-safe identities. Numerical
ratings remain separate: KAN-59 owns CRUD/scale, KAN-60 the UI, and KAN-61 ranking
integration. No rating is inferred from a like or arbitrary event JSON. The
alphabetical fallback and weights remain transparent baseline rules.

## Reasons (KAN-32)

Every returned book has a nonempty Ukrainian `reason` string. It is plain text,
not HTML. The explanation reuses the signals actually included in the profile:
for each candidate it selects the largest **positive weight × cosine similarity**
contribution. Normalizing the total profile divides all contributions by the same
constant, so the selected factor reflects the ranking rather than a fabricated
post-hoc similarity. It is one main factor, not an exhaustive account of all signals.
Equal contributions use the profile's stable source order (book IDs, then retained
searches). Ranking, result limits and availability rules are unchanged.

- A book action names its current title and the strongest recorded action. Views,
  clicks and borrowing intent do not claim that the reader borrowed or read a book.
  A loan says the reader borrowed it; a return says they returned it. Even a loan
  or return is not treated as proof that the book was read.
- A search quotes only the current account's successfully encoded search text.
  Failed/invalid search encodings, deleted books and incompatible seed vectors do
  not become named reasons.
- A ranked candidate with no positive individual contribution has the neutral
  reason `Рекомендовано за сукупністю ваших інтересів.`
- Empty-history fallback and alphabetical padding explicitly say
  `Доступна книга із запасного списку рекомендацій.` They do not invent a personal
  connection, including when the rest of the response is personalized.

Example fragment after a real book-view event:

```json
{
  "name": "1984",
  "reason": "Рекомендовано, бо ви переглядали «Clean Code: A Handbook of Agile Software Craftsmanship»."
}
```

Titles and exact order depend on the catalog and the history. Explanation generation
uses no LLM, additional inference, persisted reason, or per-result database lookup.
Source titles and candidate vectors are joined in bulk. Other catalog and search
responses do not gain the recommendation-only field. Session isolation and refusal
of account selectors continue to apply, including to librarians.

## Verification

The `book.test_recommendations` suite runs with every existing Django suite in the
Docker Build smoke-test matrix against PostgreSQL. It checks personalization from book and search history, signal
strength, bounded inference, repeat suppression, stable Top-N, missing history/vectors, current loan and
reservation stock, expiry, API validation and account isolation. The CI HTTP check
also requests recommendations as a seeded reader and verifies anonymous refusal.

## Persistent explicit signals (KAN-51)

Likes and favorites are now available as independent owned states. Either gives
weight 5, with no double boost for both. Current state is read on each request;
removal drops the explicit signal while other history can remain. See
[the preference contract](reader-preferences.md) for API routes, search identities,
privacy and failure handling. Numerical ratings remain a separate future stage.
