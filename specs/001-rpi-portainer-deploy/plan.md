# Implementation Plan: Automatic Deployment to a Self-Hosted Raspberry Pi

**Branch**: `feat/move-from-render-to-dedicated-rpi-host` | **Date**: 2026-10-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-rpi-portainer-deploy/spec.md`

## Summary

This feature replaces Render with a Raspberry Pi 5 that runs the site as a Portainer Business
Edition Git stack (`docker-compose.yml`), using only pre-built images.

**Pipeline**:
- Lint and the full smoke test run on native amd64 and arm64 runners for pushes to `main`,
  version tags and pull requests to `main`.
- For `main` and tag pushes, each architecture is built on its own runner and pushed by digest.
  The digests are then merged into one multi-architecture GHCR manifest, and the
  `PORTAINER_WEBHOOK_URL` webhook is called.
- Missing secrets are reported, failed calls fail visibly, and stale runs never move `main`.

**Embedding model**: the Render-constrained e5-small int8 model is replaced by `bge-m3` int8
(1024 dimensions).
- Research found it matches the current model on the 18-query seed evaluation, and is clearly
  more robust once similar distractor books are added.
- It is defined once in `library/book/embedding_config.py`, overridable through `BOOK_EMBEDDING_*`
  variables.
- The Dockerfile bakes it in through `scripts/fetch_embedding_model.py`. A system check rejects a
  runtime setting that differs from the image.
- Vectors move to an untyped pgvector column and are re-encoded at startup after a model change.

**Render retirement**: all Render files, checks and settings are removed. A platform-neutral
HTTPS-proxy switch replaces them, and an operator guide covers the Pi, Portainer, GitHub and the
Render shutdown.

## Technical Context

**Language/Version**: Python 3.12 (Django 4.1); POSIX `sh` (entrypoint); GitHub Actions and
Compose YAML.

**Primary Dependencies**:
- Runtime, pinned and unchanged: Django 4.1, DRF 3.15.1, drf-spectacular, pgvector 0.5.0,
  onnxruntime 1.30.0, sentencepiece 0.2.1, huggingface-hub 1.33.0, gunicorn 22.0.0, whitenoise,
  Celery 5.6.3.
- CI: `docker/setup-buildx-action@v3`, `docker/build-push-action@v6`,
  `docker/metadata-action@v5`, `docker/login-action@v3`, `actions/upload-artifact`,
  `actions/download-artifact`.
- No new runtime Python dependencies.

**Storage**:
- PostgreSQL 15 with pgvector (`pgvector/pgvector:0.8.2-pg15`). `book_bookembedding.vector`
  becomes an untyped `vector`.
- Redis 7.4 with AOF as the Celery broker.
- Named volumes `pgdata` and `redisdata`.
- The model files live inside the image, under `/app/.cache/book-embeddings` with a
  `manifest.json`.

**Testing**:
- The Django test runner on PostgreSQL in `docker-compose-dev.yml`, mocked by default. Real-model
  tests and the 18-query evaluation set are gated by `RUN_BOOK_EMBEDDING_MODEL_TESTS=1`.
- `node --test` for tracking.
- Smoke scripts `smoke_test_tracking`, `smoke_tracking_recovery.py` and the new
  `smoke_stack_budget.py`.
- `docker compose config` for the server file.

**Target Platform**:
- `linux/amd64` and `linux/arm64` containers.
- Production: Raspberry Pi 5 (Cortex-A76, 8 GB, 64-bit OS) with Portainer BE and Docker Engine.
- CI: GitHub-hosted `ubuntu-24.04` and `ubuntu-24.04-arm` runners.

**Project Type**: a web service (Django monolith with Celery worker) plus deployment
infrastructure (CI workflow, Compose stacks, image build).

**Performance Goals**:
- On the Pi, 95% of searches return in under 500 ms (SC-010) and book saves take under 2 s
  (SC-011).
- Re-encoding after a model change finishes within 10 minutes for 1,000 books (SC-014).
- A merge is live within 30 minutes (SC-001).
- A routine redeploy causes under 2 minutes of downtime (SC-009).

**Constraints**:
- The whole stack stays within 4 GB of memory on the Pi (SC-012); the estimate is about 2.7 GB
  (research R6).
- Nothing is built on the server.
- No files tuned for one CPU family or instruction set.
- Secrets come only from the environment.
- Webhook TLS is always verified.

**Scale/Scope**:
- Up to about 1,000 books on one Pi, with demo-level traffic.
- About 25 repository files touched (see Project Structure), plus one new migration and three
  new scripts and modules.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against the constitution **v2.0.0** (amended 2026-10-20). That amendment resolves the
spec's assumption that Render retirement conflicted with v1.0.0.

| # | Principle / gate | Pre-design | Post-design | Evidence |
|---|---|---|---|---|
| I | Domain-owned apps | PASS | PASS | The model setting, system checks, migration and re-encoding live in `book`. There is no new app. Startup reuses the single "embedding refresh" implementation (`generate_book_embeddings`) instead of a second copy. There is no API change. |
| II | Explicit role-based access | PASS | PASS | No new views or endpoints. The healthcheck uses the existing anonymous `/api/schema/`. |
| III | Test-backed changes | PASS | PASS | New and updated tests: spec resolution, validation and tag (`book`); manifest checks E001 and W001; migration and untyped-vector storage; startup re-encode skip and resume (mocked); proxy and host settings replacing `RenderSettingsTests` (`authentication`); the real-model evaluation set (18/18, both architectures). Default runs never load the model. |
| IV | Secrets and safe defaults | PASS | PASS | `SECRET_KEY` and `DB_PASSWORD` use `:?` with no defaults. `PORTAINER_WEBHOOK_URL` is only a repository secret and never printed. `TRUST_X_FORWARDED_PROTO` defaults to `False`. Server `DJANGO_SEED` defaults to `false`. |
| V | Consistent data, best-effort side effects | PASS | PASS | Migration `book/0004` comes from `makemigrations`. Each vector is tagged with `spec.tag`, and search filters on it. Re-encoding commits per book under row locks, as the existing command does. Analytics are untouched. |
| VI | Lean, portable, reproducible deployment | PASS | PASS | Pins are unchanged. The model is defined in one place and fetched by its own script. The images are multi-architecture with no instruction-set files. The Pi stack uses images only. The memory budget and latency are measured by `smoke_stack_budget.py` (CI: memory; Pi: latency). Dev and server Compose files are split. `.env.example`, the README and the operator guide are updated in the same PR. New infrastructure is justified below. |
| — | Platform constraints | PASS | PASS | The model and vector-size change is identified in the spec (FR-027) and justified here (R1, R4). ONNX Runtime on CPU in process is unchanged. |
| — | CI gates (workflow item 4) | PASS | PASS | Lint, plus smoke-test on native amd64 and arm64, with a `docker-compose.yml` validity check. Publishing and the webhook run only for `main` and `v*` pushes after both pass. |

**Gate result: PASS.** There are no violations, so Complexity Tracking only records the
justification Principle VI requires for new infrastructure.

## Project Structure

### Documentation (this feature)

```text
specs/001-rpi-portainer-deploy/
├── spec.md
├── plan.md                         # this file
├── research.md                     # Phase 0: decisions R1–R12 and model measurements
├── data-model.md                   # Phase 1: BookEmbedding, model spec, manifest, references, stack
├── quickstart.md                   # Phase 1: validation scenarios (dev, CI, Pi)
├── contracts/
│   ├── embedding-model-setting.md  # BOOK_EMBEDDING_* variables, fetch script, E001/W001, re-encode
│   ├── server-stack.md             # docker-compose.yml services, variables, Portainer settings
│   └── ci-pipeline.md              # triggers, jobs, image tags, deploy behavior
├── checklists/requirements.md
└── tasks.md                        # Phase 2 (/speckit-tasks), not created here
```

### Source Code (repository root)

```text
.github/workflows/docker-build.yml        # REWRITE: triggers; amd64+arm64 smoke-test; publish→merge→deploy
Dockerfile                                # BOOK_EMBEDDING_* ARG→ENV; runs fetch script; gunicorn config
docker-compose.yml                        # NEW CONTENT: server stack (images only, Portainer variables)
docker-compose-dev.yml                    # RENAMED from docker-compose.yml; + image: library-django:dev
entrypoint.sh                             # migrate (checks) → seed → re-encode stale vectors; Render bits removed
.env.example                              # new variables; optional COMPOSE_FILE=docker-compose-dev.yml
AGENTS.md                                 # CI description → docker-compose-dev.yml
README.md                                 # quick start, embeddings, tests, layout, deployment → Pi
docs/deployment/raspberry-pi-portainer.md # NEW operator guide (FR-021, FR-022)
docs/ba/semantic-search.md                # bge-m3, no prefixes, Pi budget instead of Render 512 MiB
docs/shared/changelog.md                  # one entry (feature, and constitution v2.0.0)
.specify/memory/constitution.md           # remove Sync Impact Report comment before commit
render.yaml                               # DELETE
scripts/
├── fetch_embedding_model.py              # NEW: resolve spec → download pinned files → manifest.json
├── smoke_stack_budget.py                 # NEW: peak memory (4 GiB) + search/save latency
├── smoke_tracking_recovery.py            # unchanged (called with --compose-file docker-compose-dev.yml)
├── test_tracking_js.cjs                  # unchanged
├── render_start.py                       # DELETE
├── test_render_start.py                  # DELETE
├── check_render_config.py                # DELETE
└── smoke_render_free.py                  # DELETE
library/
├── gunicorn.conf.py                      # NEW: workers from WEB_CONCURRENCY, timeout 60, post_worker_init warm-up
├── library/settings.py                   # hosts/proxy/CSRF without Render; embedding cache dir
├── authentication/tests.py               # RenderSettingsTests → proxy/host settings tests
└── book/
    ├── embedding_config.py               # NEW: the single model definition (stdlib only)
    ├── checks.py                         # NEW: system checks book.E001 / book.W001
    ├── apps.py                           # register checks
    ├── embeddings.py                     # generic encoder: pooling, prefixes, threads, manifest path
    ├── search.py                         # query prefix and tag filter from the spec
    ├── models.py                         # VectorField() untyped; refresh check uses spec
    ├── migrations/0004_*.py              # NEW (makemigrations): vector → untyped
    ├── management/commands/generate_book_embeddings.py  # --threads; tag from spec
    ├── search_evaluation.json            # NEW: 18 evaluation queries (EN, and UK against EN)
    ├── test_embedding_config.py          # NEW: spec, tag, validation, manifest, checks
    ├── tests.py                          # model-agnostic dimensions/prefixes; storage; re-encode
    └── test_search.py                    # evaluation-set real-model test replaces 3-query test
