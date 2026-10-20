# Implementation Plan: Django 5.2 LTS Upgrade and Dependency Refresh

**Branch**: `chore/kan-17-django-5.2-lts` (PR 1; PR 2 and PR 3 get their own branches, see
[research.md](research.md) R15) | **Date**: 2026-10-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-django-lts-upgrade/spec.md`

## Summary

The work ships as three pull requests, merged in this order (FR-025).

**PR 1: runtime dependencies (KAN-17).**
- Move to Django **5.2.18** and every other runtime package to its latest release. Only redis-py
  stays below its latest, at 6.4.0, because kombu caps it (R1).
- Pin the complete resolved set in the root `requirements.txt` and delete
  `library/requirements.txt` (R2).
- Django 5.1 removed `STATICFILES_STORAGE`, which would silently switch off WhiteNoise's
  compressed, hashed static files, so it is replaced by `STORAGES`. `USE_L10N` is deleted (R3).
- Two migrations that predate the upgrade and have never been generated ship now: the `role`
  choice label and `order.id` as `BigAutoField` (R4).
- New tests guard each of these. The OpenAPI schema is compared with `main` to prove the API is
  unchanged (R5).
- Remaining third-party deprecation warnings are listed in `deprecations.md` (R10).
- Carries the constitution v2.1.0 amendment.

**PR 2: lint and format tools.** black 26.10.1 and ruff 0.17.1. Measured today, they need no
reformatting and report no findings, so this PR is the two pins (R11).

**PR 3: database and broker images.** `pgvector/pgvector:0.8.7-pg18` and `redis:8.10.2-alpine`
in both Compose files.
- New volumes, `pgdata18` mounted at `/var/lib/postgresql` and `redisdata8`, make the redeploy
  start from an empty database and queue on its own. The old volumes are kept as the rollback
  path (R12, R13).
- The operator guide gains the one-time check, reseed and cleanup steps (R14).
- Amends the constitution to v2.2.0.

## Technical Context

**Language/Version**: Python 3.12 (Django 4.1 → 5.2.18); POSIX `sh` entrypoint; Compose YAML.

**Primary Dependencies**:
- PR 1:
  - Django 5.2.18, DRF 3.18.3, drf-spectacular 0.30.0, psycopg2-binary 2.9.13.
  - gunicorn 26.2.0, whitenoise 6.12.0, pgvector 0.5.1, celery[redis] 5.6.3 with kombu 5.6.2
    and redis 6.4.0.
  - onnxruntime 1.31.0, numpy 2.5.4, sentencepiece 0.2.2, huggingface-hub 2.2.0,
    python-dotenv 1.2.4.
  - The full pinned set is in R1 and R2.
- PR 2: black 26.10.1 and ruff 0.17.1.
- PR 3: `pgvector/pgvector:0.8.7-pg18` and `redis:8.10.2-alpine`.

**Storage**:
- PostgreSQL 15 with pgvector until PR 3, then PostgreSQL 18 with pgvector 0.8.7.
- PR 1 adds two migrations: `authentication/0003` (state only) and `order/0003` (`id` to
  `bigint`).
- PR 3 moves the data to new named volumes `pgdata18` and `redisdata8`
  ([data-model.md](data-model.md)).

**Testing**:
- The Django test runner on PostgreSQL in `docker-compose-dev.yml`, mocked by default. Real-model
  tests and the evaluation set run with `RUN_BOOK_EMBEDDING_MODEL_TESTS=1`.
- New project-wide tests in `authentication/tests.py`:
  - the static files storage backend;
  - no missing migrations;
  - a password hash with the old iteration count is upgraded at sign-in;
  - both Compose stacks use the same service images (PR 3).
- A one-off OpenAPI schema comparison against `main` and a one-off run that collects deprecation
  warnings.
- The existing smoke scripts and the CI memory budget check.

**Target Platform**: `linux/amd64` and `linux/arm64` images. Production is a Raspberry Pi 5 running
a Portainer Business Edition Git stack. CI runs on GitHub-hosted Ubuntu runners for both
architectures.

**Project Type**: a web service (Django monolith with a Celery worker) plus its Compose and image
build.

**Performance Goals**: unchanged. On the Pi, 95% of searches answer in under 500 ms and a book save
takes under 2 s (SC-005, measured with `scripts/smoke_stack_budget.py` after PR 1 and after PR 3).

**Constraints**:
- The whole stack stays within 4 GiB.
- No new direct runtime dependency.
- Existing migrations are never edited.
- No new operator step for PR 1 and PR 2 (FR-014).
- PR 3's reset runs only while the server holds seed data alone.

**Scale/Scope**:
- PR 1: 10 files (see Project Structure), including the 2 new migrations, plus 3 new tests.
- PR 2: 1–2 files.
- PR 3: 7 files, plus 1 new test.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against the constitution **v2.1.0** (amended 2026-10-20, in the working tree, shipping
with PR 1).

| # | Principle / gate | Pre-design | Post-design | Evidence |
|---|---|---|---|---|
| I | Domain-owned apps | PASS | PASS | No new app. The settings changes are project wiring in `library/library/`. Each migration lives in its owning app (`authentication`, `order`). Project-wide tests go in `authentication/tests.py`, where the settings tests already are. Every endpoint stays under `/api/v1/` and in the schema ([contracts/api-compatibility.md](contracts/api-compatibility.md)). |
| II | Explicit role-based access | PASS | PASS | No route, permission or decorator changes. The existing permitted and denied tests must pass unchanged (FR-004). |
| III | Test-backed changes | PASS | PASS | Each behavior-preserving change has a test that fails without it: `STORAGES` (fails on 5.2 if the setting is not migrated), the migration check (fails until the two migrations exist) and the Compose image match (PR 3). The password re-hash test guards FR-007. Everything runs on PostgreSQL with pgvector, with real-model tests on both architectures. |
| IV | Secrets and safe defaults | PASS | PASS | No new settings or secrets. `DJANGO_SEED` still defaults to `false` in `docker-compose.yml`. The reset turns it on for one redeploy and replaces the demo passwords before the site is reachable (FR-023). |
| V | Consistent data, best-effort side effects | PASS | PASS | The drift is fixed with migrations from `makemigrations`, and none on `main` is edited. The PR 3 reset is the spec's documented exception for seed-only data: the old volumes are kept until verification, and the broker queue is dropped because analytics are derived data. No change to `transaction.atomic` or `on_commit` use. |
| VI | Lean, portable, reproducible deployment | PASS | PASS | One root `requirements.txt` pins the complete set. Wheels resolve identically on amd64 and arm64. No new direct dependency; the new transitive packages from huggingface-hub 2.x are listed in R1. The model and revision are unchanged. Memory and latency are measured in CI and on the Pi. README, operator guide and changelog are updated in each PR. `.env.example` needs no change: no variable changes, and `DB_ENGINE` stays valid (R3). |
| — | Platform constraints | PASS | PASS | Moving Django to the 5.2 line and DRF to 3.18 is identified in the spec (Assumptions) and justified below. PostgreSQL 15 → 18 and Redis 7.4 → 8.10 are component version changes, justified below. |
| — | CI gates (workflow item 4) | PASS | PASS | The workflow is unchanged. Lint, `smoke-test` on both architectures and CodeQL gate every PR. The `docker-compose.yml` validity check covers PR 3. |

**Gate result: PASS.** There are no violations. Complexity Tracking records the justifications the
platform constraints require.

## Project Structure

### Documentation (this feature)

```text
specs/002-django-lts-upgrade/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0: versions, Django 5.2 impact, drift, images, reset (R1–R15)
├── data-model.md        # Phase 1: dependency list, migrations, volumes, seed dataset
├── quickstart.md        # Phase 1: validation per pull request
├── contracts/
│   ├── runtime-dependencies.md   # the single requirements.txt and how it is regenerated
│   ├── api-compatibility.md      # what "API unchanged" means and how it is checked
│   └── service-images.md         # Compose images and volumes, and the one-time reset
├── deprecations.md      # Created in PR 1 (FR-012)
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
# PR 1: runtime dependencies
requirements.txt                       # complete pinned set, direct and transitive groups
library/requirements.txt               # deleted
library/library/settings.py            # STORAGES replaces STATICFILES_STORAGE; drop USE_L10N; 5.2 doc links
library/authentication/migrations/0003_alter_customuser_role.py   # new (makemigrations)
library/order/migrations/0003_alter_order_id.py                   # new (makemigrations)
library/authentication/tests.py        # storage, missing-migration and password re-hash tests
README.md                              # Django 5.2 LTS; local setup from root requirements.txt; layout
docs/shared/changelog.md               # PR 1 entry, including the constitution v2.1.0 amendment
.specify/memory/constitution.md        # v2.1.0 (already amended)
specs/002-django-lts-upgrade/deprecations.md                      # new

