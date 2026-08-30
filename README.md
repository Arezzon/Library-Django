# Django Library - Online Marathon Project

A full-featured **Library Management System** built with **Python + Django 4.1**, a
**Django REST Framework** API, and **PostgreSQL** - packaged and ready to run in
**Docker** with a single command.

> Borrow books, manage a catalog of authors and titles, track who borrowed what,
> and run the whole thing from a clean containerized stack.

-----------------------------------------------------------------------------

## What this project is

This is a small but complete library app:

- **Web UI** (server-rendered Django templates) for browsing books, authors, and orders.
- **Role-based access** - regular *visitors* and *librarians* (librarians get the admin powers).
- **REST API** with auto-generated OpenAPI docs (Swagger / ReDoc) via `drf-spectacular`.
- **PostgreSQL** as the database, with a seeded sample dataset so you can log in and explore immediately.
- **Dockerized** - `Dockerfile` + `docker-compose.yml` bring up the web app and the DB together.

-----------------------------------------------------------------------------

## Architecture

```
+---------------------------------------------------------------------+
|                      docker-compose                                 |
|                                                                     |
|   +----------------------+        +----------------------+          |
|   |   web  (Django)      |  TCP   |   db  (PostgreSQL)    |          |
|   |   port 8000          | <----> |   postgres:15-alpine  |          |
|   |   runserver / gunicorn       |   volume: pgdata      |          |
|   +----------------------+        +----------------------+          |
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
| `ALLOWED_HOSTS`  | `localhost,127.0.0.1,0.0.0.0` | Hosts Django will serve        |
| `DB_NAME`        | `library_db`        | Database name                        |
| `DB_USER`        | `postgres`          | Database user                        |
| `DB_PASSWORD`    | `postgres`          | Database password                    |
| `DB_HOST`        | `db` (compose)      | Database host                        |
| `DB_PORT`        | `5432`              | Database port                        |
| `DJANGO_SEED`    | `true`              | Seed sample data on startup          |

-----------------------------------------------------------------------------

## How the container is built

- **`Dockerfile`** - based on `python:3.12-slim`. Installs dependencies, copies the
  repo, and uses `entrypoint.sh` as the container entrypoint.
- **`entrypoint.sh`** - waits for Postgres (via a socket probe), applies migrations,
  optionally seeds, then `exec`s the server.
- **`docker-compose.yml`** - two services: `web` (the Django app, port `8000`) and
  `db` (`postgres:15-alpine`) with a healthcheck and a persistent `pgdata` volume.
- **`.dockerignore`** - keeps `.env`, `.venv`, and caches out of the image.

> Note: the image ships **`gunicorn`** for production. The default `CMD` runs
> Django's `runserver` for convenience; switch to gunicorn for real deployments
> (see below).

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
├── .dockerignore
├── requirements.txt            # canonical deps for the image
├── .env / .env.example         # configuration (secrets NOT committed)
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

## Deploying (free options)

This is a Dockerized Django + Postgres app, so it fits any container host:

- **Render** - point at the repo, use the `Dockerfile`, add a free Postgres. Easiest.
- **Fly.io** - `fly launch` + `fly postgres` (needs card on file, not charged free).
- **Railway** - free $5/mo credit covers a small web + Postgres.
- **Oracle Cloud Always-Free** - a free ARM VM forever; `docker compose up` yourself.

> Static-only hosts (Netlify Drop, tiiny.host, neocities) and a plain localhost.run
> tunnel cannot run Django + Postgres - they're for static files or temporary local
> exposure respectively.

-----------------------------------------------------------------------------

## Production tip

For a real deployment, run gunicorn instead of runserver. From inside the image:

```bash
gunicorn library.wsgi:application --bind 0.0.0.0:8000
```

Set `DEBUG=False` and a strong `SECRET_KEY` via environment variables, and serve
static files through a reverse proxy (nginx / the platform's web server).

-----------------------------------------------------------------------------

## License

This project is provided as a learning / marathon exercise. Add a license as needed.
