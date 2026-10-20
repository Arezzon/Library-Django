---

description: "Task list for the Django 5.2 LTS upgrade and dependency refresh"
---

# Tasks: Django 5.2 LTS Upgrade and Dependency Refresh

**Input**: Design documents from `specs/002-django-lts-upgrade/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included. Constitution Principle III (non-negotiable) requires every behavior change
to ship with Django tests that fail without it. Write each test task first and confirm it fails
before the implementation task that follows it. Where a test is a regression guard that passes
before the change as well, the task says so.

**Organization**: The work ships as three pull requests, merged in order (FR-025):

| Pull request | Phases | Stories |
|---|---|---|
| **PR 1**: runtime dependencies (KAN-17) | Phases 1–6 | US1–US3 |
| **PR 2**: lint and format tools | Phase 7 | US4 |
| **PR 3**: database and broker images | Phase 8 | US5 |

Phase 9 covers the checks that span the whole feature.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US5, as in spec.md)
- Paths are relative to the repository root. Django commands run from `library/`, inside the
  `web` service of `docker-compose-dev.yml` unless a task says otherwise.
- `DC` means `docker compose -f docker-compose-dev.yml`, as in quickstart.md.

---

## Phase 1: Setup (PR 1 branch and baselines)

**Purpose**: Start PR 1 from a current base, confirm the target versions, and record the pre-upgrade
API schema and data while the old pins are still installed.

- [x] T001 Verify the PR 1 branch `chore/kan-17-django-5.2-lts` with the `.agents/skills/fresh-feature-branch/SKILL.md` procedure:
  - run `git fetch origin main`;
  - confirm that the only commits on top of `origin/main` are the constitution v2.1.0 amendment (`docs(constitution): …`), and that the working tree adds only `specs/002-django-lts-upgrade/` and the bridge files (`.specify/superpowers-handoff.json`, `.specify/bridge-events.jsonl`, `.specify/bridge-snapshots/…`). `.specify/feature.json` is gitignored;
  - if `origin/main` has moved, rebase onto it;
  - leave other branches untouched.
- [x] T002 Re-check the target versions with quickstart.md §1, and wherever a newer release exists, replace the versions in the R1 table of `specs/002-django-lts-upgrade/research.md`:
  - Django: newest `5.2.x` only;
  - every other direct package (contracts/runtime-dependencies.md): newest release;
  - `pgvector/pgvector` and `redis` image tags: record any newer ones for Phase 8.

  Each package left below its latest release keeps a one-line reason in R1 (FR-003).
- [x] T003 Record the baselines before any pin changes, following quickstart.md §2.1 but run on this branch, which still has the old pins (skip the `git switch` lines):
  - start the stack with `$DC up --build -d --wait`;
  - save `GET /api/schema/` to a scratch file `schema-main.yaml` outside the repository;
  - save the six-count query to `counts-main.txt`.

  **Keep the stack's volumes**: T013 upgrades in place over them.

**Checkpoint**: Baseline schema and counts saved; target versions confirmed in research.md R1.

---

## Phase 2: Foundational (the new runtime pins)

**Purpose**: Replace the root `requirements.txt` with the complete pinned set from
[contracts/runtime-dependencies.md](contracts/runtime-dependencies.md). Every PR 1 story depends on
it.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Rewrite `requirements.txt` with the header and the direct group only:
  - **Header comment**: as in the contract's "Format" section. It says the file is "the only runtime dependency list", "Installed by the Dockerfile and by local development (see README)", and how the transitive group is regenerated.
  - **Direct group** under `# --- Direct ---`, with the versions from research R1 (after T002): `Django==5.2.18`, `djangorestframework==3.18.3`, `drf-spectacular==0.30.0`, `psycopg2-binary==2.9.13`, `python-dotenv==1.2.4`, `gunicorn==26.2.0`, `whitenoise==6.12.0`, `pgvector==0.5.1`, `onnxruntime==1.31.0`, `numpy==2.5.4`, `sentencepiece==0.2.2`, `huggingface-hub==2.2.0`, `celery[redis]==5.6.3`, `kombu==5.6.2`, `redis==6.4.0`.
  - **Remove** all other lines, including `pytz` (no longer required) and the old partial transitive pins.
