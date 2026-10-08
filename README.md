# Django Library - Online Marathon Project

![Logo](/images/library-sys.png)

A full-featured **Library Management System** built with **Python + Django 4.1**, a
**Django REST Framework** API, and **PostgreSQL** - packaged and ready to run in
**Docker** with a single command.

> Borrow books, manage a catalog of authors and titles, track who borrowed what,
> and run the whole thing from a clean containerized stack.

-----------------------------------------------------------------------------

## What this project is

This is a small but complete library app:

- **Web UI** (server-rendered Django templates) using Tailwind for browsing books, authors, and orders.
- **Role-based access** - regular *visitors* and *librarians* (librarians get the admin powers).
- **REST API** with auto-generated OpenAPI docs (Swagger / ReDoc) via `drf-spectacular`.
- **PostgreSQL** as the database, with a seeded sample dataset so you can log in and explore immediately.
- **Dockerized** - `Dockerfile` + `docker-compose.yml` bring up the web app and the DB together.

-----------------------------------------------------------------------------

## Architecture

```
+---------------------------------------------------------------------+
|                            docker-compose                           |
|                                                                     |
|      +----------------------+         +----------------------+      |
|      | web  (Django)        |   TCP   | db  (PostgreSQL)     |      |
|      | port 8000            | <-----> | Postgres + pgvector  |      |
|      | gunicorn (3 workers) |         | volume: pgdata       |      |
|      +----------------------+         +----------------------+      |
+---------------------------------------------------------------------+
```

**Django apps (`library/`):**

| App             | Responsibility                                                        |
|-----------------|----------------------------------------------------------------------|
| `authentication`| Custom email-based user model, login/register, profiles, roles        |
| `author`        | Author catalog (name / surname / patronymic) + M2M to books           |
| `book`          | Book catalog (name, description, stock count) + authors               |
| `order`         | Borrowing orders: who borrowed which book, due date, return date      |

**Data model at a glance:**

- `CustomUser` (email login, `role`: visitor=0 / librarian=1) - librarians get staff/superuser rights.
- `Author` - `name`, `surname`, `patronymic`; many-to-many with `Book`.
- `Book` - `name`, `description`, `count` (total copies); `available_count` = copies minus active orders.
- `Order` - `user` + `book` + `created_at`, `plated_end_at` (planned return), `end_at` (actual return, `null` while borrowed). One active copy per single-copy book.

**Access control decorators** (`authentication/decorators.py`):
- `librarian_required` - staff-only views (user list, all orders, order edits/closing).
- `librarian_or_owner_required` - a user may edit/see their own profile.
- `role_required(*roles)` - generic role gate.

-----------------------------------------------------------------------------

## Quick start (Docker - recommended)

> Requires **Docker** and **Docker Compose**. Everything runs locally on `http://localhost:8000`.

```bash
# 1. (optional) provide your own secrets - copy and edit
cp .env.example .env

# 2. Build the image and start web + db
docker compose up --build

# 3. Open the app
#    http://localhost:8000
```

That's it. On first launch the entrypoint:
1. waits for PostgreSQL to become ready,
2. runs `migrate`,
3. **seeds** sample data (users, authors, books, orders) when `DJANGO_SEED=true`.
   The seed is a **fast no-op if any user already exists** (e.g. on redeploys),
   so warm boots stay quick.

### Stop / reset

```bash
docker compose down            # stop containers
docker compose down -v         # also wipe the database volume (fresh start)
```

### Useful env vars (set in `.env` or `docker-compose.yml`)

| Variable         | Default             | Purpose                              |
|------------------|---------------------|--------------------------------------|
| `DEBUG`          | `False`             | Django debug mode                    |
| `SECRET_KEY`     | `change-me-in-prod` | Session/cookie signing key           |
| `ALLOWED_HOSTS`  | `localhost,127.0.0.1` | Hosts Django serves; `.onrender.com` is always allowed too |
| `DB_NAME`        | `library_db`        | Database name                        |
| `DB_USER`        | `postgres`          | Database user                        |
| `DB_PASSWORD`    | `postgres`          | Database password                    |
| `DB_HOST`        | `db` (compose)      | Database host                        |
| `DB_PORT`        | `5432`              | Database port                        |
| `DJANGO_SEED`    | `true`              | Seed sample data on startup (skips if users exist) |

-----------------------------------------------------------------------------

## How the container is built

