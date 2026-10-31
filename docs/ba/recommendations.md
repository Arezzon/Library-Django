# Personalized book recommendations (KAN-31)

`GET /api/v1/books/recommendations/?limit=10` returns an array of existing book
representations (`id`, `name`, `description`, `count`, `available_count`, `authors`).
The session account is the only signal owner, including for librarians. Anonymous
requests receive 401; inactive accounts are refused. Only `limit` is accepted;
account selectors such as `user_id` receive 400. `limit` defaults to 10 and must
be an integer from 1 to 20. No event history, reader IDs or vectors are returned.
The reader interface may also call `book.recommendations.recommend_books(user, limit)`.

## Baseline ranking

1. Read at most the 200 most recent eligible events from the current account within
   the last 90 days: supported book actions and server-recorded KAN-30 searches.
   Ignore future, deleted-resource and unsupported events. Authentication and loan
   reassignment do not establish a book preference. Author-only searches without
   text, malformed payloads and client-origin search events are ignored.
2. Use the strongest action per book: view **1**, click **2**, borrow intent **3**,
   borrowed or returned **4**. Repeated actions on a book do not accumulate weight.
   These baseline weights express intent; they are not learned or calibrated ratings.
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
No new ML model, persisted profile, queue job or migration is needed. Book-only
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
personal signal payload. KAN-51 owns completing search persistence and adding explicit
likes/favorites; this ticket consumes existing recorded catalog searches only.
Favorites/likes (KAN-51) and rating models (KAN-59–61) are not present in this base. They are not invented
or inferred from event JSON: explicit positive/negative feedback needs integration
when those schemas and their agreed semantics are available. KAN-59 owns rating
CRUD and its scale, KAN-60 owns its UI, and KAN-61 owns connecting that separate
signal to this ranking, including changed/deleted ratings. No rating is inferred
from a like or from an arbitrary event JSON value. Recommendation explanations
(KAN-32) remain outside this baseline. The alphabetical fallback and weights are the
baseline rules proposed for review, rather than a claim that another ticket defined them.

## Verification

The `book.test_recommendations` suite runs with every existing Django suite in the
Docker Build smoke-test matrix against PostgreSQL. It checks personalization from book and search history, signal
strength, bounded inference, repeat suppression, stable Top-N, missing history/vectors, current loan and
reservation stock, expiry, API validation and account isolation. The CI HTTP check
also requests recommendations as a seeded reader and verifies anonymous refusal.