- [x] T005 Generate the transitive group in `requirements.txt` inside a Linux image:
  1. Run `$DC build web`. Changing `requirements.txt` re-runs the model fetch layer, about 0.6 GB.
  2. Run `docker run --rm --entrypoint pip library-django:dev freeze --exclude-editable`.
  3. Append every package not already in the direct group under `# --- Transitive (pinned for reproducible builds) ---`, sorted case-insensitively. The freeze shows `celery==5.6.3` without `[redis]`, and that counts as the direct pin.
  4. Data-model §1 rules: "Every line is `name==version`", "No package appears twice", and the group "contains no Windows-only packages such as `colorama`, and no orphans such as `pytz`".
  5. Rebuild with `$DC build web`, then run `docker run --rm --entrypoint pip library-django:dev check`. **Expected**: "No broken requirements found."
- [x] T006 Verify the complete file resolves to wheels on both architectures from a Linux environment, so platform markers match the image. From the repository root, run:

  ```bash
  for arch in x86_64 aarch64; do
    docker run --rm -v "$PWD:/w" -w /w python:3.12-slim \
      pip install --dry-run --ignore-installed --only-binary=:all: \
        --python-version 3.12 --implementation cp \
        --platform manylinux_2_17_$arch --platform manylinux_2_28_$arch --platform manylinux_2_34_$arch \
        --target /tmp/t -r requirements.txt 2>&1 | tail -1
  done
  ```

  **Expected**: both runs print the same "Would install" set, and it equals the packages in `requirements.txt`.

**Checkpoint**: `requirements.txt` holds the complete pinned set. The image builds and `pip check` passes.

---

## Phase 3: User Story 1 - The library keeps working on a security-supported framework (Priority: P1) 🎯 MVP

**Goal**: The site, its data and its API behave exactly as before, on Django 5.2 LTS with every
runtime dependency current (FR-001–FR-009, FR-013, FR-014).

**Independent Test**: The full suite and the CI checks pass on both architectures. An in-place
upgrade over the baseline data keeps every record and lets existing accounts sign in. The OpenAPI
schema matches `main` under [contracts/api-compatibility.md](contracts/api-compatibility.md).

### Tests for User Story 1 (write first) ⚠️

- [x] T007 [P] [US1] In `library/authentication/tests.py`, add `StaticFilesStorageTests(SimpleTestCase)` (FR-008, FR-011). It asserts:
  - `settings.STORAGES["staticfiles"]["BACKEND"] == "whitenoise.storage.CompressedManifestStaticFilesStorage"`;
  - `settings.STORAGES["default"]["BACKEND"] == "django.core.files.storage.FileSystemStorage"`;
  - `django.core.files.storage.storages["staticfiles"]` is an instance of `whitenoise.storage.CompressedManifestStaticFilesStorage`.

  Run it with `$DC exec -T web python manage.py test authentication.tests.StaticFilesStorageTests`. It must **fail** on the new pins before T010, because Django 5.2 ignores `STATICFILES_STORAGE`.
- [x] T008 [P] [US1] In `library/authentication/tests.py`, add `MigrationStateTests(TestCase)` (FR-009). It calls `django.core.management.call_command("makemigrations", check=True, dry_run=True, stdout=io.StringIO())`. A `SystemExit` means a missing migration: catch it and fail with the captured output. It must be a `TestCase`, not a `SimpleTestCase`, because `makemigrations` reads the database's migration history. It must **fail** before T011, which reports `authentication 0003` and `order 0003` as missing.
- [x] T009 [P] [US1] In `library/authentication/tests.py`, add `PasswordHashUpgradeTests(TestCase)` (FR-007, SC-003). It:
  1. creates a user with `CustomUser.objects.create_user(email="old-hash@example.com", password="unused", first_name="Old", middle_name="", last_name="Hash", is_active=True)`. `is_active` defaults to `False`, and an inactive user cannot sign in. The call matches `ProxyLoginTests.setUp` in the same file;
  2. replaces `user.password` with `PBKDF2PasswordHasher().encode("old-hash-pass-123", PBKDF2PasswordHasher().salt(), iterations=390000)` and saves (390,000 is the Django 4.1 default);
  3. asserts `self.client.login(email=user.email, password="old-hash-pass-123")` is `True`;
  4. asserts that after `refresh_from_db()`, `user.password.split("$")[1] == str(PBKDF2PasswordHasher.iterations)`.

  This is a regression guard: it passes on both old and new pins. Record that in the docstring.