- **`Dockerfile`** - based on `python:3.12-slim`. Installs dependencies, copies the
  repo, runs `collectstatic` at build time, and uses `entrypoint.sh` as the entrypoint.
- **`entrypoint.sh`** - waits for Postgres (via a socket probe), applies migrations,
  optionally seeds, then launches the server. It also honors the platform's `$PORT`
  (e.g. Render injects it) by binding gunicorn to `0.0.0.0:$PORT` (default 8000).
- **`docker-compose.yml`** - two services: `web` (the Django app, port `8000`) and
  `db` (`pgvector/pgvector:0.8.2-pg15`) with a healthcheck and a persistent `pgdata` volume.
- **`.dockerignore`** - keeps `.env`, `.venv`, `staticfiles/`, and caches out of the image.

> The image runs **`gunicorn`** in production by default (3 workers, `library.wsgi:application`),
> not Django's `runserver`. Static files (Django admin CSS/JS) are served by **WhiteNoise**
> with `CompressedManifestStaticFilesStorage`, so the app works correctly with `DEBUG=False`.
> `ALLOWED_HOSTS` always includes `.onrender.com` (and `localhost`/`127.0.0.1`), so a
> missing/wrong host env value can't cause HTTP 400s on deploy.

### Files

| File                  | Purpose                                                        |
|-----------------------|----------------------------------------------------------------|
| `Dockerfile`          | Python 3.12-slim image; collectstatic; gunicorn CMD           |
| `entrypoint.sh`       | wait-for-DB, migrate, seed, honor `$PORT`                     |
| `docker-compose.yml`  | local `web` + `db` stack                                       |
| `render.yaml`         | one-click Render Blueprint (web + free Postgres)              |
| `.github/workflows/`  | GitHub Actions: compose smoke test + GHCR push                |
| `.dockerignore`       | keeps secrets/caches out of the image                         |

-----------------------------------------------------------------------------

## Running without Docker (local dev)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Point settings at a local Postgres via .env, then:
python manage.py migrate
python manage.py runserver          # http://localhost:8000
```

Seed sample data any time with:

```bash
cd library && python seed_db.py
```

-----------------------------------------------------------------------------

## Book embeddings (KAN-27)

Generate multilingual document embeddings from book titles and descriptions:

```bash
docker compose exec web python manage.py generate_book_embeddings
# Restrict a run, regenerate, or use an already cached model:
docker compose exec web python manage.py generate_book_embeddings --book-id 1 --batch-size 8
docker compose exec web python manage.py generate_book_embeddings --force --offline
```

The model is [intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small),
pinned to revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`. It runs on CPU through
ONNX Runtime using the pinned int8 artifact and produces normalized 384-dimensional vectors. Document input is
`passage: <title>\n<description>`; future search queries must use the same model with
the `query: ` prefix. No paid API or API key is required. Docker builds download the model files into the image; runtime inference works offline.
The int8 artifact has its own revision identity so older fp32 vectors are regenerated.
Every new book automatically receives an embedding when saved. A missing or blank
description uses the title alone.
Changing the title or description regenerates it; changing stock counts or saving
unchanged text does not when its vector is current. Clearing a description
regenerates the vector from the title. Every save also repairs missing vectors,
stale input hashes and outdated model names/revisions. This applies
to normal ORM saves, web forms, the API and the admin, including admin text edits.
Generation is synchronous: the save succeeds only after the vector is stored.
If inference fails, the transaction rolls back both book changes and the vector;
web/API/admin report the failure. The model initializes lazily and is cached per
process. The first text save initializes the model; later saves reuse the in-process session.

Migration `book.0003` enables the PostgreSQL `vector` extension and creates a
separate `BookEmbedding` table (`vector(384)`, model/revision, input SHA-256 and timestamp).
Compose uses `pgvector/pgvector:0.8.2-pg15`, retaining PostgreSQL major version 15.
For an externally hosted database, ensure pgvector is installed and the migration
user can enable the extension, or have an administrator enable it beforehand.
SQLite is not supported by this command. Apply migrations before running it.

