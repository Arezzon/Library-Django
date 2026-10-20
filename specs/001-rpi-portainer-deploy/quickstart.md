# Quickstart: validating the feature

**Feature**: [spec.md](spec.md) | **Contracts**: [contracts/](contracts/)

These scenarios prove the feature end to end. Sections 1–4 run on a developer machine and in CI.
Sections 5–8 run on the Raspberry Pi by the operator, following
`docs/deployment/raspberry-pi-portainer.md`.

## Prerequisites

- **Developer**: Docker with Compose v2, and Python 3.12 for the scripts. A `.env` copied from
  `.env.example`, with `SECRET_KEY` and `DB_PASSWORD` set.
- **Operator**:
  - Raspberry Pi 5 (8 GB) with a 64-bit OS, Docker Engine and Portainer BE, and Portainer
    reachable over HTTPS with a trusted certificate.
  - Repository admin access, or someone who has it, to create the `production` environment and
    its secret.

## 1. Local development stack (FR-025, US5)

```bash
docker compose -f docker-compose-dev.yml up --build -d --wait
docker compose -f docker-compose-dev.yml exec -T web python manage.py migrate --check
curl -fsS "http://localhost:8000/api/v1/books/search/?q=тоталітарний%20нагляд" | head -c 300
```

**Expected**:
- The stack is healthy.
- The search returns *1984* first.
- `docker compose -f docker-compose-dev.yml exec web python -c "from book.embedding_config import resolve; print(resolve())"`
  shows the `Xenova/bge-m3` spec with 1024 dimensions.

## 2. Single model setting (FR-030, FR-031, edge case)

```bash
grep -n "bge-m3\|model_int8\|e5-small" Dockerfile docker-compose*.yml library/book/*.py scripts/*.py
python scripts/fetch_embedding_model.py --print
```

**Expected**:
- The only match in code or build files is `library/book/embedding_config.py`.
- `--print` outputs the spec and its 40-hex tag.

**Mismatch check**: start `web` with a runtime override that differs from the image. Compose
passes only the variables listed under `environment:`, so give the override to the container
directly:

```bash
docker compose -f docker-compose-dev.yml run --rm --no-deps \
  -e BOOK_EMBEDDING_MODEL_REVISION=0000000000000000000000000000000000000000 web
```

**Expected**: `web` exits during `migrate` with `book.E001`, naming both revisions.

## 3. Startup re-encoding (FR-034, SC-014)

Start from a database whose vectors were written by the old model, for example an existing
`pgdata` volume from before this feature. Then run:

```bash
docker compose -f docker-compose-dev.yml up -d --wait
docker compose -f docker-compose-dev.yml exec -T web python manage.py shell -c \
 "from book.models import Book, BookEmbedding; from book.embedding_config import resolve; \
  t=resolve().tag; print(Book.objects.count(), BookEmbedding.objects.filter(model_revision=t).count())"
```

**Expected**:
- Both counts are equal.
- The web log shows `Generated: N` on this start and `Generated: 0` on the next restart.

## 4. CI gates (FR-001 – FR-004, FR-032)

- **Open a pull request to `main`**: `lint` and both `smoke-test` legs (amd64 and arm64) run, and
  no `publish`, `merge`, `promote` or `deploy` job runs.
- **Merge it**: `publish` (×2), then `merge`, `promote` and `deploy` run. Then check the image:

  ```bash
  docker buildx imagetools inspect ghcr.io/arezzon/library-django:main
  ```

  **Expected**: the manifest list contains `linux/amd64` and `linux/arm64`, and a `sha-<short>`
  tag exists. There is no `latest`.
- **Push a tag `v0.0.0-test`**: the `0.0.0-test` image is published, `main` doesn't move, and
  `deploy` runs.
- **Forward-only `main`** (FR-002, FR-019): merge two pull requests quickly, one after the other.
  Re-run the older commit's `promote` job after the newer one has finished. **Expected**: it
  leaves `main` alone (the older build keeps only `sha-<short>`), emits the "newer commit
  already moved `main`" notice, and skips `deploy`.