### Implementation for User Story 1

- [x] T010 [US1] In `library/library/settings.py` (FR-008, FR-011):
  1. Replace `STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"` with:

     ```python
     STORAGES = {
         "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
         "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
     }
     ```

     Keep the "Let WhiteNoise compress and cache static assets" comment above it.
  2. Delete `USE_L10N = True`.
  3. Change every `https://docs.djangoproject.com/en/3.1/` link in the file to `/en/5.2/`.

  Leave the `DB_ENGINE` default `django.db.backends.postgresql_psycopg2` unchanged: research R3 confirms Django 5.2 still maps it. T007 must now pass.
- [x] T011 [US1] Generate the two migrations that predate the upgrade (FR-009; research R4; data-model §2). Run `$DC exec -T web python manage.py makemigrations authentication order` and commit the two files unedited:
  - `library/authentication/migrations/0003_alter_customuser_role.py`, holding `AlterField role: IntegerField(choices=[(0, 'visitor'), (1, 'librarian')], default=0)`;
  - `library/order/migrations/0003_alter_order_id.py`, holding `AlterField id: BigAutoField`.

  Do not touch `0001`/`0002`. Migrations are excluded from ruff and black. T008 must now pass.
- [x] T012 [P] [US1] Update the framework doc links in the module docstrings, from `https://docs.djangoproject.com/en/4.0/` to `/en/5.2/`. The files are `library/library/urls.py`, `library/library/wsgi.py` and `library/library/asgi.py`. Comment-only change.
- [x] T013 [US1] Upgrade in place over the T003 baseline volumes and verify, per quickstart.md §2.2 (FR-006, FR-007, SC-003):
  - `$DC up --build -d --wait` with no `down -v`;
  - the `web` log shows `Applying authentication.0003…` and `Applying order.0003…`;
  - the six counts `diff` cleanly against `counts-main.txt`;
  - the shell check prints `True 1000000`.
- [x] T014 [US1] Compare the API schema, per quickstart.md §2.3 and [contracts/api-compatibility.md](contracts/api-compatibility.md) (FR-005, SC-004):
  - save `schema-branch.yaml` and `diff -u` it against `schema-main.yaml`;
  - fix every difference the contract calls breaking in the owning app's serializer or view, never by editing tests;
  - list each allowed difference, one line with its reason, in a scratch note for the PR description (T026).
- [x] T015 [US1] Run the full suite as CI does, per quickstart.md §2.4, with `RUN_BOOK_EMBEDDING_MODEL_TESTS=1 CELERY_TASK_ALWAYS_EAGER=True` (FR-004, SC-001):
  - every test passes, including T007–T009 and the 18-query evaluation set;
  - fix failures in application code; tests change only where a framework API they call changed, and they still verify the same behavior (FR-004);
  - if the evaluation set fails on onnxruntime 1.31.0, step down to the highest onnxruntime release that passes and record why in research R1 and R9 (FR-003).
- [x] T016 [US1] Run quickstart.md §2.6 (FR-008, FR-009):
  - `staticfiles/staticfiles.json` exists after `collectstatic`;
  - `makemigrations --check --dry-run` prints "No changes detected";
  - `check --deploy --fail-level ERROR` passes.

  Also run the CI-only checks locally, as in `.github/workflows/docker-build.yml`:
  - `$DC exec -T web python manage.py smoke_test_tracking`;
  - `python scripts/smoke_tracking_recovery.py --compose-file docker-compose-dev.yml`;
  - `python scripts/smoke_stack_budget.py --compose-file docker-compose-dev.yml --max-memory-gib 4` (FR-013).