```

**Structure decision**: the existing single Django project layout stays. Embedding work stays
in the `book` app (Principle I), and deployment files stay at the repository root and in
`scripts/`, where CI and Portainer expect them.
`library/requirements.txt` stays identical to `requirements.txt`, because no dependency changes.

## Phase outputs

- **Phase 0**: [research.md](research.md). There were no open unknowns, and every
  technical decision (R1–R12) is recorded with its alternatives.
  - FR-028's measurements: quality and x86-64 latency and memory were measured.
  - Pi latency is estimated, and is confirmed by quickstart §5 during rollout.
- **Phase 1**:
  - [data-model.md](data-model.md)
  - [contracts/embedding-model-setting.md](contracts/embedding-model-setting.md)
  - [contracts/server-stack.md](contracts/server-stack.md)
  - [contracts/ci-pipeline.md](contracts/ci-pipeline.md)
  - [quickstart.md](quickstart.md)
  - The REST API is unchanged, so no API contract is needed.
- **Implementation order for `/speckit-tasks`**, matching the user stories:
  1. Model setting, storage and re-encoding (US5 foundation).
  2. Dev/server Compose split and Dockerfile (US1).
  3. CI pipeline and deploy (US2, US3).
  4. Render removal and documents (US4).
  5. Operator guide.

## Complexity Tracking

> Principle VI requires every new infrastructure component to be justified here. There are no
> constitution violations.

| Addition | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| GitHub-hosted `ubuntu-24.04-arm` runners for `smoke-test` and `publish` | FR-004 requires the build and full smoke test on real ARM64 | QEMU emulation was rejected in clarification. It is several times slower for the model layer and tests, and it isn't real hardware. |
| Per-architecture `publish` jobs plus a `merge` manifest job | One manifest list for both architectures, without emulation (FR-001) | One `buildx` multi-platform build on one runner needs QEMU for the foreign architecture. |
| CI → Portainer webhook (external call with a repository secret) | FR-015: redeploy only after both architectures are published | Portainer Git polling sees the new commit before the images exist, and would redeploy the old image. |
| `scripts/smoke_stack_budget.py` (replaces `smoke_render_free.py`) | Principle VI requires measured memory and latency against the Pi budget | Portainer's container stats are manual and miss the latency. The Render check targets a retired platform. |
