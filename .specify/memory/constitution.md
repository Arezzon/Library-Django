<!--
Sync Impact Report
==================
Version change: unversioned template → 1.0.0 (initial ratification)

Modified principles (template placeholder → ratified title):
  - [PRINCIPLE_1_NAME] → I. Domain-Owned Django Apps
  - [PRINCIPLE_2_NAME] → II. Explicit Role-Based Access
  - [PRINCIPLE_3_NAME] → III. Test-Backed Changes (NON-NEGOTIABLE)
  - [PRINCIPLE_4_NAME] → IV. Secrets and Safe Defaults
  - [PRINCIPLE_5_NAME] → V. Consistent Data, Best-Effort Side Effects
  - (new)              → VI. Lean, Reproducible Deployment

Added sections:
  - Technology & Platform Constraints (was [SECTION_2_NAME])
  - Development Workflow & Quality Gates (was [SECTION_3_NAME])
  - Governance rules (was [GOVERNANCE_RULES])

Removed sections: none

Templates: not modified. The plan template's "Constitution Check" derives its gates from
this file at runtime.

Deferred placeholders: none.

Known non-compliance in existing code (follow-up work, not changed by this amendment):
  - Principle II: the /api/v1/ user, author, book and order viewsets declare no
    permission_classes and REST_FRAMEWORK sets no DEFAULT_PERMISSION_CLASSES, so DRF
    allows anonymous create/update/delete on them.
  - Guidance drift: AGENTS.md lists `manage.py test authentication author book order`;
    CI also runs the `events` suite.

Remove this comment before committing the amended constitution.
-->

# Library Django Constitution

## Core Principles

### I. Domain-Owned Django Apps

- Feature code MUST live in the Django app under `library/` that owns its domain:
  `authentication` (users, roles), `author`, `book` (catalog, embeddings, semantic search),
  `order` (borrowing) and `events` (tracking, analytics). Project-wide wiring (settings, URLs,
  Celery, shared mixins) belongs in `library/library/`.
- A new Django app MUST be justified in the plan's Complexity Tracking table; extending the
  owning app is the default.
- A domain rule (stock availability, borrowing guards, embedding refresh, event identity) MUST
  be implemented once, in a model, manager or service module, and reused by both the
  server-rendered views and the REST API. Views, forms and serializers MUST NOT re-implement it.
- Every REST endpoint MUST be mounted under `/api/v1/` and MUST appear accurately in the
  drf-spectacular schema at `/api/schema/`; query parameters and non-default responses MUST be
  described with `extend_schema`.

Rationale: CODEOWNERS assigns review per app, and one implementation per rule keeps the web UI
and the API from drifting apart.

### II. Explicit Role-Based Access

- Every view and API endpoint MUST declare its audience: anonymous, authenticated, resource
  owner, or librarian (`ROLE_LIBRARIAN`). HTML views use the decorators in
  `authentication/decorators.py`; DRF views set `permission_classes`. Relying on a framework
  default is not a declaration.
- Data-changing actions (create, update, delete, return, reopen, reassign) MUST be limited to
  librarians or the owning user, MUST use a non-GET method, and MUST be CSRF-protected.
- Librarian-only data, including the analytics dashboard and other users' records and orders,
  MUST NOT be exposed to visitors in templates or API responses.
- Tests for a protected route MUST cover at least one permitted role and at least one denied
  caller (anonymous or visitor).

Rationale: roles are the system's security boundary, and DRF allows anonymous access to any
endpoint that does not declare otherwise.

### III. Test-Backed Changes (NON-NEGOTIABLE)

- Every behavior change and bug fix MUST include Django tests in the owning app (`tests.py` or
  `test_*.py`) that fail without the change and pass with it.
- Tests MUST run against PostgreSQL with pgvector, as CI does; SQLite is not supported because
  migrations create `vector(384)` columns.
