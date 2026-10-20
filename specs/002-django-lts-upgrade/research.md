# Research: Django 5.2 LTS Upgrade and Dependency Refresh

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Date**: 2026-10-20

Versions below were the latest on 2026-10-20. Before each pull request, re-run the resolution in
[quickstart.md](quickstart.md) §1. A newer release then replaces the version named here, as FR-001
and FR-003 require.

## R1. Target versions for the runtime dependencies (PR 1)

**Decision**: Resolve every runtime package to its latest release, except where something else
in the pinned set requires a lower one. The resolution was checked on CPython 3.12 against
`manylinux` wheels for both `x86_64` and `aarch64`. It gives the same 53 packages on both, with
wheels for all of them.

| Package | Now | Target | Note |
|---|---|---|---|
| Django | 4.1 | **5.2.18** | Newest 5.2 release (2026-10-06). 6.1.2 is newer but not LTS (spec Assumptions). |
| djangorestframework | 3.15.1 | **3.18.3** | Requires `django>=5.2`; classifiers 5.2–6.1. See R5. |
| drf-spectacular | 0.30.0 | 0.30.0 | Already the latest; classifiers include 5.2. |
| psycopg2-binary | 2.9.9 | **2.9.13** | Django 5.2 needs psycopg2 2.8.4 or later. |
| python-dotenv | 1.2.3 | **1.2.4** | |
| gunicorn | 22.0.0 | **26.2.0** | See R7. |
| whitenoise | 6.7.0 | **6.12.0** | Classifiers 4.2–6.0. Configured through `STORAGES` (R3). |
| pgvector | 0.5.0 | **0.5.1** | |
| onnxruntime | 1.30.0 | **1.31.0** | Requires Python 3.11 or later. See R9. |
| sentencepiece | 0.2.1 | **0.2.2** | |
| huggingface-hub | 1.33.0 | **2.2.0** | Major release. See R8. |
| celery[redis] | 5.6.3 | 5.6.3 | Already the latest. |
| numpy | unpinned | **2.5.4** | Imported directly by `book`, so now pinned as a direct dependency. |
| kombu | unpinned | **5.6.2** | Imported directly by `events`. |
| redis | unpinned | **6.4.0** | Imported directly. Latest is 8.1.0, but kombu 5.6.2 requires `redis<6.5`, so 6.4.0 is the highest compatible release. |
| asgiref | 3.5.2 | **3.12.1** | Django 5.2 needs 3.8.1 or later; the old pin would have broken the install. |
| rpds-py | 2026.6.3 | **2026.9.1** | |
| pytz | 2022.2.1 | **removed** | Nothing in the resolved set requires it any more: Django 5 and Celery 5.6 use `zoneinfo`. |
| tzdata | 2025.2 | 2026.5, if required | Kept only if the Linux resolution still pulls it in (R2). |
| attrs, inflection, jsonschema, jsonschema-specifications, PyYAML, referencing, sqlparse, typing_extensions, uritemplate | — | unchanged | Already the latest. |

Every other resolved package is at its latest release. The resolution also adds the packages that
huggingface-hub 2.x and Celery pull in: `httpx2`, `httpcore2`, `hf-xet`, `truststore`, `anyio`,
`h11`, `idna`, `click` and its plugins, `billiard`, `vine`, `amqp`, `tzlocal`,
`python-dateutil`, `six`, `flatbuffers`, `protobuf`, `packaging`, `filelock`, `fsspec`, `tqdm`,
`prompt_toolkit` and `wcwidth`.

**Rationale**: the spec's clarification requires the latest releases, or the highest releases that
are compatible. Below their latest release are only Django, which stays on the LTS line by
design, and redis-py, which kombu caps. FR-003 needs a reason for each; the table records both.

**Alternatives considered**: move only the packages that block Django 5.2 (the original FR-003;
replaced by the clarification); move to Django 6.1 (not LTS, against KAN-17).

## R2. Pin the complete resolved set in one root `requirements.txt` (PR 1)

**Decision**: The root `requirements.txt` pins every runtime package the image installs, in two
commented groups:

1. **Direct**: packages the code imports or the image runs. These are Django, djangorestframework,
   drf-spectacular, psycopg2-binary, python-dotenv, gunicorn, whitenoise, pgvector, onnxruntime,
   numpy, sentencepiece, huggingface-hub, celery[redis], kombu and redis.
2. **Transitive**: everything those pull in on Linux, pinned for reproducible builds.

