# Library Django

![LibrarySys](/images/library-sys.png)

**Library Django** is a library management system built with **Django 4.1**,
Django REST Framework and PostgreSQL. It provides a server-rendered web UI,
role-based access, borrowing workflows, an OpenAPI API, pgvector-backed book
embeddings and asynchronous activity analytics.

> The project is ready to run with Docker Compose. A local `venv` setup is also
> supported when PostgreSQL with pgvector and Redis are available.

## Contents

| Section | Section | Section |
| --- | --- | --- |
| [Features](#features) | [Local development](#local-development-with-venv) | [Book embeddings](#book-embeddings) |
| [Architecture](#architecture) | [Demo data](#demo-data) | [Activity Analytics](#activity-analytics) |
| [Quick start with Docker](#quick-start-with-docker) | [REST API](#rest-api-and-interactive-docs) | [Configuration](#configuration) |
| [Local service requirements](#local-service-requirements) | [Tests and checks](#tests-and-checks) | [Deployment](#deployment) |
| [Project layout](#project-layout) | [License](#license) |  |

## TL;DR

### Docker

```bash
docker compose up --build
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
| Tests | Project dependencies and a test database | Node.js for JavaScript smoke tests |
| Embeddings | PostgreSQL + pgvector and Python dependencies | Network access for the first model download |

## Features

| Area | Included |
| --- | --- |
| Catalog | Books, descriptions, stock counts and authors |
| Borrowing | Create, return, reopen and reassign orders |
| Accounts | Email-based users, profiles and visitor/librarian roles |
| Administration | Django admin and librarian-only management screens |
| API | CRUD endpoints under `/api/v1/` plus Swagger and ReDoc |
| Embeddings | Multilingual 384-dimensional vectors generated with ONNX Runtime |
| Analytics | Activity dashboard, filters, daily totals and per-user activity |
| Deployment | Docker Compose and a Render Blueprint |

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
+-------+--------+       +-----------------------+       +-------------------+
        |
        v
+----------------+
| Celery worker  |
| events queue   |
+----------------+
```

The worker persists tracking events asynchronously. The web process can serve
the application without a worker, but event API requests return `503` while
the Redis broker is unavailable.

## Quick start with Docker

**Requirements:** Docker Desktop with Docker Compose.

#### Linux / macOS

```bash
cp .env.example .env
docker compose up --build
```

#### Windows PowerShell

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open <http://localhost:8000>. Compose starts:

| Service | Purpose | Port |
| --- | --- | --- |
| `web` | Django application with Gunicorn | `8000` |
| `db` | PostgreSQL 15 with pgvector | internal `5432` |
| `redis` | Celery broker with persistent AOF storage | internal `6379` |
| `worker` | Persists activity events from the `events` queue | — |

The first boot waits for PostgreSQL, applies migrations and seeds demo data
when `DJANGO_SEED=true`. Seeding is idempotent and becomes a quick no-op after
users already exist.

```bash
docker compose down       # stop the stack
docker compose down -v    # stop and delete database/Redis volumes
```

> **Tip:** `docker compose up --build -d` starts the stack in the background.
> Use `docker compose logs -f web worker` to follow application and worker logs.

## Local development with `venv`

The Django project root is `library/`; run management commands from there.

### Windows PowerShell

```powershell
cd "D:\path\to\Library-Django"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\library\requirements.txt
```

### Linux / macOS

```bash
cd /path/to/Library-Django
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r ./library/requirements.txt
```

Create `.env` in the repository root:

```dotenv
SECRET_KEY=local-development-secret-key
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

DB_ENGINE=django.db.backends.postgresql_psycopg2
DB_NAME=library_db
DB_USER=postgres
DB_PASSWORD=your-postgres-password
DB_HOST=localhost
DB_PORT=5432

CELERY_BROKER_URL=redis://localhost:6379/0
```

Then apply migrations and start Django.

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
because `book.0003_bookembedding` creates a `vector(384)` column.

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
| `reader@library.com` | `reader123password` | Visitor |
| `alice@library.com` | `alice123password` | Visitor |
| `bob@library.com` | `bob123password` | Visitor |

> **Security:** These credentials are for local/demo use only. Set a unique
> `SECRET_KEY` and replace seeded passwords before deploying.

## Book embeddings

Each book receives a multilingual embedding generated from its title and
description. The implementation uses
[intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small)
through ONNX Runtime and stores normalized 384-dimensional vectors in
PostgreSQL with pgvector.

```bash
# Docker
docker compose exec web python manage.py generate_book_embeddings

# One book, smaller batches, or a forced offline regeneration
docker compose exec web python manage.py generate_book_embeddings --book-id 1 --batch-size 8
docker compose exec web python manage.py generate_book_embeddings --force --offline
```

| Change | Result |
| --- | --- |
| New book | Embedding generated on save |
| Title/description changed | Embedding regenerated |
| Stock-only change | Current embedding reused |
| Missing/stale vector | Repaired on save or backfill |
| Inference failure | Transaction rolls back the book change |

The model revision is pinned for reproducibility. The first inference in each
process initializes the model; subsequent saves reuse the cached session.
Generation is synchronous for normal saves and asynchronous only for activity
tracking.

## Activity Analytics

Authenticated book views, catalog searches, authentication actions and order
changes are tracked as events. Librarians can open **Analytics** at
<http://localhost:8000/events/> and view:

| Dashboard | Visibility |
| --- | --- |
| Global activity, filters and recent events | Librarians |
| Selected user's activity | Librarians |
| Analytics dashboard | Not available to visitors |
| Raw tracking API | Authenticated clients with CSRF |

Client events are sent to:

```text
POST /api/v1/events/
```

The request accepts a UUID `event_id`, supported `event_type`, `book_id` and
catalog/book `path`. The same UUID can be retried safely. A successful response
is `202 Accepted`, which means the event was queued, not necessarily persisted.

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

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `extension "vector" is not available` | pgvector is not installed in the PostgreSQL server | Use the pgvector Docker image or install a PostgreSQL-compatible pgvector extension, then run `python manage.py migrate` again |
| `password authentication failed for user "postgres"` | Wrong PostgreSQL credentials | Set the actual `DB_PASSWORD` in `.env` and retry |
| `503 /api/v1/events/` | Redis/Memurai is stopped or Celery cannot reach the broker | Start the broker on port `6379`, verify it responds to `PING`, then start the Celery worker |
| Analytics page is empty | Events are queued but not consumed | Keep `celery -A library worker --queues=events` running and refresh the page |
| `Missing staticfiles manifest entry` in tests | Static files were not collected | Run `python manage.py collectstatic --noinput` from `library/` |
| `psql` is not recognized on Windows | PostgreSQL `bin` directory is not in `PATH` | Use `C:\Program Files\PostgreSQL\18\bin\psql.exe` or add that directory to `PATH` |

## REST API and interactive docs

The API is mounted under `/api/v1/`:

| Endpoint | Purpose |
| --- | --- |
| `/api/v1/user/` | User CRUD |
| `/api/v1/author/` | Author CRUD |
| `/api/v1/book/` | Book CRUD |
| `/api/v1/order/` | Order CRUD |
| `/api/v1/user/<id>/order/` | Orders for one user |
| `/api/v1/events/` | Queue an authenticated activity event |

Interactive documentation is generated by `drf-spectacular`:

```text
Swagger UI:      http://localhost:8000/api/docs/
ReDoc:           http://localhost:8000/api/redoc/
OpenAPI schema:  http://localhost:8000/api/schema/
```

## Configuration

| Variable | Local default | Purpose |
| --- | --- | --- |
| `DEBUG` | `True` | Django debug mode |
| `SECRET_KEY` | — | Session and cryptographic signing |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Accepted HTTP hosts |
| `DB_NAME` | `library_db` | PostgreSQL database |
| `DB_USER` | `postgres` | PostgreSQL user |
| `DB_PASSWORD` | — | PostgreSQL password |
| `DB_HOST` | `localhost` | PostgreSQL host; Compose uses `db` |
| `DB_PORT` | `5432` | PostgreSQL port |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Redis broker |
| `DJANGO_SEED` | `false` locally | Seed on container startup |
| `BOOK_EMBEDDING_CACHE_DIR` | `.cache/book-embeddings` | Model cache directory |

`.env` is intentionally ignored by Git. Never commit real credentials.

## Tests and checks

Run Django tests from `library/`:

```powershell
python manage.py test authentication author book order events
python manage.py collectstatic --noinput
python manage.py check
```

Docker smoke checks:

```bash
docker compose exec -T web python manage.py test authentication author book order events --verbosity 2
docker compose exec -T web python manage.py smoke_test_tracking
node --test scripts/test_tracking_js.cjs
```

> **Tip:** If tests fail with `Missing staticfiles manifest entry`, run
> `python manage.py collectstatic --noinput` before the test command.

## Project layout

```text
.
├── Dockerfile                 # production image
├── docker-compose.yml         # web, PostgreSQL, Redis and Celery
├── entrypoint.sh              # wait, migrate, seed, start
├── render.yaml                # Render Blueprint
├── requirements.txt            # canonical container dependencies
├── .env.example               # safe configuration template
├── scripts/                   # smoke and deployment checks
└── library/
    ├── manage.py
    ├── library/               # settings, URLs, WSGI/ASGI and Celery
    ├── authentication/        # users, roles and authentication
    ├── author/                # author catalog
    ├── book/                  # books and embeddings
    ├── order/                 # borrowing workflow
    └── events/                # tracking, queue tasks and analytics UI
```

## Deployment

The repository includes [render.yaml](render.yaml) for a Render Blueprint:
web service, PostgreSQL and a Redis-compatible Key Value queue. Render runs the
Docker image and wires `DB_*` and `CELERY_BROKER_URL` automatically.

For any production deployment:

```text
DEBUG=False
SECRET_KEY=<long-random-secret>
ALLOWED_HOSTS=<real-hostnames>
```

Keep a continuously running Celery worker wherever activity analytics is
enabled. A web process alone cannot consume queued events.

## License

This project is provided as a learning / marathon exercise.