**Checkpoint**: US1 is complete. Django 5.2 runs on the old data, the API is unchanged, and every
test and smoke check passes.

---

## Phase 4: User Story 2 - Maintainers start from a clean deprecation baseline (Priority: P2)

**Goal**: The project's code and configuration raise no deprecation warnings, and every
third-party warning is documented (FR-010–FR-012).

**Independent Test**: quickstart.md §2.5 reports no warning from `/app/library` or
`/app/scripts`, and every remaining warning appears in `deprecations.md`.

- [x] T017 [US2] Collect the warnings with quickstart.md §2.5 (`PYTHONWARNINGS=always::DeprecationWarning,always::PendingDeprecationWarning`) into a scratch `warnings.txt`. For every line whose path starts with `/app/library/` or `/app/scripts/`, fix the code at that file and line so the warning stops, without changing behavior (FR-010). Re-run until `grep -E "/app/(library|scripts)/" warnings.txt` prints nothing, then re-run T015.
- [x] T018 [US2] Confirm that no setting the framework removed is still set (FR-011, US2 acceptance 3). Run:

  ```bash
  git grep -nE "USE_L10N|STATICFILES_STORAGE|DEFAULT_FILE_STORAGE|USE_DEPRECATED_PYTZ|CSRF_COOKIE_MASKED|FORMS_URLFIELD_ASSUME_HTTPS" -- library/library/settings.py
  ```

  **Expected**: no matches.
- [x] T019 [US2] Create `specs/002-django-lts-upgrade/deprecations.md` (FR-012; data-model §5):
  - **Opening**: the date, the Django version and the exact command used in T017.
  - **Table**: one row per distinct remaining warning, with the columns `Warning | Raised by | Removed in | Expected resolution` ("Warning" is the category and message; "Raised by" is the package and module).
  - **If none remain**: state "No deprecation warnings remain" instead of the table.

**Checkpoint**: US2 complete — zero project-code deprecation warnings; third-party ones recorded.

---

## Phase 5: User Story 3 - One runtime dependency list for every environment (Priority: P3)

**Goal**: The root `requirements.txt` is the only runtime list, and every current document points to
it (FR-015, FR-016).

**Independent Test**: quickstart.md §2.7. `library/requirements.txt` is gone, `git grep` finds no
current reference to it, and a fresh virtual environment installs from the root list in one step.

- [x] T020 [P] [US3] Delete the duplicate list with `git rm library/requirements.txt` (FR-015).
- [x] T021 [P] [US3] In `README.md`, make the local setup point to the root list (FR-016):
  - **line 154 (Windows)**: change `python -m pip install -r .\library\requirements.txt` to `python -m pip install -r .\requirements.txt`;
  - **line 164 (Linux/macOS)**: change `./library/requirements.txt` to `./requirements.txt`;
  - **after the two code blocks**: add one sentence: environments installed from the old `library/requirements.txt` should be reinstalled from `requirements.txt`;
  - **Project layout (line 489)**: change the `requirements.txt` comment to `# runtime dependencies: image build and local development`.
- [x] T022 [US3] Verify with quickstart.md §2.7:
  - `test ! -e library/requirements.txt`;
  - the `git grep -n "library/requirements.txt" -- ':!specs/001-*' ':!specs/002-*' ':!.specify/bridge-snapshots' ':!docs/shared/changelog.md'` finds nothing;
  - `AGENTS.md` and `.specify/memory/constitution.md` (v2.1.0) no longer require a second copy (US3 acceptance 3);
  - **(manual)** in a fresh virtual environment, `python -m pip install -r requirements.txt` succeeds in one step (SC-007).

**Checkpoint**: US3 complete — one dependency list.

---

## Phase 6: PR 1 wrap-up

**Purpose**: The documentation, changelog, checks and pull request for PR 1 (FR-018), and the
post-merge steps.