The transitive group is generated inside the built Linux image (`pip freeze`), not on a developer
machine. Pip evaluates platform markers against the machine it runs on: on Windows the resolution
adds `colorama` (a Windows-only dependency of `click`), and on Linux it adds packages Windows
does not. `library/requirements.txt` is deleted.

**Rationale**:
- Principle VI requires runtime dependencies to be pinned to exact versions. Today `numpy`,
  `protobuf`, `kombu`, `redis`, `httpx` and about 20 others are not pinned, so two builds of the
  same commit can differ.
- The file's own header already says transitive dependencies are "pinned for reproducible
  builds"; this completes it.
- FR-015 asks for one list.

**Alternatives considered**:
- Keep the partial list: unpinned packages can change between builds without anyone noticing,
  which breaks Principle VI.
- A lock tool such as pip-tools or uv: adds a development dependency and a second file format for
  a single-image project. The plain file plus Dependabot already covers updates.
- Keep `library/requirements.txt` as a copy: the spec rules it out (FR-015), and the constitution
  v2.1.0 no longer asks for it.

## R3. Django 4.1 → 5.2 changes that reach this code (PR 1)

**Decision**: Change two settings. Leave everything else as it is.

| Finding | Effect on 5.2 | Action |
|---|---|---|
| `STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"` | Removed in 5.1 and silently ignored. Static files would lose compression and their hashed, cache-busting names, with no error. | Replace it with `STORAGES = {"default": FileSystemStorage, "staticfiles": CompressedManifestStaticFilesStorage}` (FR-008, FR-011). Add a test that fails without the change. |
| `USE_L10N = True` | Removed in 5.0 and ignored. Localized formatting is always on, which matches today's behavior. | Delete the line (FR-011). |
| `DB_ENGINE` defaults to `django.db.backends.postgresql_psycopg2` | Django 5.2.18's `load_backend` still maps this name to `postgresql`, as confirmed in the installed source. | No change. Renaming it would touch `.env.example`, the Compose files and the Portainer variables for no gain. |
| Settings comments link to the Django 3.1 and 4.0 docs | Cosmetic | Point the links at 5.2 along with the settings change. |
| Default form rendering is div-based in 5.0 | No template renders `{{ form }}` or `as_table`, `as_p` or `as_ul`, so this has no effect. | None. |
| PBKDF2 iterations 390,000 → 1,000,000 | Stored hashes still verify, and Django re-hashes on the next successful sign-in. | Add a test: a user with a 390,000-iteration hash signs in and is re-hashed (FR-007). |
| Removed or deprecated APIs swept: `pytz`, `index_together`, `CheckConstraint(check=)`, `timezone.utc`, `assertFormError(response, …)`, `assertQuerysetEqual`, `get_storage_class`, `URLField` without `assume_scheme`, positional `Model.save()`, `format_html()` without arguments, `USE_DEPRECATED_PYTZ`, `CSRF_COOKIE_MASKED` | None of them is used. | None. |
| Sessions | The serializer (JSON) and the session hash algorithm have not changed since 3.1. | None. Signed-in users stay signed in (spec edge case). |

**Evidence**: with the R1 pins installed, `manage.py check` on Django 5.2.18 with
`PYTHONWARNINGS=always` reports only the expected local `book.W001` (no model downloaded) and **no
deprecation warnings**. Warnings raised while the tests run are checked in quickstart §2.

## R4. Migration drift that predates the upgrade (PR 1)

**Finding**: `makemigrations --check --dry-run` on 5.2.18 reports two changes that have no
migration. Neither comes from the upgrade: both follow from model and setting changes already on
`main`, so Django 4.1 detects them as well. CI has no `makemigrations --check` step, which is how
they went unnoticed.

1. `authentication.0003_alter_customuser_role`: the `role` choice label changed from `admin` to
   `librarian` without a migration. This changes migration state only and runs no SQL.
2. `order.0003_alter_order_id`: `0001_initial` created `id` as `AutoField`, but
   `DEFAULT_AUTO_FIELD` has been `BigAutoField` since the initial commit. The SQL is
   `ALTER COLUMN id TYPE bigint` plus the sequence; no other table references `order.id`.

**Decision**: Generate both with `makemigrations` and ship them in PR 1, as FR-009 and the "schema
drift" edge case require. Add a project-wide test that calls `makemigrations --check --dry-run`,
so drift fails the existing test job in the future without a CI change.

**Rollback**: the 4.1 image also models `order.id` as `BigAutoField`, from `DEFAULT_AUTO_FIELD`. It
reads a `bigint` column without problems, and the `role` change has no SQL. The previous release
therefore stays deployable on the migrated database (FR-009).