The management command remains available for legacy books and forced regeneration
(including model revision changes). Book.objects.bulk_create is rejected; create
books through create() or save(). QuerySet.update and bulk_update reject name or
description changes, while stock-only updates remain supported. Raw SQL and
Django raw fixture loading bypass model hooks and require backfilling.
Unchanged inputs/model revisions are skipped; title-only books are included. Command inference runs in batches outside database locks;
a vector is saved only if the
book text still matches the captured input. If text changes during inference,
the command reports it and a subsequent run processes the new text. Successfully
completed batches remain saved if a later batch fails. Normal book saves generate
and persist under the book row lock to keep the text/vector pair atomic. This
ticket does not add a search endpoint or a scheduled generation job. Semantic
search should validate the input hash and model metadata of imported vectors.

Docker CI enables `RUN_BOOK_EMBEDDING_MODEL_TESTS=1` to test real Ukrainian/English
inference and a pgvector cosine-distance query in addition to offline regression
tests for idempotency, batching, invalid outputs and concurrent text edits.

## REST API

The API lives under **`/api/v1/`** and is powered by Django REST Framework ViewSets.

| Endpoint                          | Methods            | Description                          |
|-----------------------------------|--------------------|--------------------------------------|
| `/api/v1/user/`                   | GET, POST, ...     | Users (CRUD)                         |
| `/api/v1/author/`                 | GET, POST, ...     | Authors (CRUD)                       |
| `/api/v1/book/`                   | GET, POST, ...     | Books (CRUD)                         |
| `/api/v1/order/`                  | GET, POST, ...     | Orders (CRUD)                        |
| `/api/v1/user/<id>/order/`        | GET, POST          | Orders scoped to a specific user     |
| `/api/v1/user/<id>/order/<pk>/`   | GET, PUT, PATCH, DELETE | Single user order               |

### Interactive docs

- **Swagger UI:** `http://localhost:8000/api/docs/`
- **ReDoc:** `http://localhost:8000/api/redoc/`
- **OpenAPI schema (JSON):** `http://localhost:8000/api/schema/`

Generated automatically with `drf-spectacular` - no manual docs to keep in sync.

-----------------------------------------------------------------------------

## Seeded demo accounts

After the first container start you can log in with:

| Email                  | Password             | Role       |
|------------------------|----------------------|------------|
| `librarian@library.com`| `admin123password`   | Librarian  |
| `reader@library.com`   | `reader123password`  | Visitor    |
| `alice@library.com`    | `alice123password`   | Visitor    |
| `bob@library.com`      | `bob123password`     | Visitor    |

The seed also creates 8 authors (Shevchenko, Franko, Orwell, ...), 9 books, and a few
sample borrow orders so the UI and API have something to show immediately.

-----------------------------------------------------------------------------

## Project layout

```
.
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
├── render.yaml                 # Render Blueprint (one-click deploy)
├── .dockerignore
├── requirements.txt            # canonical deps for the image
├── .env / .env.example         # configuration (secrets NOT committed)
├── .github/workflows/          # CI: docker compose smoke test + GHCR push
└── library/                    # Django project root
    ├── manage.py
    ├── requirements.txt        # dev deps mirror
    ├── seed_db.py              # sample-data seeder
    ├── library/                # settings, urls, wsgi, asgi, api router
    ├── authentication/         # users, auth views, decorators
    ├── author/                 # authors app
    ├── book/                   # books app
    └── order/                  # borrowing orders app
```

-----------------------------------------------------------------------------

## Deploying

This is a Dockerized Django + Postgres app, so it fits any container host:

- **Render** - the repo ships a `render.yaml` Blueprint: one-click deploy (web + free Postgres).
- **Fly.io** - `fly launch` + `fly postgres` (needs card on file, not charged free).
- **Railway** - free $5/mo credit covers a small web + Postgres.
- **Oracle Cloud Always-Free** - a free ARM VM forever; `docker compose up` yourself.

> Static-only hosts (Netlify Drop, tiiny.host, neocities) and a plain localhost.run
> tunnel cannot run Django + Postgres - they're for static files or temporary local
> exposure respectively.

### Deploy to Render (free, one-click)

1. Push this repo to GitHub.
2. In Render: **New** -> **Blueprint** -> connect the repo. The `render.yaml` creates:
   - a **web** service (Docker, free) running gunicorn, and
   - a **free PostgreSQL** database, with `DB_*` env vars auto-wired to it.
3. Render builds the image, migrates, and seeds on first boot. Open the assigned
   `https://<app>.onrender.com` URL and log in with a seeded account (below).