- [x] T023 In `README.md` line 5, change "built with **Django 4.1**" to "built with **Django 5.2 LTS**" (FR-018). Run this after T021, which edits the same file.
- [x] T024 [P] Add the PR 1 entry at the top of `docs/shared/changelog.md`, in the existing format (date line `2026-10-20` or the merge date, a title line, one paragraph). The title is "Django 5.2 LTS and current runtime dependencies (KAN-17)". The paragraph covers:
  - Django 4.1 → 5.2.x, with every runtime dependency at its latest compatible release (redis-py capped by kombu);
  - the complete pinned set in the single root `requirements.txt`, and `library/requirements.txt` removed;
  - `STORAGES` replacing the removed `STATICFILES_STORAGE`;
  - the two migrations that had never been generated (`role` label, `order.id` to `bigint`);
  - the deprecation baseline;
  - constitution v2.1.0 (Django 5.2 LTS line, single dependency list, patch releases routine).
- [x] T025 From the repository root, run `ruff check .` and `black --check .` with the `requirements-dev.txt` pins, and fix every finding.
- [x] T026 Commit and open PR 1:
  - **Commit**: follow `.agents/skills/preview-commit/SKILL.md`.
  - **Push and PR**: follow `.agents/skills/preview-pr/SKILL.md`, with the title `chore(deps): upgrade Django to 5.2 LTS and refresh runtime dependencies`.
  - **PR description**: follows `.github/PULL_REQUEST_TEMPLATE.md`. It includes the R1 version table, the allowed schema differences from T014, the `deprecations.md` summary, and a note that it supersedes Dependabot's `django-5.2.17` and `djangorestframework-3.17.2` pull requests.
  - **Merge gate**: wait for `lint`, `smoke-test` on both architectures, and CodeQL.
- [x] T027 After PR 1 merges and the Pi has redeployed (manual):
  - run the operator guide's "Measure the stack on the Pi" (quickstart.md §2.9, SC-005) and append the JSON summary to a new "Measurements" section at the end of `specs/002-django-lts-upgrade/research.md`;
  - close the superseded Dependabot pull requests with `gh pr close` and a comment linking PR 1;
  - the assignee moves KAN-17 to Done.

**Checkpoint**: PR 1 is merged and deployed. KAN-17 is complete.

---

## Phase 7: User Story 4 - Maintainers lint and format with current tools (Priority: P4) — PR 2

**Goal**: black and ruff at their latest releases, with the code passing them and no behavior change
(FR-019, FR-020).

**Independent Test**: quickstart.md §3. Lint and format report nothing, and the suite passes with no
test assertion changed (SC-008).

- [x] T028 [US4] After PR 1 has merged, create `chore/lint-tools-latest` from a freshly fetched `origin/main`, following `.agents/skills/fresh-feature-branch/SKILL.md`.
- [x] T029 [US4] In `requirements-dev.txt`, set `black` and `ruff` to their newest releases (`python -m pip index versions black` and `… ruff`). On 2026-10-20 these are `black==26.10.1` and `ruff==0.17.1` (research R11). Keep the file's header comment.
- [x] T030 [US4] Install the new pins (`python -m pip install -r requirements-dev.txt`) and run `ruff check .` and `black --check .` from the root:
  - **Findings**: apply `ruff check --fix .` and `black .`, then fix the rest by hand without changing behavior.
  - **A finding that cannot be fixed without a behavior change**: suppress it at that line with `# noqa: <code>`, followed by the reason.
  - **`pyproject.toml`**: change it only if the tools warn about a renamed or removed setting or rule (FR-020).
- [x] T031 [US4] Run the full suite as in quickstart.md §2.4. Every test passes with no test assertion changed (SC-008).
- [ ] T032 [US4] Finish PR 2:
  - add a changelog entry at the top of `docs/shared/changelog.md` ("Current lint and format tools": versions, plus "no code changes needed" or a summary of the fixes);
  - commit with the preview-commit skill;
  - open the PR with the preview-pr skill, titled `chore(ci): bump black and ruff to their latest releases`;
  - wait for the CI gates and merge.

**Checkpoint**: PR 2 is merged. The lint tools are current.

---

## Phase 8: User Story 5 - The database and message broker run on current releases (Priority: P5) — PR 3