- **Secret scope** (FR-016): in a pull-request run, the `deploy` job doesn't exist, and the
  `production` environment shows no deployment for it.
- **Webhook visibility** (US3):
  - With no `PORTAINER_WEBHOOK_URL` secret, `deploy` is green with a warning.
  - With a wrong URL, `deploy` is red with "published, but the server was not redeployed", and
    no URL appears in the log.
- **Version endpoint** (FR-035):

  ```bash
  curl -fsS http://localhost:8000/api/v1/version/
  ```

  **Expected**: `{"commit":"unknown"}` on a local build, or the commit SHA on a CI build.

## 5. First deployment on the Pi (US1, SC-002, SC-003, SC-007)

Follow the guide: create the Portainer Git stack (`docker-compose.yml`), set `SECRET_KEY`,
`DB_PASSWORD`, `ALLOWED_HOSTS` and optionally `DJANGO_SEED=true`, then deploy.

**Expected**:
- Portainer shows four running containers, with `web` *healthy*.
- The image was pulled, not built: `docker image inspect ghcr.io/arezzon/library-django:main
  --format '{{.Architecture}}'` prints `arm64`.
- `/`, `/api/docs/`, `/api/schema/` and a semantic search all answer.

**Budget and latency on the Pi** (R1, R8, SC-010 – SC-012): this needs a repository checkout and
`python3` on the Pi.

```bash
python3 scripts/smoke_stack_budget.py --project-name <stack name> --base-url http://localhost:8000 \
  --max-memory-gib 4 --max-search-p95-ms 500 --max-save-ms 2000
```

**Expected**: PASS. Record the reported peak memory and latencies, with `WEB_CONCURRENCY` and
`BOOK_EMBEDDING_THREADS`, in [research.md](research.md) §R1. This step is the completion gate
from FR-028. If it fails, follow the tuning steps in [research.md](research.md) §R14 and re-run.
If latency still misses, the measured values become the relaxed targets, with the user's
sign-off.

## 6. Automatic redeploy (US2, SC-001, SC-009, FR-036)

1. A repository admin creates the `production` environment, limited to `main` and `v*` tags.
2. In that environment, they add the secret `PORTAINER_WEBHOOK_URL` and, if the site is public,
   the variable `SITE_URL`.
3. Merge a visible text change into `main`.

**Expected**:
- The change is live on the Pi within 30 minutes, without anyone touching the Pi.
- The web downtime during the swap is under 2 minutes.
- The `deploy` job ends with "Redeploy confirmed: the site runs <commit>". Without `SITE_URL`,
  it ends with a notice that confirmation was skipped.
- `curl -fsS $SITE_URL/api/v1/version/` reports the merged commit.

## 7. Rollback and resume (US3, SC-005)

1. In Portainer, set `IMAGE_TAG=sha-<earlier short sha>` and redeploy.
2. Check that the site runs that build: `/api/v1/version/` reports the earlier commit, and the
   change from §6 is gone.
3. While the stack is pinned, merge any change. **Expected**: if `SITE_URL` is set, the `deploy`
   confirmation fails after 15 minutes with "may be pinned". The Pi stays on the pinned build.
4. Remove `IMAGE_TAG` and redeploy.

**Expected**:
- The rollback takes under 5 minutes.
- The site returns to the newest `main` build.

**Rolling back past this feature** (x86-64 hosts only; R15): images built before this feature
have no ARM64 variant. After pinning such an image, run:

```bash
docker exec <web container> python manage.py generate_book_embeddings
```

**Expected**: search returns results again with the older model. Rolling forward re-encodes
automatically.

## 8. Persistence and Render retirement (SC-004, US4)

- **Persistence**: create a book and an order, then redeploy three times and reboot the Pi.
  **Expected**: the data is intact, and events queued before the reboot have been processed.
- **Render retirement**:

  ```bash
  git grep -n -i "onrender\|render\.yaml\|render_start\|smoke_render_free" -- . ':!specs' ':!docs/shared/changelog.md'
  ```

  **Expected**: no matches.
- **Shut down Render**: follow the guide's section on suspending and deleting the Render web
  service, its key-value store and its database. **Expected**: Render no longer deploys from
  `main`.