- Default test runs MUST NOT download or execute the embedding model; they mock the encoder
  (for example by patching `book.embeddings.load_embedding_model`). Real ONNX inference tests
  are gated by `RUN_BOOK_EMBEDDING_MODEL_TESTS=1`, which CI enables.
- Celery-backed code is unit-tested with `CELERY_TASK_ALWAYS_EAGER=True`; real queue behavior
  is covered by `manage.py smoke_test_tracking` and `scripts/smoke_tracking_recovery.py`, which
  MUST keep passing.
- Changes to `library/events/static/events/tracking.js` MUST keep
  `node --test scripts/test_tracking_js.cjs` passing and MUST extend it for new behavior.

Rationale: CI is the only gate before an image is published, and a test that cannot fail
protects nothing.

### IV. Secrets and Safe Defaults

- Secrets (`SECRET_KEY`, database and broker credentials, tokens) MUST come only from the
  environment. Source code, settings, Dockerfiles, Compose files, fixtures and `.env.example`
  MUST NOT contain real or default secret values.
- Settings MUST fail closed: a missing `SECRET_KEY` raises `ImproperlyConfigured`, `DEBUG` is
  off unless set to `True`, and every new security-relevant setting defaults to its safe value.
- Logs, error messages, API responses, test output and issue reports MUST NOT include secrets,
  credentials, connection URLs containing passwords, or personal data the feature does not need.
- Demo accounts created by `seed_db.py` are for local and demo use only and MUST remain
  documented as such.

Rationale: a default secret in the repository or the image is a published secret.

### V. Consistent Data, Best-Effort Side Effects

- Schema changes MUST ship as Django migrations generated by `makemigrations` and committed with
  the code that needs them. A migration that has reached `main` MUST NOT be edited; corrections
  go in a new migration.
- Writes that must succeed or fail together (an order with its stock change, a book with its
  embedding) MUST run inside `transaction.atomic`. When a required step fails, such as embedding
  inference during a book save, the whole business change MUST roll back.
- Analytics and other non-essential side effects MUST NOT block, slow or undo a business
  operation: they publish after commit (`transaction.on_commit`), a broker outage is logged
  rather than raised to the user, and the events API answers a retryable `503`.
- Event ingestion MUST stay idempotent: retrying the same client `event_id` MUST NOT create a
  second event.

Rationale: catalog and borrowing data are the system of record; analytics are derived and may
be lost, but must never corrupt that record.

### VI. Lean, Reproducible Deployment

- Runtime dependencies MUST be pinned to exact versions in `requirements.txt`, kept identical in
  `library/requirements.txt`; lint and format tools are pinned in `requirements-dev.txt`. Model
  revisions used for inference MUST be pinned.
- The Render free-tier deployment (web and Celery worker sharing one container under 512 MiB)
  MUST keep working, and `scripts/smoke_render_free.py` MUST pass. A change that adds a
  dependency, model or background process MUST report the peak memory that script measures.
- A new runtime dependency, external service or infrastructure component MUST be justified in
  the plan's Complexity Tracking table, including the simpler alternative that was rejected.
- The Docker Compose stack (`web`, `db`, `redis`, `worker`) MUST build and start from `.env`
  values alone. Changes to setup or configuration MUST update `.env.example`, the README and,
  where relevant, `render.yaml` in the same pull request.

Rationale: the hosted demo runs on free plans with hard limits, and exact pins keep CI, Docker
and Render builds identical.

## Technology & Platform Constraints

- **Runtime**: Python 3.12, Django 4.1, Django REST Framework, drf-spectacular.
- **Database**: PostgreSQL (version 15 in Compose and on Render) with the `vector` extension;
  book embeddings are 384-dimensional pgvector columns.
- **Background work**: Celery on a Redis-compatible broker, JSON serialization only, `events`
  queue. The web process MUST keep serving pages while the broker is unavailable.
- **Embeddings**: ONNX Runtime running the pinned `intfloat/multilingual-e5-small` model on CPU,
  in process. Hosted model APIs and external vector services are not used.