**Goal**: PostgreSQL 18 with pgvector and Redis 8 in both stacks. The server's seed-only data is
reset and reseeded through new volumes, with the old ones kept for rollback (FR-021–FR-024,
FR-017).

**Independent Test**: quickstart.md §4. The fresh development stack runs PostgreSQL 18.x and Redis
8.10.x, every CI check passes, and the local rehearsal shows the reset and the rollback. On the
Pi, SC-009 holds.

### Setup for User Story 5

- [ ] T033 [US5] After PR 2 has merged, create `chore/service-images-pg18-redis8` from a freshly fetched `origin/main`, following `.agents/skills/fresh-feature-branch/SKILL.md`. Re-check the newest `pgvector/pgvector:<ver>-pg<major>` and `redis:<ver>-alpine` tags on Docker Hub, and confirm both publish `amd64` and `arm64`. Use any newer tag in place of `0.8.7-pg18` and `8.10.2-alpine` everywhere below and in `contracts/service-images.md`.

### Tests for User Story 5 (write first) ⚠️

- [ ] T034 [US5] In `library/authentication/tests.py`, add `ComposeServiceImagesTests(SimpleTestCase)` (FR-021). It loads `docker-compose.yml` and `docker-compose-dev.yml` from `settings.BASE_DIR.parent` with `yaml.safe_load` (PyYAML is pinned), then asserts:
  - `services.db.image` and `services.redis.image` are equal across the two files;
  - the `db` image matches `^pgvector/pgvector:\d+\.\d+\.\d+-pg\d+$` and the `redis` image matches `^redis:\d+\.\d+\.\d+-alpine$` (exact tags, no floating tags);
  - `db` mounts `pgdata18:/var/lib/postgresql` and `redis` mounts `redisdata8:/data`;
  - the top-level `volumes` contain `pgdata18` and `redisdata8` and no longer `pgdata` or `redisdata`.

  The image bakes the Compose files into `/app` (`COPY . /app`), so rebuild with `$DC build web` before running. It must **fail** before T035.

### Implementation for User Story 5

- [ ] T035 [US5] In `docker-compose.yml`:
  - **`db`**: set `image: pgvector/pgvector:0.8.7-pg18` and change the volume to `pgdata18:/var/lib/postgresql`. PostgreSQL 18 images keep data in `/var/lib/postgresql/18/docker` and exit if a volume sits at `/var/lib/postgresql/data` (research R12).
  - **`redis`**: set `image: redis:8.10.2-alpine` and change the volume to `redisdata8:/data`. Keep its `command` and healthcheck.
  - **Top-level `volumes`**: replace `pgdata:` and `redisdata:` with `pgdata18:` and `redisdata8:`.
  - **Comment**: add one line above the volumes, saying they are new so the move to PostgreSQL 18 starts from empty data, and pointing to the operator guide's reset section.
- [ ] T036 [US5] Make the same image, volume and mount changes in `docker-compose-dev.yml`. Leave the `web` and `worker` source mounts (`./library:/app/library`) unchanged. Rebuild and confirm T034 passes.
- [ ] T037 [US5] Validate per quickstart.md §4.1 and §4.2:
  - `SECRET_KEY=placeholder DB_PASSWORD=placeholder docker compose -f docker-compose.yml config --quiet`, as CI does;
  - `$DC up --build -d --wait` on the new volumes;
  - `select version()` reports PostgreSQL 18.x and `redis-server --version` reports 8.10.x;
  - note the fresh-seed author, book and order counts (the reference values for T039 and T042);
  - the full suite (quickstart.md §2.4), `smoke_test_tracking`, `smoke_tracking_recovery.py` and `smoke_stack_budget.py --max-memory-gib 4` all pass.
- [ ] T038 [US5] **(manual)** Rehearse the reset and rollback locally, per quickstart.md §4.3:
  1. On `main` (`pgdata`), add one book.
  2. Switch to the PR 3 branch: the site is freshly seeded and the book is absent.
  3. Switch back to `main`: the book is present.

  Then clean up the old local volumes.