**Alternatives considered**: a separate CI step running `makemigrations --check` (a test does the
same within the existing gate); leaving the drift (FR-009 forbids it, and the next `makemigrations`
by anyone would quietly include it).

## R5. Django REST Framework 3.15.1 → 3.18.3 (PR 1)

**Breaking changes in the range**:
- 3.16: changes to UniqueConstraint and nullable-field validation.
- 3.17: coreapi removed.
- 3.18.0: Django 4.2–5.1 dropped; `many=True` serializer errors use dict format;
  `UniqueTogetherValidator` gains `nulls_distinct`.
- 3.18.1: `FloatField` rejects NaN and infinity.
- 3.18.2: limits on large `Accept` headers.

**Impact on this code**: low.
- `many=True` appears only on output serializers (`BookSearchSerializer`) and on
  `PrimaryKeyRelatedField(many=True)`, which is a `ManyRelatedField`, not a `ListSerializer`.
- No serializer declares a unique validator, and no model has `UniqueConstraint` or
  `unique_together`.
- `similarity` is a read-only `FloatField`.
- The schema uses drf-spectacular, not coreapi.

**Decision**: Take 3.18.3. Verify FR-005 by comparing the OpenAPI schema generated on `main` with
the one generated on the branch ([contracts/api-compatibility.md](contracts/api-compatibility.md)),
and by running the existing API tests unchanged.

## R6. drf-spectacular 0.30.0 (PR 1)

0.30.0 is already the latest release, declares support for Django 5.2, and depends on DRF 3.10.3
or later. The pin stays. Any difference in the generated schema must come from DRF or Django, and
is handled by R5's comparison.

## R7. gunicorn 22.0.0 → 26.2.0 (PR 1)

**Breaking changes in the range**:
- 23.0: stricter HTTP/1.1 parsing.
- 25.0: eventlet worker removed.
- 26.0: stricter request-target and header checks; body framing dropped on HEAD, 204 and 304.
- 26.1: `packaging` no longer a dependency.
- 26.2: cleartext HTTP/2 off by default.

None touches the sync worker, `workers`, `timeout` or the `post_worker_init` hook that
`library/gunicorn.conf.py` uses.

**Decision**: Take 26.2.0 and leave `gunicorn.conf.py` unchanged. The CI endpoint checks, the
tracking smoke test and the Pi measurement cover request handling behind the proxy.

## R8. huggingface-hub 1.33.0 → 2.2.0 (PR 1)

**What changed**: 2.0 moves the HTTP layer from `httpx` to `httpx2`/`httpcore2`, uses the system
certificate store (`truststore`) and removes APIs that 1.x had deprecated. `snapshot_download`
keeps its signature.

**How the project uses it**:
- The only caller is `scripts/fetch_embedding_model.py`, at image build time. It calls
  `snapshot_download(repo_id, revision, cache_dir, allow_patterns)` and catches every exception.
- Containers run with `HF_HUB_OFFLINE=1` and never download.
- `book/tests.py` patches `huggingface_hub.snapshot_download`, which still exists.
- `python:3.12-slim` ships the system CA bundle that `truststore` reads.

**Decision**: Take 2.2.0 with no code change. The image build exercises the download on both
architectures, and the manifest checks confirm the model files are present.

## R9. onnxruntime 1.31.0, numpy 2.5.4, protobuf 7.x and sentencepiece 0.2.2 (PR 1)

These change the inference stack, not the model: the model and its revision stay pinned in
`book/embedding_config.py`.

**Verification**:
- The real-model tests and the 18-query English and Ukrainian evaluation set run on both
  architectures (`RUN_BOOK_EMBEDDING_MODEL_TESTS=1`).
- `smoke_stack_budget.py` checks memory in CI.
- On the Pi, the operator guide's measurement (§"Measure the stack on the Pi") checks SC-005: at
  most 4 GiB, and 95% of searches under 500 ms.

If the evaluation set or the budget fails, the fallback is the highest onnxruntime release that
passes, with the reason recorded (FR-003).

## R10. Deprecation warnings: how they are found and recorded (PR 1)

**Decision**:
1. Run the full suite once inside the development stack with
   `PYTHONWARNINGS=always::DeprecationWarning,always::PendingDeprecationWarning`. These categories
   include Django's `RemovedInDjango60Warning` and `RemovedInDjango61Warning`.
2. Sort each warning by the file that triggers it: project code (`/app/library`, `/app/scripts`)
   or `site-packages`.