- **UI**: server-rendered Django templates, Tailwind via CDN and plain JavaScript in app static
  directories, with no frontend build step.
- **Serving**: Gunicorn with WhiteNoise in the Docker image; Docker Compose for local
  development and CI; a Render Blueprint for the hosted demo.
- **Code style**: ruff and black, configured in `pyproject.toml` (line length 88, target
  `py312`). Migrations are excluded from both and stay as Django generated them.
- Replacing any component above, upgrading Django or DRF, or adding a frontend toolchain MUST
  be identified in the feature spec and justified in the plan under Principle VI.

## Development Workflow & Quality Gates

1. **Branching**: feature branches start from a freshly fetched `origin/main`, or from a
   verified, current feature branch when the work depends on it, as described in
   `.agents/skills/fresh-feature-branch/SKILL.md`.
2. **Design**: for features planned with Spec Kit, the plan's Constitution Check MUST record a
   pass or fail for each principle, and every failure MUST be justified in Complexity Tracking
   before implementation starts. Business-analysis requirements live in `docs/ba/`.
3. **Local checks**: before a pull request, run `ruff check .` and `black --check .` from the
   repository root and the Django tests for every affected app from `library/`.
4. **CI gates**: all of these MUST pass before merge:
   - the `lint` job;
   - the `smoke-test` job: Render configuration checks, tracking JavaScript tests,
     `manage.py test authentication author book order events` on PostgreSQL, endpoint checks,
     asynchronous tracking smoke test, broker and worker recovery, and the 512 MiB Render check;
   - CodeQL, with any alert newly raised by the change resolved or dismissed with a recorded
     reason.

   Images are published to GHCR only from non-pull-request builds after `lint` and `smoke-test`
   pass.
5. **Pull requests**: the title follows `<action>(<service>): <description>`; the description
   follows `.github/PULL_REQUEST_TEMPLATE.md`, with Definition of Done items checked only when
   true and unchecked items explained; one entry is added to `docs/shared/changelog.md`; the
   code owners in `.github/CODEOWNERS` for each touched path review the change.
6. **Scope**: each commit and pull request contains only the change it describes; unrelated
   refactors go in a separate pull request.
7. **Documentation**: changes to behavior, setup, configuration or API contracts MUST update
   the README, the relevant feature document in `docs/` and `.env.example` in the same pull
   request.
8. **Defects**: bug reports use `.github/ISSUE_TEMPLATE/bug_report.md`.

## Governance

- This constitution takes precedence over other practice documents. `AGENTS.md`, `README.md`
  and the skills in `.agents/skills/` provide runtime guidance and MUST stay consistent with it;
  where they conflict, this constitution applies until the conflict is resolved by amendment.
- **Amendments** are made through `/speckit-constitution` and delivered as a pull request that
  changes `.specify/memory/constitution.md`, states the version bump and its rationale, and adds
  a changelog entry. A code owner of the path, per `.github/CODEOWNERS`, MUST approve it.
  Amendments MUST NOT be made while a Superpowers handoff is `executing`; set the handoff to
  `blocked` first, as the speckit-superpowers-bridge guard requires.
- **Versioning** follows semantic versioning:
  - MAJOR: a principle or governance rule is removed or redefined incompatibly.
  - MINOR: a principle or section is added, or guidance is materially expanded.
  - PATCH: clarifications, wording and typo fixes that do not change meaning.
- **Compliance**: every Spec Kit plan passes the Constitution Check gate, and every reviewer
  checks the principles that apply to the touched code. Code that predates this constitution
  MUST be brought into compliance when it is changed, or through a dedicated feature.
- **Review**: the constitution MUST be reviewed whenever the CI workflow, the deployment target
  or a component in Technology & Platform Constraints changes, so the rules match what is
  actually enforced.

**Version**: 1.0.0 | **Ratified**: 2026-10-19 | **Last Amended**: 2026-10-19