- [ ] T039 [P] [US5] In `docs/deployment/raspberry-pi-portainer.md`:
  - **New section** "Upgrade to PostgreSQL 18 and Redis 8 (one-time reset)", listed in the Contents. It contains [contracts/service-images.md](contracts/service-images.md) §Reset steps 1–6, with the commands verbatim and the step 1 expected counts filled in from T037. It must open with the step 1 check and its instruction to stop if the check fails (FR-024).
  - **Line 107**: replace "remove the `pgdata` volume" with `pgdata18`.
  - **Line 193 ("Backup and restore")**: name `pgdata18` and `redisdata8`, and add one sentence on where PostgreSQL 18 keeps its data (`/var/lib/postgresql/18/docker`).
- [ ] T040 [P] [US5] In `README.md`:
  - **Line 127**: `| \`db\` | PostgreSQL 18 with pgvector | internal \`5432\` |`.
  - **Line 128**: name Redis 8: "Celery broker (Redis 8) with persistent AOF storage".
  - **Quick start with Docker**: add one sentence saying the stack now uses the volumes `pgdata18` and `redisdata8`, and that the old `<project>_pgdata` and `<project>_redisdata` volumes can be removed with `docker volume rm`.
  - **Line 229**: check that the "PostgreSQL 18" wording for local installs still matches.
- [ ] T041 [US5] Amend the constitution with `/speckit-constitution` (FR-017):
  - in `.specify/memory/constitution.md` Technology & Platform Constraints, change "**Database**: PostgreSQL 15 with the `vector` extension" to "PostgreSQL 18 with the `vector` extension";
  - bump the version from 2.1.0 to **2.2.0** (MINOR: platform constraint updated) and set Last Amended to the PR date;
  - remove the Sync Impact Report comment before committing.
- [ ] T042 [US5] Finish PR 3:
  - **Changelog** entry at the top of `docs/shared/changelog.md`, titled "PostgreSQL 18 and Redis 8": the images, the new volumes, the one-time seed-only reset, and constitution v2.2.0.
  - **Commit** with the preview-commit skill.
  - **PR** with the preview-pr skill, titled `chore(deploy): move to PostgreSQL 18 and Redis 8 images`.
  - **PR description**: a "Before merging" checklist covering reset steps 1–2 (seed-only check passed, `DJANGO_SEED=true` saved in Portainer). Merge only after the operator confirms both.
- [ ] T043 [US5] **(manual, operator)** After the merge, finish the reset on the Pi with steps 3–6 of the guide's new section (SC-009):
  - confirm the redeploy;
  - replace the demo passwords and set `DJANGO_SEED=false`;
  - verify the counts, that no book lacks a vector, the searches, and `smoke_stack_budget.py`;
  - then delete `library_pgdata` and `library_redisdata`.

  Append the counts and the budget JSON to the "Measurements" section of `specs/002-django-lts-upgrade/research.md`.

**Checkpoint**: PR 3 is merged and the Pi runs PostgreSQL 18 and Redis 8 on fresh seed data. All
five stories are done.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Consistency checks across the whole feature after PR 3.

- [ ] T044 Search the current documents for stale versions and names:

  ```bash
  git grep -nE "Django 4\.1|PostgreSQL 15|redis:7\.|0\.8\.2-pg15|\bpgdata\b|\bredisdata\b|library/requirements\.txt" -- ':!specs/001-*' ':!specs/002-*' ':!.specify/bridge-snapshots' ':!docs/shared/changelog.md'
  ```

  **Expected**: no matches. Fix any hit in its file in a follow-up commit on the PR 3 branch, or in a small docs PR if PR 3 has merged.
- [ ] T045 Re-read `specs/002-django-lts-upgrade/spec.md` success criteria SC-001–SC-009 against the evidence:
  - CI runs of PRs 1–3;
  - the T013 and T014 outputs;
  - `deprecations.md`;
  - the "Measurements" section in `research.md`.

  Mark the spec's **Status** as `Implemented` once every criterion has evidence.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies. T003 must run before T004 changes any pin.