3. Fix every warning from project code (FR-010).
4. List every third-party warning in `specs/002-django-lts-upgrade/deprecations.md` with the
   package, the removal release and the expected resolution (FR-012).

**Alternatives considered**: making CI fail on any deprecation warning (`-W error`). Third-party
warnings that the project cannot fix would fail every run, and US2 needs a recorded baseline, not
a new gate.

## R11. Lint and format tools (PR 2)

**Measured on 2026-10-20**: with black **26.10.1** (from 26.5.1) and ruff **0.17.1** (from
0.16.10), `black --check .` reports "86 files would be left unchanged" and `ruff check .` reports
"All checks passed!", with no warnings about the `pyproject.toml` settings.

**Decision**: PR 2 changes only the two pins in `requirements-dev.txt`, plus whatever
reformatting or lint fixes the then-latest releases ask for. Today that is none. `pyproject.toml`
changes only if a rule is renamed or removed (FR-020). The CI lint job reads
`requirements-dev.txt`, so it needs no change.

## R12. Database image: `pgvector/pgvector:0.8.7-pg18` (PR 3)

**Findings**:
- The newest tags are `0.8.7-pg18` (pgvector 0.8.7 on PostgreSQL 18), published for `amd64` and
  `arm64`. No PostgreSQL 19 image exists yet.
- Django 5.2 supports PostgreSQL 14 and later. `psycopg2-binary` bundles its own `libpq`.
- PostgreSQL 18 images keep their data in `/var/lib/postgresql/18/docker`, and their volume is
  `/var/lib/postgresql`. A volume still mounted at `/var/lib/postgresql/data` makes the container
  exit at startup.
- A PostgreSQL 18 server cannot open the PostgreSQL 15 data directory in any case.

**Decision**: In both Compose files, use `pgvector/pgvector:0.8.7-pg18`, mounted at
`/var/lib/postgresql` on a **new volume** named `pgdata18`.
- On the Pi, the webhook redeploy then starts PostgreSQL 18 on an empty volume. The new database
  can never meet the old data, which FR-024's "never starts the new database on the old data"
  requires, and no manual step has to happen before the merge.
- The old `pgdata` volume stays untouched. Until the operator deletes it, reverting PR 3 brings
  back the PostgreSQL 15 database exactly as it was.

**Alternatives considered**:
- `pg_upgrade` or a dump and restore: not needed, because the data is seed-only (spec
  clarification).
- Keep the volume name and have the operator wipe it before the merge: one missed step takes the
  site down, and there is no rollback.
- Stay on PostgreSQL 15: against the clarification.

## R13. Broker image: `redis:8.10.2-alpine` (PR 3)

**Findings**:
- `8.10.2-alpine` is the newest Redis 8 release, and it is multi-architecture.
- kombu 5.6.2 with redis-py 6.4.0 supports Redis 8.
- The server flags `--appendonly yes --appendfsync always --maxmemory-policy noeviction` still
  apply.
- Redis 8 is licensed under RSALv2, SSPLv1 or AGPLv3. Running the unmodified image ourselves is
  allowed under any of them.
- Redis 8 images bundle the query, JSON and time-series modules, so their idle memory may be
  slightly higher. The CI 4 GiB budget check and the Pi measurement cover this.

**Decision**: Use `redis:8.10.2-alpine` on a **new volume** named `redisdata8`. The broker starts
with an empty queue, as FR-022 requires: old events would point at users of the dropped database.
The old `redisdata` volume is kept for rollback until the operator deletes it.

**Alternatives considered**: Valkey. The constitution allows any Redis-compatible broker, but the
clarification names Redis, and replacing the broker is a component change outside this feature.

## R14. One-time reset on the Raspberry Pi (PR 3)

**Decision**: These ordered steps go in the operator guide; the contract is
[contracts/service-images.md](contracts/service-images.md) §Reset.

1. **Check** that the current database holds only seed data. The only users are the four seeded
   e-mails, and the book and order counts match a freshly seeded development stack. If not,
   **stop**: the reset is not allowed (spec edge case).
2. **Before the merge**, set `DJANGO_SEED=true` in the Portainer stack. On the current database
   this does nothing, because seeding skips once users exist.
3. **Merge** PR 3. The webhook redeploys onto `pgdata18` and `redisdata8`. `web` runs the
   migrations, seeds, re-encodes every book with the current model and then serves.
4. **Replace** the demo passwords, as the guide's existing seeding warning describes, then set
   `DJANGO_SEED=false` again.
5. **Verify** with SC-009: record counts match the seed, search finds every seeded book, and the
   Pi measurement passes.
