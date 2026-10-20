# Contract: Server stack (`docker-compose.yml`)

**Covers**: FR-006 – FR-014, FR-021, FR-025, FR-026, US1 and US3.
**Deployed by**: Portainer Business Edition as a Git repository stack on the Pi's local Docker
environment, with no Edge agent. The file is self-contained and uses no relative path volumes,
so it also runs with plain `docker compose -f docker-compose.yml up -d` on any `linux/amd64`
or `linux/arm64` host.

## Services

| Service | Image | Restart | Depends on | Notes |
|---|---|---|---|---|
| `db` | `pgvector/pgvector:0.8.2-pg15` | `unless-stopped` | none | Volume `pgdata`; healthcheck `pg_isready` |
| `redis` | `redis:7.4-alpine` | `unless-stopped` | none | AOF with `appendfsync always` and `noeviction`; volume `redisdata`; healthcheck `redis-cli ping` |
| `web` | `${IMAGE_REPOSITORY:-ghcr.io/arezzon/library-django}:${IMAGE_TAG:-main}` | `unless-stopped` | `db` and `redis` healthy | Runs the entrypoint: migrate, checks, optional seed, re-encode, then gunicorn. Port `${WEB_PORT:-8000}:8000`. |
| `worker` | same image as `web` | `unless-stopped` | `db` and `redis` healthy | `entrypoint: ["celery"]`, `-A library worker --queues=events --concurrency=2`. It never loads the model and never re-encodes. |

The stack has no `build:` keys and no bind mounts.

**`web` healthcheck**:
- Command: `python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/version/', timeout=5)"`.
  The endpoint is described in [version-endpoint.md](version-endpoint.md).
- Timing: `interval: 30s`, `timeout: 10s`, `retries: 3`, `start_period: 15m`.

The 15-minute start period covers the first startup after a model change (SC-014); a normal
start is healthy within about a minute.

## Environment variables (set in the Portainer stack)

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `SECRET_KEY` | **yes** | none (`${SECRET_KEY:?…}`) | Django signing key |
| `DB_PASSWORD` | **yes** | none (`${DB_PASSWORD:?…}`) | PostgreSQL password; set when the volume is first created |
| `ALLOWED_HOSTS` | no | `localhost,127.0.0.1` | Comma list of public hostnames |
| `CSRF_TRUSTED_ORIGINS` | no | empty | Comma list such as `https://library.example.com`, for proxies that rewrite the host |
| `TRUST_X_FORWARDED_PROTO` | no | `False` | Set `True` only behind the operator's HTTPS proxy. Case-insensitive `true`/`false`, `1`/`0`, `yes`/`no`, `on`/`off`; any other value stops startup |
| `WEB_PORT` | no | `8000` | Host port for `web` |
| `IMAGE_REPOSITORY` | no | `ghcr.io/arezzon/library-django` | Override for forks |
| `IMAGE_TAG` | no | `main` | `main` follows the latest build; `sha-<short>` or `<semver>` pins one |
| `DJANGO_SEED` | no | `false` | `true` loads demo data, whose passwords are public; see the guide's warning |
| `DEBUG` | no | `False` | Must stay `False` on the server |
| `DB_NAME` / `DB_USER` | no | `library_db` / `postgres` | Database identity |
| `WEB_CONCURRENCY` | no | `3` | Gunicorn workers; each holds one model copy of about 0.6 GB |
| `BOOK_EMBEDDING_THREADS` | no | `2` | ONNX Runtime threads per worker |

The `BOOK_EMBEDDING_*` model-identity variables MUST NOT be set here. The image already contains
its model, and the stack does not pass these variables to its containers, so a Portainer value
has no effect. If a different value does reach `web` (for example through an edited Compose
file), `web` stops with `book.E001`, as described in
[embedding-model-setting.md](embedding-model-setting.md).

## Behavior guarantees

- **Missing secret**: Compose refuses to deploy and names the variable (US1-2).
- **Redeploy or reboot**: `pgdata` and `redisdata` persist, and every service restarts on its
  own (FR-009, FR-010).
- **Pull failure**: the previous containers keep running (edge case).
- **New version fails to start**: `web` turns *unhealthy* after `start_period` plus 3 failed
  checks, and the operator pins `IMAGE_TAG` to roll back (US3-3, US3-4). Migrations already
  applied are not reverted.
- **Seeding**: idempotent, since `seed_db.py` exits early when users exist.

## Portainer configuration (expected by the operator guide)

| Setting | Value |
|---|---|
| Build method | Repository |
| Repository URL | `https://github.com/Arezzon/Library-Django` (public, no credentials) |
| Repository reference | `refs/heads/main` |
| Compose path | `docker-compose.yml` |
| GitOps updates | On; mechanism **Webhook** |
| Re-pull image | On |
| Force redeployment | On (so a webhook redeploys even when Git is unchanged, for example on tag runs) |
| Relative path volumes | Not needed |
| Environment variables | As in the table above |