- **Foundational (Phase 2)**: Depends on Setup. It blocks US1, US2 and US3.
- **US1 (Phase 3)**: Depends on Phase 2.
- **US2 (Phase 4)**: Depends on US1's T010–T011 (settings and migrations in place), and re-runs T015 at the end.
- **US3 (Phase 5)**: Depends on Phase 2 only (the root list must be complete before the duplicate is deleted). It can run in parallel with US1 and US2.
- **PR 1 wrap-up (Phase 6)**: Depends on US1–US3.
- **US4 (Phase 7, PR 2)**: Depends on PR 1 being merged (T026), because it branches from the updated `main`.
- **US5 (Phase 8, PR 3)**: Depends on PR 2 being merged (T032). It needs Django 5.2 on `main`, which supports PostgreSQL 18.
- **Polish (Phase 9)**: Depends on PR 3.

### User Story Dependencies

- **US1 (P1)**: The MVP. Needs only Foundational.
- **US2 (P2)**: Builds on US1's settings change; independently verifiable with quickstart.md §2.5.
- **US3 (P3)**: Independent of US1 and US2 apart from the shared Foundational phase.
- **US4 (P4)**: Independent of the code changes, but merged after PR 1 by the delivery order (FR-025).
- **US5 (P5)**: Merged last (FR-025). Its reset relies on the seed script and migrations as they are on `main` after PR 1.

### Within Each User Story

- Test tasks (T007–T009, T034) come first and must fail before their implementation task, except T009, which is a regression guard.
- Settings and migrations (T010, T011) before the in-place upgrade (T013) and the full run (T015).
- Compose changes (T035, T036) before validation (T037) and the documentation that quotes T037's counts (T039).

### Parallel Opportunities

- T007, T008 and T009 add separate test classes. They can be written in parallel, but they touch the same file, so merge them carefully, or write them in sequence if one person does all three.
- T012 (docstrings) can run alongside T010 and T011.
- US3 (T020, T021) can run alongside US1 once Phase 2 is done.
- T024 (changelog) can run alongside T023.
- T039 (guide) and T040 (README) can run in parallel after T037.

---

## Parallel Example: PR 1 after Phase 2

```bash
# Write the three US1 tests (same file: coordinate the edits):
Task: "StaticFilesStorageTests in library/authentication/tests.py"
Task: "MigrationStateTests in library/authentication/tests.py"
Task: "PasswordHashUpgradeTests in library/authentication/tests.py"

# Meanwhile, on other files:
Task: "Update doc links in library/library/urls.py, wsgi.py, asgi.py"   # T012
Task: "git rm library/requirements.txt"                                  # T020
Task: "Point README local setup to the root requirements.txt"            # T021
```

## Parallel Example: User Story 5 after T037

```bash
Task: "Add the one-time reset section to docs/deployment/raspberry-pi-portainer.md"   # T039
Task: "Update README service table and old-volume note"                              # T040
```

---

## Implementation Strategy

### MVP first (User Story 1)

1. Phase 1, then Phase 2: the complete pinned set builds.
2. Phase 3 (US1): settings, migrations, then the in-place upgrade, the schema comparison and the
   full suite. **Stop and validate.** This alone removes KAN-17's security risk.
3. Add US2 (deprecation baseline) and US3 (single list), then Phase 6. PR 1 merges and KAN-17 is
   done.

### Incremental delivery

1. **PR 1** (US1–US3): deploys automatically with no operator step (FR-014). Measure it on the Pi
   (T027).
2. **PR 2** (US4): the lint tool pins, plus any fixes. It deploys with no operator step and changes
   no behavior.
3. **PR 3** (US5): needs the operator's steps 1–2 before the merge and steps 3–6 after it. The old
   volumes stay until verification, so a revert restores the previous stack exactly.

---

## Notes

- [P] tasks touch different files and have no dependencies on incomplete tasks.
- Commit after each task or logical group. PR boundaries are strict: nothing from Phase 7 or 8 goes
  into PR 1 (constitution workflow item 6).
- Versions in this file are the 2026-10-20 values. T002 and T033 replace them if newer releases
  exist.
- Never edit an existing migration. Never weaken a test to make the upgrade pass.