# PR 2: lint and format tools
requirements-dev.txt                   # black 26.10.1, ruff 0.17.1
pyproject.toml                         # only if a setting or rule was renamed or removed (FR-020)
docs/shared/changelog.md

# PR 3: database and broker images
docker-compose.yml                     # images, pgdata18 at /var/lib/postgresql, redisdata8
docker-compose-dev.yml                 # same images and volumes
library/authentication/tests.py        # test that both stacks use the same images
docs/deployment/raspberry-pi-portainer.md   # one-time reset; backup section names the new volumes
README.md                              # service table (PostgreSQL 18, Redis 8); remove old local volumes
docs/shared/changelog.md
.specify/memory/constitution.md        # v2.2.0: Database line names PostgreSQL 18
```

**Structure Decision**: the existing single Django project under `library/` with its Compose
stacks. No new app, module or script; every change edits a file that already owns the concern.

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

There are no violations. The rows below are the Principle VI justifications that the platform
constraints require for component changes.

| Change | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Django 4.1 → 5.2.18 (new release line) | 4.1 has had no security fixes since December 2023 (KAN-17); 5.2 LTS is supported until April 2028. | Staying on 4.1 leaves the site unpatched. 6.1 is not LTS, so its support ends sooner. |
| DRF 3.15.1 → 3.18.3 (new minor) | The spec asks for the latest compatible release; 3.18 supports Django 5.2 and carries security fixes (3.17.2, 3.18.2). | 3.15.1 does not declare support for Django 5.2. Pinning 3.16 would ignore the clarification. |
| Pin the complete transitive set | Principle VI requires exact pins. Today about 25 installed packages float between builds. | A lock tool adds a development dependency and a second format (R2). |
| PostgreSQL 15 → 18 (`pgvector 0.8.7-pg18`), new volume `pgdata18` | The spec asks for the latest images. PostgreSQL 18 needs a different data path, and a new volume makes the reset automatic and reversible. | `pg_upgrade` or a dump and restore are unnecessary for seed-only data. Reusing `pgdata` risks a crash loop and loses the rollback path (R12). |
| Redis 7.4 → 8.10 (`8.10.2-alpine`), new volume `redisdata8` | The spec asks for the latest images. An empty queue avoids events pointing at reseeded users. | Keeping `redisdata` would replay stale events against new user IDs (spec edge case). Valkey would be a component swap outside the scope (R13). |