6. **Delete** the old `<stack>_pgdata` and `<stack>_redisdata` volumes. Once they are gone, a
   rollback means another reset.

**Development stacks**: CI starts from nothing on every run (`down -v`). Local developers get the
new volumes, and `DJANGO_SEED` defaults to `true` in `docker-compose-dev.yml`, so the new stack
seeds itself. The README tells them to remove the two old volumes.

## R15. Constitution amendments and delivery

- **PR 1** carries the v2.1.0 amendment already in the working tree: the Django 5.2 LTS line, a
  single dependency list, and patch releases treated as routine.
- **PR 3** changes the Database line from "PostgreSQL 15" to "PostgreSQL 18". This is a platform
  constraint change, so MINOR, giving **v2.2.0** (FR-017).
- **PR 2** names no tool versions in the constitution and does not amend it.
- **Branches**:
  - PR 1: `chore/kan-17-django-5.2-lts`, the current branch.
  - PR 2: `chore/lint-tools-latest`, from `main` after PR 1 merges.
  - PR 3: `chore/service-images-pg18-redis8`, from `main` after PR 2 merges.

  Each PR adds its own changelog entry (FR-018). After PR 1 merges, close Dependabot's
  `django-5.2.17` and `djangorestframework-3.17.2` branches.

## Measurements

### After PR 1 (Django 5.2.18, #30), Raspberry Pi 5

Taken with the operator guide's "Measure the stack on the Pi", `scripts/smoke_stack_budget.py`
(SC-005):

```json
{
  "project": "library-django",
  "containers": 4,
  "peak_memory_gib": 2.645,
  "search_ms": {"count": 60, "p50": 170.6, "p95": 219.4},
  "save_ms": {"count": 5, "p50": 155.8, "p95": 171.2},
  "vectors_current": "9/9",
  "clients": 3,
  "result": "PASS"
}
```

All targets are met: 2.645 GiB of 4 GiB, search p95 219 ms against 500 ms, and book save p95
171 ms against 2 s. The Django 4.1 stack measured 2.45 GiB, search p95 237 ms and save p95 199 ms
(feature 001, R1), so memory rose slightly and latency improved. The superseded Dependabot pull
requests are closed, and KAN-17 is Done.

### After PR 3 (PostgreSQL 18 and Redis 8, #32), Raspberry Pi 5

The stack was measured after the one-time reset and reseed (SC-005, SC-009):

```json
{
  "project": "library-django",
  "containers": 4,
  "peak_memory_gib": 2.669,
  "search_ms": {"count": 60, "p50": 167.5, "p95": 242.6},
  "save_ms": {"count": 5, "p50": 155.9, "p95": 173.3},
  "vectors_current": "9/9",
  "clients": 3,
  "result": "PASS"
}
```

All targets are met: 2.669 GiB of 4 GiB, search p95 243 ms against 500 ms, and book save p95
173 ms against 2 s. Every seeded book has a vector from the current model. Compared with the
PostgreSQL 15 and Redis 7.4 stack after PR 1 (2.645 GiB, 219 ms, 171 ms), memory and latency are
practically unchanged.

The operator confirmed every step of the one-time reset: the seed-only check passed, the demo
passwords were replaced, `DJANGO_SEED=false` was set and the site brought back online, and the
old `pgdata` and `redisdata` volumes were deleted.

### Success criteria evidence (T045)

| Criterion | Evidence |
|---|---|
| SC-001 tests pass, none weakened | 156 → 159 tests OK locally with real-model tests; #30, #31 and #32 merged through the required `lint` and `smoke-test` checks |
| SC-002 no project-code deprecation warnings | `deprecations.md`: none, from project or third-party code |
| SC-003 data and sign-in survive | In-place upgrade over a 4.1 database: counts `4\|8\|9\|3\|0\|9` unchanged; hash re-encoded to 1,000,000 iterations |
| SC-004 API unchanged | `/api/schema/` byte-identical to the 4.1 baseline |
| SC-005 Pi targets | Met after #30 (2.645 GiB, p95 219 ms) and after #32 (2.669 GiB, p95 243 ms) |
| SC-006 supported until April 2028 | Django 5.2.18 LTS |
| SC-007 one dependency list | `library/requirements.txt` removed; fresh venv installs in one step |
| SC-008 current lint tools, no findings | black 26.10.1 and ruff 0.17.1: 0 findings, no code changes |
| SC-009 reset on the Pi | Seed-only check passed; 9/9 vectors current; demo passwords replaced; budget check PASS |
