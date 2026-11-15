# Library Django

![LibrarySys](/images/library-sys.png)

**Library Django** is a library management system built with **Django 5.2 LTS**,
Django REST Framework and PostgreSQL. It provides a server-rendered web UI,
role-based access, borrowing workflows, an OpenAPI API, pgvector-backed book
embeddings, personalized discovery, reservations and asynchronous activity analytics.

> The project is ready to run with Docker Compose. A local `venv` setup is also
> supported when PostgreSQL with pgvector and Redis are available.

## Contents

| Getting started | Using the site | Running it |
| --- | --- | --- |
| [Prerequisites](#prerequisites) | [Demo data](#demo-data) | [Configuration](#configuration) |
| [Features](#features) | [Reader features](#reader-features) | [Tests and checks](#tests-and-checks) |
| [Architecture](#architecture) | [Book embeddings](#book-embeddings) | [Troubleshooting](#troubleshooting) |
| [Quick start with Docker](#quick-start-with-docker) | [Activity Analytics](#activity-analytics) | [Project layout](#project-layout) |
| [Local development](#local-development-with-venv) | [REST API](#rest-api-and-interactive-docs) | [Deployment](#deployment) |
| [Local service requirements](#local-service-requirements) | [Book covers](#book-covers) | [Delivery status and plans](#delivery-status-and-plans) |
|  |  | [License](#license) |

## TL;DR

### Docker

```bash
cp .env.example .env    # then set SECRET_KEY and DB_PASSWORD
docker compose -f docker-compose-dev.yml up --build
```

Open <http://localhost:8000>.

### Windows `venv`

```powershell
.\.venv\Scripts\Activate.ps1
cd .\library
python manage.py migrate
python manage.py runserver
```

PostgreSQL with pgvector and a Redis-compatible broker such as Memurai must
already be running locally. See [Local service requirements](#local-service-requirements)
before using the `venv` setup.

## Prerequisites

| Setup | Required | Optional |
| --- | --- | --- |
| Docker | Docker Desktop with Compose | — |
| Windows `venv` | Python 3.12, PostgreSQL + pgvector, Redis or Memurai | WSL for Redis |
| Linux/macOS `venv` | Python 3.12, PostgreSQL + pgvector, Redis | — |
| Tests | Project and development dependencies, PostgreSQL + pgvector | Node.js and Chromium/Chrome for browser, accessibility and JavaScript checks |
| Embeddings | PostgreSQL + pgvector and Python dependencies | Network access once, to fetch the model (`venv` only; images ship with it) |

## Features

| Area | Included |
| --- | --- |
| Catalog | Required book titles, descriptions, stock counts and authors; compact local covers on book pages, with a placeholder for other titles ([covers](#book-covers)) |
| Discovery | Semantic search by meaning, a For You page of recommendations, likes and saved books, private 1–5 ratings, and an assistant that answers catalog questions in Ukrainian or English ([reader features](#reader-features)) |
| Borrowing | Librarians lend at the desk; return, reopen and reassign orders. Every loan starts with a librarian, and none while the reader has an overdue loan |
| Reservations | Immediate holds for a configurable 1–168 hours (default 48), at most 3 per reader, with overdue and duplicate-book guards. Saved deadlines stay unchanged when the policy changes. Readers see Kyiv-time deadlines and cancel their own holds; librarians issue them or cancel with a confirmed reason ([guide](docs/features/reservations.md)) |
| Accounts | Email-based users and profiles with three roles. Sign-up always creates a reader. Librarians run the catalog, loans, reservations and account status. Administrators have every librarian right and are the only ones who make someone a librarian or take the role away, and only they change an administrator's account. The operator creates administrators on the server ([guide](docs/deployment/raspberry-pi-portainer.md#create-the-first-administrator)) |
| Administration | Django admin and librarian-only management screens |
| API | Endpoints under `/api/v1/`, each open only to its stated audience, plus Swagger and ReDoc |
| Embeddings | Multilingual 1024-dimensional `bge-m3` vectors generated with ONNX Runtime |
| Analytics | Aggregate library overview, explainable demand forecast and filtered activity log. Search events record displayed result counts and similarity; catalog clicks can be linked to the originating search ([search analytics](docs/features/search-analytics.md)) |
| Logs and audit | One log line format whose request identifier follows a request into the worker; secrets and search text redacted; rotated logs; a read-only audit trail of role, account, loan and stock changes in the admin site |
| Deployment | Docker Compose for development; a Raspberry Pi 5 Portainer stack from multi-architecture GHCR images |

## Architecture

```text
                         +-----------------------+
                         | Browser / REST client |
                         +----------+------------+
                                    |
                                    v
+----------------+       +----------+------------+       +-------------------+
| Redis          | <---- | Django web            | ----> | PostgreSQL        |
| broker         |       | runserver / gunicorn  |       | + pgvector        |
+-------+--------+       +-----------------------+       +---------+---------+
        |                                                          ^
        v                                                          | daily pg_dump
+----------------+                                       +---------+---------+
| Celery worker  |                                       | Backup            |
| events queue   |                                       | pgbackups volume  |
+----------------+                                       +-------------------+
```

The worker persists tracking events asynchronously, and its embedded Celery beat
schedules reservation expiry every five minutes. Availability releases a hold at
its saved deadline even before the expiry task updates its state. The web
process can serve the application without a worker, but event API requests
return `503` while
the Redis broker is unavailable. The backup service takes a daily, checked
backup of the database into a volume of its own.

## Quick start with Docker

**Requirements:** Docker Desktop with Docker Compose.

#### Linux / macOS

```bash
cp .env.example .env
```

#### Windows PowerShell

```powershell
Copy-Item .env.example .env
```

Fill in the required values in `.env`. The project ships no default secrets,
so Compose refuses to start while they are blank:

| Variable | Value |
| --- | --- |
| `SECRET_KEY` | Output of `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DB_PASSWORD` | A password of your choice; Compose creates the database with it |

```bash
docker compose -f docker-compose-dev.yml up --build
```

Open <http://localhost:8000>. Compose starts:

| Service | Purpose | Port |
| --- | --- | --- |
| `web` | Django application with Gunicorn | `8000` |
| `db` | PostgreSQL 18 with pgvector | internal `5432` |
| `redis` | Celery broker (Redis 8) with persistent AOF storage | internal `6379` |
| `worker` | Persists activity events from the `events` queue; beat schedules reservation expiry | — |
| `backup` | Takes a checked daily `pg_dump` into the `pgbackups` volume | — |

The first boot waits for PostgreSQL, applies migrations and seeds demo data
when `DJANGO_SEED=true`. Seeding is idempotent and becomes a quick no-op after
users already exist.

```bash
docker compose -f docker-compose-dev.yml down       # stop the stack
docker compose -f docker-compose-dev.yml down -v    # stop and delete database/Redis volumes
```

The stack keeps its data in the `pgdata18` and `redisdata8` volumes. Stacks
created before the move to PostgreSQL 18 and Redis 8 start freshly seeded on
them; the old `<project>_pgdata` and `<project>_redisdata` volumes are no longer
used and can be removed with `docker volume rm`.

> **Tip:** `docker compose -f docker-compose-dev.yml up --build -d` starts the stack in the background.
> Use `docker compose -f docker-compose-dev.yml logs -f web worker` to follow application and worker logs.
> Each line carries the request's `X-Request-ID`, so one request can be followed from the web
> service into the worker; the operator guide's "Viewing logs" explains the format.

## Local development with `venv`

The Django project root is `library/`; run management commands from there.

### Windows PowerShell

```powershell
cd "D:\path\to\Library-Django"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\requirements.txt
```

### Linux / macOS

```bash
cd /path/to/Library-Django
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r ./requirements.txt
```

`requirements.txt` in the repository root is the only runtime dependency list; the
image installs the same file.

Create `.env` in the repository root from `.env.example`:

```dotenv
SECRET_KEY=<generated-secret-key>
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

DB_ENGINE=django.db.backends.postgresql_psycopg2
DB_NAME=library_db
DB_USER=postgres
DB_PASSWORD=<your-postgres-password>
DB_HOST=localhost
DB_PORT=5432

CELERY_BROKER_URL=redis://localhost:6379/0
```

Django refuses to start without `SECRET_KEY`; generate one with
`python -c "import secrets; print(secrets.token_urlsafe(50))"`. Instead of the
`DB_*` values you can set a single
`DATABASE_URL=postgresql://user:password@localhost:5432/library_db`, which
takes precedence.

Fetch the embedding model once (about 0.6 GB, into `.cache/book-embeddings`),
then apply migrations and start Django:

```bash
python scripts/fetch_embedding_model.py
```

#### Windows PowerShell

```powershell
cd .\library
python manage.py check
python manage.py migrate
python manage.py runserver
```

#### Linux / macOS

```bash
cd library
python manage.py check
python manage.py migrate
python manage.py runserver
```

Open <http://127.0.0.1:8000>.

### Local service requirements

The local database must provide the `vector` extension. Installing the Python
package `pgvector` alone is not enough: it only provides Django/Python support.

```sql
CREATE DATABASE library_db;
\c library_db
CREATE EXTENSION IF NOT EXISTS vector;
```

If PostgreSQL is installed on Windows but pgvector is not, use the
`pgvector/pgvector` Docker image for the database, or install a PostgreSQL 18
compatible pgvector binary. The project does not support SQLite for migrations
because book embeddings are stored in a pgvector `vector` column.

For activity tracking, a Redis-compatible broker must listen on
`localhost:6379`. Windows users can choose either **Memurai** (native Windows
service) or Redis through WSL. Memurai speaks the Redis protocol, so it works
with the project's Celery configuration without code changes.

With Memurai, install the Community edition, start the Memurai service and
verify the default port:

```powershell
Get-Service *Memurai*
Get-NetTCPConnection -State Listen -LocalPort 6379
```

If the Memurai CLI is available, this should return `PONG`:

```powershell
memurai-cli ping
```

If `memurai-cli` is not in `PATH`, the service can still be used. The port
check is sufficient, or run the CLI from the Memurai installation directory.

### Redis through WSL (Windows)

```bash
sudo apt update
sudo apt install redis-server
sudo service redis-server start
redis-cli ping                  # PONG
```

Keep the broker URL in `.env` unchanged for either option:

```dotenv
CELERY_BROKER_URL=redis://localhost:6379/0
```

Run the worker in a second PowerShell window:

```powershell
cd "D:\path\to\Library-Django"
.\.venv\Scripts\Activate.ps1
cd .\library
celery -A library worker --loglevel=INFO --concurrency=2 --queues=events
```

> **Tip:** Without Redis and Celery, normal pages still work. Only asynchronous
> analytics delivery is affected; `POST /api/v1/events/` returns retryable
> `503 Service Unavailable`.

## Demo data

Seed users, authors, books and sample orders after migrations:

```powershell
cd library
python seed_db.py
```

| Email | Password | Role |
| --- | --- | --- |
| `librarian@library.com` | `admin123password` | Librarian |
| `reader@library.com` | `reader123password` | Reader |
| `alice@library.com` | `alice123password` | Reader |
| `bob@library.com` | `bob123password` | Reader |

> **Security:** These credentials are for local/demo use only. Set a unique
> `SECRET_KEY` and replace seeded passwords before deploying.

## Reader features

Everything here needs a signed-in account and touches only that account's own
data. [The reader walkthrough](docs/features/reader-verification.md) checks each
feature step by step.

### Search and recommendations

The catalog search finds books by meaning, not only by words in the title
([semantic search](docs/ba/semantic-search.md)); the API is
`GET /api/v1/books/search/?q=`. **For You** in the header opens
`/book/recommendations/`: available books ranked for the account, each with the
reason it was picked. The JSON is `GET /api/v1/books/recommendations/`
([algorithm](docs/ba/recommendations.md), [data contract](docs/ba/recommendation-data.md)).

### Likes and saved books

Readers like and save books on the book page and manage them on **Saved Books**
(`/book/preferences/`). The API is `GET/PATCH/DELETE /api/v1/books/<id>/preferences/`
and `GET /api/v1/me/book-preferences/?kind=all|likes|favorites`
([contract](docs/ba/reader-preferences.md)).

### Ratings

A reader gives a book a private score from 1 to 5 with keyboard-accessible stars
on its page. Others see only the mean and the count, also at
`GET /api/v1/books/<id>/rating-summary/`. `GET/PUT/PATCH/DELETE
/api/v1/books/<id>/rating/` reads or changes only the account's own score.
Recommendations treat 4–5 as positive, 1–2 as negative and 3 as neutral, and
leave out books already rated ([contract](docs/features/book-ratings.md)).

### Catalog assistant

**Assistant** (`/assistant/`) answers catalog questions in Ukrainian or English
with facts and links to the books, without a language model, for example
`знайди твори Шевченка`, `Is 1984 available?` or `Порадь книги про програмування`.
It asks back when a question matches several books, and keeps no question text.
The API is `GET /api/v1/assistant/?q=` ([contract](docs/ba/catalog-assistant.md),
[page design](docs/ba/assistant-interface.md)).

### Reservations and collection periods

Readers reserve from the book page and follow the saved deadline in **My
Reservations** (`/order/reservations/`). Confirmation and reservation history
use the same Europe/Kyiv time and EET/EEST zone label. At the deadline the copy
becomes available again; the reader can reserve it again if it is still free.

Librarians and administrators set the library-wide collection period at
`/order/reservations/settings/`, next to **Reservation Desk**. The value is a
whole number from 1 to 168 hours, defaulting to 48. It applies to new web and API
reservations; existing holds keep their original deadline. A maximum of three
active holds, overdue loans, duplicate reservations and copies held by other
readers are checked in the shared borrowing workflow. See the
[reservations guide](docs/features/reservations.md) for issuing, cancellations
and refusal codes.

### Book covers

Book pages show a cover beside the title in a shared light frame: 64 pixels
wide on small screens and 80 pixels on larger ones, with contained image
proportions. The nine sample catalog titles use locally bundled Open Library
images; other titles receive a neutral placeholder. Matching is by trimmed,
case-insensitive title, so existing sample books need no reseeding or migration.

New titles need a curated image and a manifest entry; there is no automatic
runtime lookup or upload feature. Sources and image URLs are recorded in
`library/book/covers.json`. The catalog has no ISBN, so artwork illustrates a
work rather than guaranteeing the physical edition. See the
[cover guide](docs/features/book-covers.md) and actual
[desktop](docs/screenshots/book-covers/desktop.png) /
[mobile](docs/screenshots/book-covers/mobile.png) screenshots.

## Book embeddings

Each book receives a multilingual embedding generated from its title and
description, used by [semantic search](docs/ba/semantic-search.md). The model is
[BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) (dense vectors), run from the
pinned int8 ONNX export in `Xenova/bge-m3` through ONNX Runtime on CPU. Vectors
have 1024 dimensions and are stored normalized in PostgreSQL with pgvector. The
same model runs on amd64 and arm64.

The model is defined in one place, `library/book/embedding_config.py`, and every
part of the system reads it from there.

- **Docker images** ship with the model: the build runs
  `scripts/fetch_embedding_model.py`, and containers never download it.
- **A local `venv`** needs it fetched once: `python scripts/fetch_embedding_model.py`
  from the repository root (it writes `.cache/book-embeddings/manifest.json`).
- **Another model** is chosen at build time with `BOOK_EMBEDDING_*` build arguments,
  for example
  `docker build --build-arg BOOK_EMBEDDING_MODEL=<owner/name> --build-arg BOOK_EMBEDDING_MODEL_REVISION=<40-hex commit> ...`.
  Empty values mean the defaults. Setting a different value only at runtime stops
  startup with the `book.E001` check.

```bash
# Docker
docker compose -f docker-compose-dev.yml exec web python manage.py generate_book_embeddings

# One book, smaller batches, more threads, or a forced regeneration
docker compose -f docker-compose-dev.yml exec web python manage.py generate_book_embeddings --book-id 1 --batch-size 8
docker compose -f docker-compose-dev.yml exec web python manage.py generate_book_embeddings --threads 4
docker compose -f docker-compose-dev.yml exec web python manage.py generate_book_embeddings --force
```

| Change | Result |
| --- | --- |
| New book | Embedding generated on save |
| Title/description changed | Embedding regenerated |
| Stock-only change | Current embedding reused |
| Missing/stale vector | Repaired on save, backfill or container startup |
| Model changed (new image) | Every vector re-encoded on startup, before traffic |
| Inference failure | Transaction rolls back the book change |

The web container runs `generate_book_embeddings` after migrations on every
start. It skips books whose vectors already match the model, so a normal start
runs no inference; after a model change it re-encodes the whole catalog before
the site serves requests.

Tuning: each Gunicorn worker loads one model copy (about 0.6 GB) before taking
requests. `WEB_CONCURRENCY` (default 3) sets the number of workers and
`BOOK_EMBEDDING_THREADS` (default 2) the inference threads per worker; lower the
workers to save memory, raise the threads to cut latency.

## Activity Analytics

Authenticated book views, catalog searches, authentication actions and order
changes are tracked as events. Librarians can open **Analytics** at
<http://localhost:8000/events/> and view:

| Dashboard | Visibility |
| --- | --- |
| Library overview: aggregated loans, reservations and views | Librarians |
| Global activity, filters and recent events (Activity log) | Librarians |
| Selected user's activity | Librarians |
| Analytics dashboard | Not available to readers |
| Raw tracking API | Authenticated clients with CSRF |

**Analytics** opens on the **Overview** tab (KAN-54): loans, returns, borrowers,
overdue loans, reservations and book views for the last 7, 30 or 90 days or 12
months, each against the period before, with loans over time, the most borrowed
and most viewed books and reader counts. It shows no personal data. The per-event
screen above is the **Activity log** tab at <http://localhost:8000/events/activity/>.
The **Forecast** tab (KAN-35, <http://localhost:8000/events/forecast/>) ranks books by
a 0–100 demand index made of five weighted scores (loans, reservations, interest,
preferences and stock pressure), forecasts each book's loans for the next 30 days
and says how many copies to buy ([forecast design](docs/ba/demand-forecast.md)).
The Overview figures also come from `GET /api/v1/analytics/overview/` (KAN-34):
loans and returns from orders, interest from these events, with every metric
defined in [the dashboard design](docs/ba/analytics-dashboard.md). The Forecast
is a separate server-rendered page; its demand index and purchase suggestions
are transparent weighted rules, not a trained prediction model.

Client events are sent to:

```text
POST /api/v1/events/
```

The request accepts a UUID `event_id`, supported `event_type`, `book_id` and
catalog/book `path`, plus optional `search_id` for `book_click` only. The same
UUID can be retried safely. A successful response is `202 Accepted`, which
means the event was queued, not necessarily persisted.

```json
{
  "event_id": "2d931f2f-0d2e-4e58-a8b0-7f4b9e9a6d24",
  "event_type": "book_click",
  "book_id": 1,
  "path": "/book/1/"
}
```

Tracking is best effort for business actions: a broker outage is logged and
does not undo an otherwise successful book or order operation. The browser
keeps at most 50 pending events per user in `sessionStorage` and retries the
same UUID after temporary network failures.

### Search quality and click attribution

Since KAN-105 and KAN-106, successful web and API searches record the number of
books actually displayed and the first displayed book's raw cosine similarity.
Similarity is `null` for empty results or author-only browsing; zero and negative
values remain valid measurements. Search events retain the existing query,
trimmed to 200 characters, and the optional author filter. Technical logs redact
search text; this does not mean the event database contains no search text.

Catalog links from a recorded web search carry its current action UUID. The
tracking API accepts optional `search_id` only for `book_click`, validates it as a
UUID and derives a reference bound to the signed-in account. This connects a
reader's search to the book they open without copying the query into the click.
Ordinary catalog clicks and older events still work without this reference.
[Search analytics](docs/features/search-analytics.md) documents the payload,
identity mapping and asynchronous persistence behavior.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `extension "vector" is not available` | pgvector is not installed in the PostgreSQL server | Use the pgvector Docker image or install a PostgreSQL-compatible pgvector extension, then run `python manage.py migrate` again |
| `ImproperlyConfigured: SECRET_KEY is not set` | `.env` or the service environment has no `SECRET_KEY` | Generate a key with `python -c "import secrets; print(secrets.token_urlsafe(50))"` and set it |
| `required variable SECRET_KEY is missing a value` | Compose found no `.env` or blank required values | Copy `.env.example` to `.env` and fill in `SECRET_KEY` and `DB_PASSWORD` |
| `password authentication failed for user "postgres"` | Wrong PostgreSQL credentials | Set the actual `DB_PASSWORD` in `.env` and retry. A Compose volume keeps the password it was created with (`postgres` for volumes created without `.env` by earlier versions); reuse it or recreate the volume with `docker compose -f docker-compose-dev.yml down -v` |
| `503 /api/v1/events/` | Redis/Memurai is stopped or Celery cannot reach the broker | Start the broker on port `6379`, verify it responds to `PING`, then start the Celery worker |
| Analytics page is empty | Events are queued but not consumed | Keep `celery -A library worker --queues=events` running and refresh the page |
| `Missing staticfiles manifest entry` in tests | Static files were not collected | Run `python manage.py collectstatic --noinput` from `library/` |
| `psql` is not recognized on Windows | PostgreSQL `bin` directory is not in `PATH` | Use `C:\Program Files\PostgreSQL\18\bin\psql.exe` or add that directory to `PATH` |

## REST API and interactive docs

The API is mounted under `/api/v1/`. It accepts session sign-in only: sign in at
`/authentication/login/` and send the session cookie, plus the `X-CSRFToken` header for
changes. Each operation is open only to its audience:

| Endpoint | Purpose | Audience |
| --- | --- | --- |
| `/api/v1/` | Index of the API | Anyone |
| `/api/v1/version/` | Commit of the running image | Anyone |
| `/api/v1/books/search/?q=` | Semantic search | Signed-in accounts |
| `/api/v1/assistant/?q=` | Grounded catalog assistant (KAN-52) | Signed-in accounts |
| `/api/v1/books/recommendations/?limit=10` | Available books ranked for the current account with a per-book reason; [algorithm](docs/ba/recommendations.md) / [data contract](docs/ba/recommendation-data.md) | Signed-in accounts, own signals only |
| `/api/v1/book/` | Books | Signed-in accounts read; librarians create, change and delete |
| `/api/v1/author/` | Authors | Signed-in accounts read; librarians create, change and delete |
| `/api/v1/user/` | Accounts | Librarians list, create, change and delete; only an administrator sets `role` (reader or librarian) or changes an administrator's account; a reader reads and renames only their own account |
| `/api/v1/order/` | Orders (loans) | Librarians start, read and change every order; a reader reads their own |
| `/api/v1/user/<id>/order/` | Orders for one user | That user or a librarian reads; only librarians start, change or delete |
| `/api/v1/reservation/` | Reservations | Signed-in accounts reserve for themselves, and read and cancel their own; librarians read every reservation, issue it (`<id>/issue/`) or cancel it with a reason (`<id>/cancel/`) |
| `/api/v1/events/` | Queue an activity event | Signed-in accounts |
| `/api/v1/analytics/overview/?period=30d&limit=10` | Aggregated loans, returns, reservations, book views, top books and reader counts for `7d`, `30d`, `90d` or `12m`, compared with the period before; no personal data ([metrics](docs/ba/analytics-dashboard.md)) | Librarians and administrators |

A request that is not signed in gets `401` with `WWW-Authenticate: Session`. A signed-in
account without the right role gets `403`, and so does a reader who sends `role`,
`is_active`, `email` or `password` for their own account, or a librarian who sends `role` or
changes an administrator's account. A reader who asks for another
user's record gets `404`, the same answer as for a record that does not exist. Deleting an
author who is attached to a book, or a book that has loans or reservations, gets `409`, and
nothing changes; the web pages and the admin site refuse it too. Deleting an account, in any
channel, keeps its loans and reservations: they are the library's records, so their `user`
becomes `null` and the pages show "Deleted reader". An unreturned book stays on loan until a
librarian returns it (KAN-82). A reservation, an issue or
a loan that a rule refuses gets `409` with a `code` and a message that says what to do next;
the [reservations guide](docs/features/reservations.md#through-the-api) lists the codes.
Every book needs a title: creating or changing a book with an empty `name`, or one of only
spaces, gets `400` with an error for `name`, and the web form and the admin site show the
error beside the title. The database refuses such a book too (KAN-81).

On the web, a signed-in reader who opens a librarian or administrator page gets the same
`404` page as an unknown address, so the site does not confirm that the page exists, while
an anonymous visitor is sent to sign in (KAN-80).
The schema states
each operation's audience in its description and in `x-audience`.

API datetimes carry the library's offset, Europe/Kyiv (`+02:00` or `+03:00`), for the same
instants as before.

Interactive documentation is generated by `drf-spectacular`:

```text
Swagger UI:      http://localhost:8000/api/docs/
ReDoc:           http://localhost:8000/api/redoc/
OpenAPI schema:  http://localhost:8000/api/schema/
```

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DEBUG` | `False` | Django debug mode; set `True` for local development only |
| `LOG_LEVEL` | `INFO` | Level of the web, gunicorn and worker logs: `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`; any other value stops startup |
| `SECRET_KEY` | — (required) | Session and cryptographic signing |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Accepted HTTP hosts |
| `TRUST_X_FORWARDED_PROTO` | `False` | Treat `X-Forwarded-Proto: https` as secure; set `True` only behind your HTTPS proxy, where it also makes session and CSRF cookies HTTPS-only; an unrecognized value stops startup |
| `CSRF_TRUSTED_ORIGINS` | empty | Comma list of trusted origins for form posts, e.g. `https://library.example.com` |
| `DATABASE_URL` | — | Full PostgreSQL URL; overrides the `DB_*` values |
| `DB_NAME` | `library_db` | PostgreSQL database |
| `DB_USER` | `postgres` | PostgreSQL user |
| `DB_PASSWORD` | — (required by Compose) | PostgreSQL password |
| `DB_HOST` | `localhost` | PostgreSQL host; Compose uses `db` |
| `DB_PORT` | `5432` | PostgreSQL port |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Redis broker |
| `DJANGO_SEED` | `false`; `docker-compose-dev.yml` sets `true` | Seed demo data on container startup |
| `BOOK_EMBEDDING_CACHE_DIR` | `.cache/book-embeddings` | Model cache directory |
| `BOOK_EMBEDDING_THREADS` | `2` | Inference threads per Gunicorn worker |
| `WEB_CONCURRENCY` | `3` | Gunicorn workers; each holds one model copy (about 0.6 GB) |
| `BACKUP_HOUR` | `1` | UTC hour at or after which the `backup` service takes each day's backup |
| `BACKUP_KEEP_DAYS` | `7` | Days backups are kept; the 7 newest always stay |

`.env` is ignored by Git and Docker builds, so local secrets reach neither
commits nor images. `.env.example` holds placeholders only; never commit real
credentials.

## Tests and checks

Install runtime and development dependencies first. Tests require PostgreSQL
with pgvector; the database user must be able to create the disposable test
database. Run Django management commands from `library/`:

```powershell
python manage.py collectstatic --noinput
python manage.py check
python manage.py test authentication author book order events audit ai
```

Docker smoke checks:

```bash
docker compose -f docker-compose-dev.yml exec -T -e RUN_BOOK_EMBEDDING_MODEL_TESTS=1 -e CELERY_TASK_ALWAYS_EAGER=True web python manage.py test authentication author book order events audit ai --verbosity 2
docker compose -f docker-compose-dev.yml exec -T web python manage.py smoke_test_tracking
docker compose -f docker-compose-dev.yml exec -T backup library-backup once
node --test scripts/test_tracking_js.cjs
```

The full CI test command enables real-model checks with
`RUN_BOOK_EMBEDDING_MODEL_TESTS=1` and runs unit-test Celery tasks eagerly with
`CELERY_TASK_ALWAYS_EAGER=True`. Default local test runs mock the encoder. Real
queue delivery and recovery use the separate smoke checks with a running broker
and worker.

**Docker Build** runs on pull requests targeting `main` or `KAN-*`, pushes to
`main` and version tags. Its five native smoke-test runners cover
`ubuntu-latest`, `ubuntu-26.04`, `ubuntu-26.04-arm`, `ubuntu-24.04` and
`ubuntu-24.04-arm`. Checks include the full PostgreSQL suites, HTTP/API smoke
checks and, on `ubuntu-latest`, browser navigation, ratings, reader preferences,
the assistant, reservation settings, load, accessibility and sign-in. CodeQL
checks Actions, JavaScript/TypeScript and Python separately. The current
[workflow](.github/workflows/docker-build.yml) defines the exact commands;
test counts and historical measurements in delivery records describe those runs.

CI also restores that backup into a scratch database and compares every table's
row count with the live database; the operator guide's "Restore into a separate
database" shows the same restore by hand.

CI's `ubuntu-latest` leg also sends 100 simultaneous reservations for a book's
only copy, 20 times, and fails unless exactly one succeeds each time. The script
makes its own temporary accounts and books and removes them afterwards. To run it
against the development stack, from the repository root:

```bash
python scripts/smoke_reservation_load.py --compose-file docker-compose-dev.yml --burst 100 --runs 20
```

`--readers 30` adds the load check that the operator guide's "Check reservations
under load" runs on the Pi.

CI's `ubuntu-latest` leg also checks the main pages for accessibility: axe, run
through Playwright in Chromium, must find no WCAG 2.2 level A or AA violation on
any of them, signed in as the demo reader and the demo librarian. The only data it
changes is one reservation, which the reader makes and cancels again. To run it
against the development stack started with demo data, from the repository root
(Node.js is needed):

```bash
npm ci --prefix scripts/a11y
npx --prefix scripts/a11y playwright install chromium
node scripts/a11y/check_pages.mjs --base-url http://localhost:8000
```

`A11Y_READER_EMAIL`, `A11Y_READER_PASSWORD`, `A11Y_LIBRARIAN_EMAIL` and
`A11Y_LIBRARIAN_PASSWORD` sign in with other accounts. The keyboard and
screen-reader checks stay manual; `specs/003-priority-tech-debt/quickstart.md`
section 10 lists them.

The same leg runs the browser sign-in tests in headless Chrome: the demo reader
signs in and out, and wrong details show the error. To run them against the
development stack started with demo data, from the repository root (Google Chrome
is needed):

```bash
python -m pip install -r requirements-dev.txt
SELENIUM_HEADLESS=1 BASE_URL=http://localhost:8000 python -m pytest library/test_selenium_auth_pytest.py library/test_selenium_auth_unittest.py -v -p no:cacheprovider
```

Without `SELENIUM_HEADLESS=1` a Chrome window opens, so you can watch the steps.
`BASE_URL` defaults to `http://127.0.0.1:8000`.

> **Tip:** If tests fail with `Missing staticfiles manifest entry`, run
> `python manage.py collectstatic --noinput` before the test command.

Lint and format checks run from the repository root. CI runs the same commands
in its `lint` job, and the image is published only when they pass:

```bash
python -m pip install -r requirements-dev.txt
ruff check .
black --check .
```

To fix findings, run `ruff check --fix .` (unused imports, import order) and
then `black .`. Rule selection lives in `pyproject.toml`; Django migrations are
excluded from both tools.

Every pull request gets a report of how many of the lines it adds or changes are
covered by tests. CI's `ubuntu-latest` smoke-test leg runs the tests under
`coverage`, and `diff-cover` compares the result with `main`. The report goes to the
job summary and into one comment on the pull request, which each push updates. To
measure it locally, with the development stack built from your branch:

```bash
python -m pip install -r requirements-dev.txt
COVERAGE_REQUIREMENT=$(sed -n '/^coverage==/p' requirements-dev.txt)
docker compose -f docker-compose-dev.yml exec -T web python -m pip install "$COVERAGE_REQUIREMENT"
docker compose -f docker-compose-dev.yml exec -T -e RUN_BOOK_EMBEDDING_MODEL_TESTS=1 -e CELERY_TASK_ALWAYS_EAGER=True web python -m coverage run --rcfile=/app/pyproject.toml manage.py test authentication author book order events audit ai
docker compose -f docker-compose-dev.yml exec -T web python -m coverage xml --rcfile=/app/pyproject.toml -o coverage.xml
git fetch origin main
(cd library && diff-cover coverage.xml --compare-branch=origin/main)
```

The target is at least 85% of the changed lines. The report does not block a
merge, because some lines are reasonably left untested, such as code that runs only
on the Raspberry Pi: a pull request below 85% lists each uncovered line with the
reason. The settings in `pyproject.toml` leave out migrations, test files and test
helpers. A strict local delivery check can add `--fail-under=100` (required
by the `do` workflow); this does not make the advisory CI report a merge gate.

## Project layout

```text
.
├── Dockerfile                 # production image
├── docker-compose.yml         # server stack (Portainer on the Raspberry Pi), published images only
├── docker-compose-dev.yml     # local development: web, PostgreSQL, Redis and Celery
├── entrypoint.sh              # wait, migrate, seed, re-encode embeddings, start
├── requirements.txt           # runtime dependencies: image build and local development
├── requirements-dev.txt       # pinned lint, format and coverage tools
├── pyproject.toml             # ruff, black and coverage settings
├── .env.example               # safe configuration template
├── scripts/                   # model fetch, smoke, stack budget and accessibility checks
├── docs/                      # ADRs, operator guide, feature guides, changelog and debt register
├── specs/                     # feature specifications, plans and tasks
├── .specify/                  # Spec Kit templates, scripts, constitution and delivery records
├── images/                    # README images
└── library/
    ├── manage.py
    ├── seed_db.py             # demo data
    ├── gunicorn.conf.py
    ├── test_selenium_auth_*.py # browser sign-in tests, run in CI
    ├── library/               # settings, URLs, WSGI/ASGI and Celery
    ├── authentication/        # users, roles and authentication
    ├── author/                # author catalog
    ├── book/                  # catalog, local covers, embeddings, search, preferences and ratings
    ├── order/                 # loans, reservations and collection-period settings
    ├── events/                # tracking, search attribution, overview and demand forecast
    ├── audit/                 # audit trail of critical changes, read in the admin site
    └── ai/                    # read-only catalog assistant
```

Design decisions are recorded in [docs/adr/](docs/adr/README.md). The technical debt that remains,
with its owners and evidence, is in the [debt register](docs/shared/debt-register.md).

## Delivery status and plans

Snapshot checked on **2026-11-15** against `origin/main`, merged pull requests,
the implementation and the existing specifications. This branch also includes
the book-cover work in [PR #84](https://github.com/Arezzon/Library-Django/pull/84),
which was still open at this review. A branch feature or an open documentation
PR is not evidence that the deployed site has it; check the
[version endpoint](docs/features/deployment-verification.md).

| Workstream | Delivered scope and source | Status at review |
| --- | --- | --- |
| Hosting and model delivery | Raspberry Pi / Portainer, portable embedded `bge-m3`, multi-architecture images and deploy confirmation; [plan 001](specs/001-rpi-portainer-deploy/plan.md), [tasks](specs/001-rpi-portainer-deploy/tasks.md) | Completed; deployment and measurements recorded in merged PRs #26, #28 and #29 |
| Django LTS and dependencies | Django 5.2 LTS, pinned tooling, PostgreSQL 18 and Redis 8; [plan 002](specs/002-django-lts-upgrade/plan.md), [tasks](specs/002-django-lts-upgrade/tasks.md) | Completed; merged PRs #30–#32 and completion record #34 |
| Priority v1.0 debt / KAN-62 | Access control, reservations, backups, logs/audit, accessibility and administrator role; [plan 003](specs/003-priority-tech-debt/plan.md), [tasks](specs/003-priority-tech-debt/tasks.md) | Completed; KAN-62 closure recorded in merged PR #61 |
| Discovery and analytics | Semantic search, recommendations with explanations, private preferences/ratings, Ukrainian/English catalog assistant, overview and rule-based demand forecast; [BA contracts](docs/ba/README.md) and [reader walkthrough](docs/features/reader-verification.md) | Implemented in `main`; forecast and overview delivered in PRs #63–#64 |
| KAN-90 implementation fixes | POST-only logout, safe admin password handling, styled 404s, hidden staff pages, Selenium in CI and complete route-access coverage; [plan 005](specs/005-tech-debt-fixes/plan.md), [tasks](specs/005-tech-debt-fixes/tasks.md) | All four implementation groups merged in PRs #65–#68; specification record merged in #69 |
| Latest merged improvements | Mobile navigation icons (#77), configurable collection periods (#78), consistent reservation deadlines (#81), advisory coverage reporting (#80), search result metrics (#82) and search-to-click attribution (#83) | Implemented in `main`; see the [changelog](docs/shared/changelog.md) |
| Book-cover presentation | Nine local covers, neutral fallback and responsive detail header; [cover guide](docs/features/book-covers.md) | Included in this branch; PR #84 awaiting merge at review |
| Remaining-debt review / plan 004 | KAN-90 Epic and recurring review procedure in [PR #71](https://github.com/Arezzon/Library-Django/pull/71); register decisions in [PR #70](https://github.com/Arezzon/Library-Django/pull/70) | Documentation PRs still open; recurring review T039–T047 and sprint-end T051 remain unchecked in plan 004 |

### Remaining work and accepted limits

The [debt register](docs/shared/debt-register.md) on `main` records **32 closed,
3 accepted and 2 open items**. No P1 item remains open. Its two open rows are
TD-18 (the decision on keeping search text) and TD-19 (the English-only UI).
PR #70 proposes accepting the existing 200-character search history; that
register update is still pending merge. This is separate from the implemented
search metrics and click attribution. Sprint 5's plan 004 calls for its final
remaining-issue review on **2026-11-17**; a checked implementation plan does not
close that review automatically.

The interface remains in English, although semantic search and assistant
questions support Ukrainian and English. Backups are copied off the Pi manually
once a week; audit entries have no automatic retention limit; account creation
times from before the timestamp fix must not be used for historical reporting.
These are recorded decisions, not promised future features. Tailwind and fonts
still load from third-party servers as accepted for this project. Book-cover
files are bundled static assets, and user uploads are not implemented.

The specifications retain their original design context and measurements. For
current behavior, use the implementation, linked feature contracts and merged
PR evidence; for remaining work, use the register and the open review PRs.

## Deployment

### Raspberry Pi (Portainer)

The site runs on a Raspberry Pi 5 as a Portainer Business Edition Git stack
defined by [docker-compose.yml](docker-compose.yml). CI publishes
multi-architecture images to GHCR on every merge into `main` and calls the
stack webhook, so nothing is built on the Pi. The operator guide,
[docs/deployment/raspberry-pi-portainer.md](docs/deployment/raspberry-pi-portainer.md),
covers the one-time setup on the Pi, in Portainer and in GitHub. To check which
commit the server runs, see [Verify which version is deployed](docs/features/deployment-verification.md).

Both stacks include a `backup` service. Every day it takes a checked `pg_dump`
of the database into the `pgbackups` volume, apart from the database's own
volume, and keeps 7 days of backups. CI restores one into a scratch database on
every run and compares every table's row count. Once a week the operator copies
the newest backup to another machine. The operator guide covers the schedule,
the weekly copy, restores and the rehearsal, and
[ADR 0003](docs/adr/0003-database-backups.md) records the design. Backups hold
password hashes and personal data, so only the operator can read them.

### Production checklist

For any production deployment:

```text
DEBUG=False
SECRET_KEY=<long-random-secret>
ALLOWED_HOSTS=<real-hostnames>
```

Django refuses to start without `SECRET_KEY`, and `DEBUG` stays off unless it
is set to `True`. Behind an HTTPS reverse proxy, also set
`TRUST_X_FORWARDED_PROTO=True` and `CSRF_TRUSTED_ORIGINS`. Hosts that provide a single connection string can set `DATABASE_URL` instead
of the `DB_*` values.

Keep a continuously running Celery worker wherever activity analytics is
enabled. A web process alone cannot consume queued events.

## License

This project is provided as a learning / marathon exercise.
