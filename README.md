# Library Django

![LibrarySys](/images/library-sys.png)

**Library Django** is a library management system built with **Django 5.2 LTS**,
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
| Tests | Project dependencies and a test database | Node.js for JavaScript smoke tests |
| Embeddings | PostgreSQL + pgvector and Python dependencies | Network access once, to fetch the model (`venv` only; images ship with it) |

## Features

| Area | Included |
| --- | --- |
| Catalog | Books, descriptions, stock counts and authors |
| Borrowing | Librarians lend at the desk; return, reopen and reassign orders. Every loan starts with a librarian, and none while the reader has an overdue loan |
| Reservations | A reader reserves an available book for 48 hours, active at once; the copy stays held until it is collected or the deadline passes. At most 3 at a time, and none while a loan is overdue. My reservations shows each deadline with the time left and what to do next. Librarians issue reserved books at the desk in one step, or cancel with a reason that they confirm and the reader sees; readers cancel their own. When 100 readers reserve the last copy at once, exactly one gets it ([guide](docs/features/reservations.md)) |
| Accounts | Email-based users, profiles and visitor/librarian roles; sign-up always creates a visitor, and only librarians change roles and account status |
| Administration | Django admin and librarian-only management screens |
| API | Endpoints under `/api/v1/`, each open only to its stated audience, plus Swagger and ReDoc |
| Embeddings | Multilingual 1024-dimensional `bge-m3` vectors generated with ONNX Runtime |
| Analytics | Activity dashboard, filters, daily totals and per-user activity |
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

The worker persists tracking events asynchronously. The web process can serve
the application without a worker, but event API requests return `503` while
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
| `worker` | Persists activity events from the `events` queue | — |

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
| `reader@library.com` | `reader123password` | Visitor |
| `alice@library.com` | `alice123password` | Visitor |
| `bob@library.com` | `bob123password` | Visitor |

> **Security:** These credentials are for local/demo use only. Set a unique
> `SECRET_KEY` and replace seeded passwords before deploying.

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
| `/api/v1/books/recommendations/?limit=10` | Available books ranked for the current account; [algorithm](docs/ba/recommendations.md) / [data contract](docs/ba/recommendation-data.md) | Signed-in accounts, own signals only |
| `/api/v1/book/` | Books | Signed-in accounts read; librarians create, change and delete |
| `/api/v1/author/` | Authors | Signed-in accounts read; librarians create, change and delete |
| `/api/v1/user/` | Accounts | Librarians list, create, change and delete; a visitor reads and renames only their own account |
| `/api/v1/order/` | Orders (loans) | Librarians start, read and change every order; a visitor reads their own |
| `/api/v1/user/<id>/order/` | Orders for one user | That user or a librarian reads; only librarians start, change or delete |
| `/api/v1/reservation/` | Reservations | Signed-in accounts reserve for themselves, and read and cancel their own; librarians read every reservation, issue it (`<id>/issue/`) or cancel it with a reason (`<id>/cancel/`) |
| `/api/v1/events/` | Queue an activity event | Signed-in accounts |

A request that is not signed in gets `401` with `WWW-Authenticate: Session`. A signed-in
account without the right role gets `403`, and so does a visitor who sends `role`,
`is_active`, `email` or `password` for their own account. A visitor who asks for another
user's record gets `404`, the same answer as for a record that does not exist. Deleting an
author who is attached to a book, or a book that has loans or reservations, gets `409`, and
nothing changes; the web pages and the admin site refuse it too. A reservation, an issue or
a loan that a rule refuses gets `409` with a `code` and a message that says what to do next;
the [reservations guide](docs/features/reservations.md#through-the-api) lists the codes.
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
| `DJANGO_SEED` | `false` locally | Seed on container startup |
| `BOOK_EMBEDDING_CACHE_DIR` | `.cache/book-embeddings` | Model cache directory |
| `BACKUP_HOUR` | `1` | UTC hour at or after which the `backup` service takes each day's backup |
| `BACKUP_KEEP_DAYS` | `7` | Days backups are kept; the 7 newest always stay |

`.env` is ignored by Git and Docker builds, so local secrets reach neither
commits nor images. `.env.example` holds placeholders only; never commit real
credentials.

## Tests and checks

Run Django tests from `library/`:

```powershell
python manage.py test authentication author book order events audit
python manage.py collectstatic --noinput
python manage.py check
```

Docker smoke checks:

```bash
docker compose -f docker-compose-dev.yml exec -T web python manage.py test authentication author book order events audit --verbosity 2
docker compose -f docker-compose-dev.yml exec -T web python manage.py smoke_test_tracking
docker compose -f docker-compose-dev.yml exec -T backup library-backup once
node --test scripts/test_tracking_js.cjs
```

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
DC="docker compose -f docker-compose-dev.yml"
$DC exec -T web sh -c "pip install -q $(grep '^coverage==' requirements-dev.txt) \
  && coverage run --rcfile=/app/pyproject.toml manage.py test authentication author book order events audit \
  && coverage xml --rcfile=/app/pyproject.toml -o coverage.xml"
git fetch origin main
(cd library && diff-cover coverage.xml --compare-branch=origin/main)
```

The target is at least 85% of the changed lines. The report does not block a
merge, because some lines are reasonably left untested, such as code that runs only
on the Raspberry Pi: a pull request below 85% lists each uncovered line with the
reason. The settings in `pyproject.toml` leave out migrations, test files and test
helpers.

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
├── scripts/                   # model fetch, smoke and stack budget checks
└── library/
    ├── manage.py
    ├── library/               # settings, URLs, WSGI/ASGI and Celery
    ├── authentication/        # users, roles and authentication
    ├── author/                # author catalog
    ├── book/                  # books and embeddings
    ├── order/                 # borrowing workflow
    ├── events/                # tracking, queue tasks and analytics UI
    └── audit/                 # audit trail of critical changes, read in the admin site
```

## Deployment

### Raspberry Pi (Portainer)

The site runs on a Raspberry Pi 5 as a Portainer Business Edition Git stack
defined by [docker-compose.yml](docker-compose.yml). CI publishes
multi-architecture images to GHCR on every merge into `main` and calls the
stack webhook, so nothing is built on the Pi. The operator guide,
[docs/deployment/raspberry-pi-portainer.md](docs/deployment/raspberry-pi-portainer.md),
covers the one-time setup on the Pi, in Portainer and in GitHub.

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