Health-check tip (free tier): the Blueprint keeps `healthCheckPath: /api/schema/`.
The free Postgres is slow to cold-start (migrate + seed can take minutes), so in the
Render dashboard raise the **Health Check Timeout** (e.g. 200-300s). The seed is a
no-op once users exist, so subsequent restarts boot in seconds.

Known gotcha: Django 4.1 does **not** treat `*` as a host wildcard - only a leading
dot (`.onrender.com`) matches subdomains. The settings already include `.onrender.com`,
which is why the health check passes; don't set `ALLOWED_HOSTS=*.onrender.com`.

-----------------------------------------------------------------------------

## Production notes

- **Server:** the image runs `gunicorn library.wsgi:application` (3 workers). The
  entrypoint binds to `$PORT` (Render injects it; defaults to 8000), so no change is
  needed per platform.
- **Static files:** served by **WhiteNoise** with `CompressedManifestStaticFilesStorage`
  (collectstatic runs at image build). Works correctly with `DEBUG=False`.
- **Settings:** set `DEBUG=False` and a strong `SECRET_KEY` via environment. `ALLOWED_HOSTS`
  always allows `.onrender.com`, `localhost`, and `127.0.0.1`.

-----------------------------------------------------------------------------

## License

This project is provided as a learning / marathon exercise.

With `DJANGO_SEED=true`, startup runs the idempotent embedding backfill even when existing users cause sample-data creation to be skipped. Current vectors are preserved; generation failure stops startup for retry.

## User event tracking (KAN-30)

Run `docker compose up --build -d` to start the web app, PostgreSQL, Redis and the
Celery worker. Redis uses an AOF volume with synchronous fsync; no Redis port is
published. Worker events are acknowledged after persistence and retried with
backoff on database failures. UUID-based inserts are idempotent.

Authenticated book views and catalog searches are captured by middleware. Login
and logout use auth signals. Order creation, returns, reopening and reassignment
use model signals and publish only after transaction commit. The actor and the
reader are distinct: librarian actions include `reader_id` in their properties.
Failed actions, anonymous requests, seed data, analytics pages and tracking API
requests are not counted as successful business events. Bulk/raw order writes
bypass signals and are outside the tracked application paths.

`POST /api/v1/events/` accepts JSON with `event_id` (UUID), `event_type`
(`book_click` or `borrow_intent`), `book_id` and `path` (catalog or book detail).
It requires authentication and session CSRF, derives identity from the session,
and rejects unknown fields and server-only event types. HTTP 202 means queued,
not yet stored; a stopped worker can consume the queue after it restarts.
The endpoint returns retryable HTTP 503 if the broker is unavailable. Server
tracking logs enqueue failures without breaking the business action; it is
best effort during broker outages, and has no database outbox fallback.

Catalog/book-page links send explicit client events with a CSRF token. The
browser retains at most 50 pending events per user in sessionStorage, retries
the same UUID after navigation/network recovery and expires saved entries after
24 hours. It never reads passwords, arbitrary form inputs, cookies or full URLs.
Search text is explicitly retained (up to 200 characters) for analytics.

Librarians see **Analytics** in navigation at `/events/`: period/action filters,
counts, daily activity, action distribution, popular books and paginated recent
activity. The same analytics are scoped to the selected user on
`/authentication/users/<id>/`, visible only to librarians; profile filters and
pagination stay on that profile. Readers cannot access analytics. Empty states and deleted
users/books are supported. Event data is not yet used to rank recommendations.
No external analytics provider or data export is configured.

Local verification (run on a disposable stack):

```bash
docker compose exec -T -e RUN_BOOK_EMBEDDING_MODEL_TESTS=1 -e CELERY_TASK_ALWAYS_EAGER=True web python manage.py test authentication author book order events --verbosity 2
node --test scripts/test_tracking_js.cjs
docker compose exec -T web python manage.py smoke_test_tracking
python3 scripts/smoke_tracking_recovery.py
```

The unit-test process enables eager tasks to keep existing suites in their own
test database; event tests mock publishing to verify async enqueue boundaries.
The HTTP smoke command uses a real Redis broker and separate worker, creates
its own test user/book, exercises the UI/API workflow, then cleans them up.
Both checks run in Docker Build / smoke-test on pull requests. Deployment
outside Compose also needs `CELERY_BROKER_URL` and a continuously running
`celery -A library worker --queues=events` process; a web process alone cannot
persist queued events. The existing Render blueprint does not provision these
additional services.
