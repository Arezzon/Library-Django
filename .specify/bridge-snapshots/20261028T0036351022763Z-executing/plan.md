# Implementation Plan: Close the Priority Technical Debt of v1.0

**Branch**: one per pull request (FR-062), named in [research.md](research.md) R1. This folder stays
untracked until PR 1 is deployed (FR-060). | **Date**: 2026-10-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-priority-tech-debt/spec.md`

## Summary

KAN-62 closes only when the priority debt of v1.0 is verified, not merely planned. The work ships as
12 pull requests (PRs) and 3 repository settings (FR-059). The recommended merge order is:

1. PR 1;
2. PRs 2, 3 and 9, in any order;
3. PR 8;
4. PRs 4 to 7;
5. PR 11;
6. PR 10;
7. PR 12.

The reasons for this order are in R1.

**PR 1, access control (KAN-24, KAN-62).** It is merged and deployed first, and nothing describing
the gap is published before that (R1 to R7).
- **Default refusal**: an API view that declares no audience refuses everyone. Every view declares
  one.
- **Clearer refusals**: the API accepts session sign-in only, and answers 401 when signing in is
  needed and 403 when the role is wrong. Web pages refuse with a 403 page.
- **Roles**: sign-up always creates a reader. One rule decides who may change a role or an account's
  status.
- **Schema**: it labels each operation's audience.
- **Automated clients**: CI's endpoint checks and the Pi measurement script sign in.

**PR 2, query counts (KAN-18).** Every list gets a test showing the same query count for 1 and 50
rows. The author API stops reading each author's books separately. The catalog's p95 is measured on
the Pi (R8).

**PR 3, tests and coverage (KAN-21).**
- Tests for authors, books, every loan change and every web route.
- A report of coverage on added and changed lines, posted on every PR.
- Fixes for two defects found while planning: account creation times that change on every save,
  and negative copy counts (R9).

**PR 4, reservation model (KAN-55).**
- A `Reservation` model in `order`, with four states, its constraints and ADR 0001.
- `PROTECT` on the book foreign keys. Today the API and the admin site delete a book's loans along
  with the book; after PR 4 no channel can (R10).

**PR 5, reserving (KAN-56).**
- Readers reserve through the web and the API.
- Availability also subtracts active reservations.
- One service checks the 3-reservation limit and the overdue block under row locks, taken in the
  order reader, then book.
- A reservation stops holding its copy at the deadline. Celery beat, running inside the existing
  worker, records the expiry.
- Times appear in Kyiv time with the zone (R11 to R13, R16).

**PR 6, issuing at the desk (KAN-57).**
- Librarians issue, lend and cancel with a reason; readers cancel their own reservations.
- A reader sees the library's cancellation the next time they open the site.
- A loan a librarian starts counts as the reader's borrow (R13 to R15).

**PR 7, complete pages (KAN-58).** Finished pages and messages, end-to-end journey tests, and a load
script: a burst of 100 in CI, and 30 concurrent readers on the Pi. It also adds the reservation
documentation (R17).

**PR 8, logs and audit (KAN-67).**
- One log line format with a request id that follows the request into the worker, redaction, and
  rotation to at most 250 MB. `LOG_LEVEL` sets the level.
- A new `audit` app writes each critical change's entry in the same transaction as the change.
- CI checks that no secret or search text reaches any log (R18 to R21).

**PR 9, backups (KAN-68).**
- A `backup` sidecar on the database image takes a daily `pg_dump`, reads it back in full, writes a
  checksum and keeps 7 days, all in a volume of its own.
- CI rehearses a restore on every run.
- The operator guide adds the weekly off-device copy, the restore into a separate database, the
  rehearsal, and the persistence and hosting measurements (R22 to R24).

**PR 10, accessibility (KAN-69).** Fixes for WCAG 2.2 AA, axe checks in CI through Playwright, every
time shown with its zone, keyboard and screen-reader checks, and a walkthrough with people new to the
system (R25).

**PR 11, administrator role (KAN-70).** Only administrators grant or remove the librarian role. The
operator creates the first administrator on the server, and every change is audited (R26).

**PR 12, debt register (KAN-71).** The register with evidence for every item, the README and ADRs
reviewed, and KAN-62 closed with no P1 item open (R28).

**Settings, applied by Arsen.** KAN-72, KAN-73 and KAN-74 make lint, code scanning and code owners'
approval required on `main` (R27).

## Technical Context

**Language/Version**:
- Python 3.12 with Django 5.2.18, DRF 3.18.3 and drf-spectacular 0.30.0;
- POSIX `sh` for `entrypoint.sh` and the backup script;
- Compose YAML;
- Node.js, on the CI runner only, for the accessibility check.

**Primary Dependencies**:
- **Runtime**: unchanged. `requirements.txt` gains no package.
- **CI and development only**:
  - coverage 7.16.2 and diff-cover 10.6.0 in `requirements-dev.txt` (PR 3);
  - Playwright 1.64.0 and @axe-core/playwright 4.13.0 in `scripts/a11y/package-lock.json` (PR 10).
  - Each is the newest release at least two weeks old on 2026-10-27 (R9, R25).
- **Images**: no new image. The backup service runs `pgvector/pgvector:0.8.7-pg18`, the database's
  image (PR 9).
- **Background work**: Celery 5.6.3's beat scheduler runs inside the existing worker (PR 5).

**Storage**: PostgreSQL 18 with pgvector ([data-model.md](data-model.md)).
- **New tables**: `order_reservation` (PR 4) and `audit_auditentry` (PR 8).
- **Migrations that change only Django's state**: `authentication/0004` (`created_at`) and `0005`
  (roles); `book/0005` (copies 0 or more); `Order.book` as `PROTECT`, inside `order/0004`.
- **New volume**: `pgbackups`, for the backup files (PR 9).

**Testing**:
- **Runner**: the Django test runner on PostgreSQL in `docker-compose-dev.yml`. The encoder is
  mocked by default, and the real-model tests run on both architectures, as today.
- **New tests**:
  - access tables over every API operation and web route (PRs 1 and 3);
  - the schema's audience labels;
  - query counts with 1 and 50 rows;
  - races on PostgreSQL, with `TransactionTestCase` and barriers (PRs 5 and 6);
  - end-to-end journeys (PR 7);
  - audit entries, rollback and redaction (PR 8);
  - Compose consistency (PR 9);
  - a template test that every displayed time shows its zone (PR 10).
- **New CI steps**:
  - signed-in endpoint checks (PR 1);
  - the diff-coverage report (PR 3);
  - the reservation burst (PR 7);
  - the log secret scan (PR 8);
  - a backup with a trial restore (PR 9);
  - axe checks (PR 10).
- **On the Pi**:
  - `smoke_stack_budget.py`, which now signs in and times the catalog;
  - `smoke_reservation_load.py`;
  - the restore rehearsal;
  - the persistence and cold-start measurements ([quickstart.md](quickstart.md)).

**Target Platform**:
- Images for `linux/amd64` and `linux/arm64`.
- Production: a Raspberry Pi 5 running a Portainer Business Edition Git stack.
- CI: GitHub-hosted Ubuntu runners for both architectures.

**Project Type**: a web service (a Django monolith with a Celery worker), with its Compose stacks and
CI.

**Performance Goals**:
- Every list at a fixed query count, and 95% of catalog page loads within 2 s on the Pi (SC-010).
- 95% of reserve, issue and cancel operations within 3 s while 30 readers reserve. A burst of 100
  never holds more copies than exist (SC-002, SC-003).
- Search p95 under 500 ms, and the whole stack within 4 GB with everything added running (SC-014).
- Pages served again within 3 minutes of a restart, a redeploy or a reboot (SC-005).
- A restore within 60 minutes. At most 24 hours of data lost while the Pi's storage survives, and 7
  days if it does not (SC-006).

**Constraints**:
- **Dependencies**: no new runtime dependency or image, and no build step for the site.
- **Logs**: at most 500 MB on disk; the design uses 250 MB. No secret, session id or search text
  ever appears in a log line or an audit entry.
- **Migrations**: existing migrations are never edited, and no existing row changes (FR-022).
- **Disclosure**: PR 1 merges and deploys first, and the spec stays off GitHub until then (FR-060).
- **Each PR stands alone**: its own branch, a passing CI run, the PR template, one changelog entry,
  and review by the code owners (FR-062). The site stays usable after every merge (FR-061).
- **Documentation travels with the change**: each PR updates the README, the operator guide and
  `.env.example` wherever it changes behavior, setup or configuration, and the reservation ADR ships
  with the reservation model (FR-057).

**Scale/Scope**:
- **Work items**: 12 PRs and 3 settings.
- **New parts**: 2 tables, 1 app, 1 Compose service, 2 scripts and 3 ADRs.
- **Data**:
  - the demo catalog (tens of books, a handful of accounts), plus whatever people registered on the
    public site;
  - tests use up to 50 rows per list and 20 concurrent contenders;
  - the HTTP burst uses 100.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against the constitution **v2.2.0** (amended 2026-10-20).

| # | Principle / gate | Pre-design | Post-design | Evidence |
|---|---|---|---|---|
| I | Domain-owned apps | PASS | PASS | **Owners**: reservations live in `order`, role rules in `authentication`, availability in `book`. One new app, `audit`, is justified in Complexity Tracking. **One implementation per rule**: `authentication/services.py` (roles, status), `order/services.py` (reserve, lend, issue, cancel, expire), `BookQuerySet.with_availability` and `Book.available_count` (availability), `audit.services.record` (audit). **Project wiring** stays in `library/library/`: logs, the request id, the schema class, the test helper. **API**: reservation operations live under `/api/v1/` and appear in the schema, with `extend_schema` for their actions, query parameters and 409 responses. |
| II | Explicit role-based access | PASS | PASS | **The gap**: the design complies; today's API does not. PR 1 brings it into compliance, as Governance requires for code that predates the constitution. **Declarations**: `DenyAll` is the default, every API view sets `permission_classes`, and every web view uses a decorator. **Tests**: every route has a permitted and a refused caller. **Data changes** use POST with CSRF, including dismissing a notice. **Audit entries** appear only in the admin site, which only librarians reach. PR 11 amends the principle to add administrators. |
| III | Test-backed changes (NON-NEGOTIABLE) | PASS | PASS | **Every PR ships tests that fail without its change**: access tables, query counts, races on PostgreSQL, audit rollback, redaction, backup consistency, the zone template test. **The author app**, which has no tests today, gets them (PR 3). **Encoder and queue**: the encoder is mocked (`FakeEncoderMixin`), Celery tasks run eagerly, and `smoke_test_tracking` checks the real queue, including the request id. **`tracking.js`** is unchanged; the reserve button reuses `data-track-event`. |
| IV | Secrets and safe defaults | PASS | PASS | **Secrets**: none are new, and none has a default. **New settings default to safe values**: `DenyAll`, `LOG_LEVEL=INFO`, and backup settings that are not secrets. **The measurement password** comes from the environment or a prompt, never the command line. **Logs and audit entries** redact (R19), and CI scans the logs for leaks. **Backups** are mode 600, readable only by root, never in the repository or the image. **Demo data**: seeding stays off on the server, and CI uses only the public demo accounts. |
| V | Consistent data, best-effort side effects | PASS | PASS | **Migrations** come from `makemigrations`, and none is edited. **Writes**: reservations, loans and audit entries are written in `transaction.atomic` with row locks, and an audit failure rolls its change back. **Analytics** stays after commit and best effort, and reservations never wait for the broker. **Unchanged**: event idempotency and the vector rules. PR 8 amends the principle to name audit entries. |
| VI | Lean, portable, reproducible deployment | PASS | PASS | **Nothing new to install**: no runtime dependency or image is added. The backup service reuses the database image, and beat runs inside the existing worker. Both are measured against 4 GB and the search target (FR-033, SC-014). **Portability**: both architectures are unchanged. **Starting the stacks**: the development stack still starts from `.env`, because the new variables have defaults; the server stack starts from images and its environment. **Pins**: CI-only tools are pinned in `requirements-dev.txt` and in the `scripts/a11y` lockfile. **Docs**: every PR that changes behavior or configuration updates the README, the operator guide and `.env.example`. |
| — | Platform constraints | PASS | PASS | No component is replaced. `TIME_ZONE` is a setting, not a component. No frontend toolchain is added: the accessibility check runs Node in CI only and builds nothing for the site. |
| — | CI gates (workflow item 4) | PASS | PASS | **Gates**: `lint`, `smoke-test` on both architectures, and CodeQL stay the gates. **New steps in `smoke-test`**: signed-in endpoint checks, the reservation burst, the log scan, the backup and restore check, and the accessibility check. **Ruleset**: KAN-72 to KAN-74 make `lint`, CodeQL and code owners required. **Constitution**: amendments keep item 4 accurate (R29). |
| — | Workflow (items 1, 5 to 8) | PASS | PASS | **Branches**: one fresh branch per PR (R1). **PRs**: titles follow `<action>(<service>): <description>` and name the Jira key; each uses the PR template and adds one changelog entry. **Review**: code owners per path; new owners for `/library/audit/` and `/scripts/a11y/`. **Scope and docs**: each PR keeps its own scope and documentation. **Defects** go through the bug template (FR-053). |
| — | Governance | PASS | PASS | **Amendments** ride with PRs 7 to 11 through `/speckit-constitution`, with the handoff set to `blocked` during each (R29). |

**Gate result: PASS.** The design violates no principle. Complexity Tracking records the
justifications that Principles I and VI require.

## Project Structure

### Documentation (this feature)

```text
specs/003-priority-tech-debt/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0: decisions R1–R30; Measurements, filled in by the PRs
├── data-model.md        # Phase 1: reservation, audit entry, changed models, backup files, migrations
├── quickstart.md        # Phase 1: validation for each pull request, and the procedures on the Pi
├── contracts/
│   ├── access-control.md     # the audience and refusals of every API operation and web route
│   ├── reservations-api.md   # reservation and desk operations, refusal codes and messages
│   ├── logs-and-audit.md     # the log line, request id, redaction, rotation and audit entries
│   ├── backups.md            # the backup service, its files, the weekly copy, restores, rehearsal
│   └── debt-register.md      # the register's columns, statuses, closing rule and first items
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
# PR 1: access control (KAN-24, KAN-62)
library/library/settings.py                  # DenyAll default, session-only API sign-in, schema class
library/library/schema.py                    # new: AutoSchema that adds audiences and refusals
library/library/api_urls.py                  # API index open to anonymous callers
library/library/templates/403.html           # new
library/authentication/permissions.py        # new: DenyAll, IsSignedIn, ReadOnlyOrLibrarian, IsSelfOrLibrarian, IsLibrarian, SessionAuthentication
library/authentication/services.py           # new: may_change_role, may_change_status, update_account
library/authentication/forms.py              # sign-up without role; ProfileForm; UserUpdateForm
library/authentication/views.py              # profile form chosen by the rule; /authentication/ redirects
library/authentication/decorators.py         # sign-in redirect with next; 403 for the wrong role
library/authentication/serializers.py        # role, status, email and password writable only by librarians
library/authentication/api_views.py          # permission classes; readers see only themselves
library/authentication/templates/authentication/login.html   # shows messages
library/author/api_views.py                  # permission classes
library/book/api_views.py                    # permission classes
library/order/api_views.py                   # permission classes; readers see and start only their own loans
library/authentication/test_access.py        # new: every API operation for each caller; schema audiences
library/{authentication,book,order,events}/tests.py, library/book/test_delete.py   # sign in as the rules require; 403 replaces the redirect home
.github/workflows/docker-build.yml           # anonymous search answers 401; signed-in search answers 200
scripts/smoke_stack_budget.py                # signs in: --email, BUDGET_CHECK_PASSWORD
docs/deployment/raspberry-pi-portainer.md    # librarian account review; signing in for the measurement
README.md                                    # API table with each audience
docs/shared/changelog.md

# PR 2: query counts (KAN-18)
library/author/api_views.py                  # prefetch each author's books
library/library/testing.py                   # new: same query count with 1 and 50 rows
library/{authentication,author,book,order,events}/test_queries.py   # new
scripts/smoke_stack_budget.py                # --max-catalog-p95-ms
docs/deployment/raspberry-pi-portainer.md    # catalog timing in "Measure the stack on the Pi"
specs/003-priority-tech-debt/                # committed now (FR-060); Measurements updated
docs/shared/changelog.md

# PR 3: tests and coverage (KAN-21)
library/author/tests.py                      # new
library/book/tests.py, library/order/tests.py   # every channel, every limit, every loan change
library/authentication/test_routes.py        # new: every web route, permitted and refused
library/authentication/models.py, library/authentication/migrations/0004_alter_customuser_created_at.py
library/book/models.py, library/book/migrations/0005_alter_book_count.py
requirements-dev.txt                         # coverage 7.16.2, diff-cover 10.6.0
pyproject.toml                               # [tool.coverage.*]
.github/workflows/docker-build.yml           # coverage on ubuntu-latest; report in the summary and a PR comment
.gitignore, README.md, docs/shared/changelog.md

# PR 4: reservation model (KAN-55)
library/order/models.py                      # Reservation, its states, a guarded queryset; Order.book PROTECT
library/order/migrations/0004_reservation.py
library/order/admin.py                       # read-only reservation list
library/book/views.py, library/book/api_views.py   # protected delete: web message, API 409
library/order/test_reservations.py           # new: model, transitions, constraints, deletion
docs/adr/README.md, docs/adr/0001-reservations-hold-a-unit-of-stock.md   # new
README.md, docs/shared/changelog.md

# PR 5: reserving (KAN-56)
library/order/services.py                    # new: reserve, lend, expire_due, refusals
library/order/tasks.py                       # new: expire_reservations
library/order/views.py, library/order/urls.py, library/order/serializers.py, library/order/api_views.py
library/order/templates/order/reservation_my.html   # new
library/book/models.py                       # availability subtracts active reservations
library/book/views.py, library/book/templates/book/book_detail.html   # reserve button and the reasons it is unavailable
library/library/api_urls.py                  # reservation routes
library/library/settings.py                  # TIME_ZONE Europe/Kyiv; CELERY_BEAT_SCHEDULE
docker-compose.yml, docker-compose-dev.yml   # the worker runs beat
library/order/test_reservations.py, library/order/test_queries.py, library/book/tests.py
docs/features/reservations.md                # new: the reader's side
README.md, docs/shared/changelog.md

# PR 6: issuing at the desk (KAN-57)
library/order/services.py                    # issue and cancel; lending for librarians only
library/order/views.py, library/order/urls.py, library/order/forms.py   # desk, issue, cancel, lend, dismiss; /order/create/ redirects
library/order/middleware.py                  # new: the reader's cancellation notices
library/order/api_views.py, library/order/serializers.py   # cancel and issue; creating loans for librarians only
library/order/templates/order/{reservation_desk,reservation_issue,reservation_cancel,order_lend}.html   # new
library/library/templates/base.html, library/library/settings.py   # notice region; middleware
library/events/signals.py                    # borrow counted for the reader, with issued_by
library/order/test_reservations.py, library/events/tests.py
docs/features/reservations.md, README.md, docs/shared/changelog.md

# PR 7: complete pages (KAN-58)
library/order/templates/order/*.html, library/book/templates/book/book_detail.html
library/order/test_reservation_journeys.py   # new: the whole journey through the web and the API
scripts/smoke_reservation_load.py            # new: burst and load
.github/workflows/docker-build.yml           # burst on ubuntu-latest
docs/features/reservations.md, README.md, docs/deployment/raspberry-pi-portainer.md
.specify/memory/constitution.md              # PATCH (R29)
docs/shared/changelog.md

# PR 8: logs and audit (KAN-67)
library/library/logs.py                      # new: format, redaction, request id, configuration
library/library/middleware.py                # new: RequestIdMiddleware
library/library/celery.py                    # setup_logging; request id in task headers and task_prerun
library/library/settings.py                  # LOGGING, LOG_LEVEL, middleware, INSTALLED_APPS adds audit
library/gunicorn.conf.py, entrypoint.sh      # the same format
library/audit/                               # new app: apps, models, services, context, admin, migrations/0001_initial.py, tests.py
library/authentication/models.py, library/authentication/signals.py, library/authentication/apps.py
library/order/models.py, library/order/services.py, library/book/models.py, library/book/tests.py
library/events/tasks.py, library/events/management/commands/smoke_test_tracking.py   # the request id reaches the worker
docker-compose.yml, docker-compose-dev.yml   # x-logging rotation; LOG_LEVEL
.github/workflows/docker-build.yml           # test command adds audit; log secret scan
.github/CODEOWNERS, AGENTS.md                # /library/audit/; test command
.env.example, README.md, docs/deployment/raspberry-pi-portainer.md
docs/adr/0002-audit-trail.md                 # new
.specify/memory/constitution.md              # MINOR (R29)
docs/shared/changelog.md

# PR 9: backups (KAN-68)
docker-compose.yml, docker-compose-dev.yml   # backup service; pgbackups volume
library/authentication/tests.py              # both stacks define the same backup service, on its own volume
.github/workflows/docker-build.yml           # one backup, trial restore, counts compared
docs/deployment/raspberry-pi-portainer.md    # backups, weekly copy, restores, rehearsal, persistence, limits
docs/adr/0003-database-backups.md            # new
.env.example, README.md
.specify/memory/constitution.md              # PATCH (R29)
specs/003-priority-tech-debt/research.md     # Measurements
docs/shared/changelog.md

# PR 10: accessibility (KAN-69)
library/library/templates/base.html, library/library/templates/includes/form_snippet.html, library/library/forms_mixins.py
library/*/templates/**/*.html                # contrast, labels, confirmations, dates with their zone, chart text
library/authentication/test_templates.py     # new: every displayed time shows its zone
scripts/a11y/package.json, scripts/a11y/package-lock.json, scripts/a11y/check_pages.mjs   # new
.github/workflows/docker-build.yml, .github/CODEOWNERS, .gitignore
README.md, .specify/memory/constitution.md (PATCH), specs/003-priority-tech-debt/research.md
docs/shared/changelog.md

# PR 11: administrator role (KAN-70)
library/authentication/models.py, library/authentication/migrations/0005_alter_customuser_role.py
library/authentication/{services,permissions,forms,views,serializers,admin}.py
library/authentication/management/commands/set_administrator.py   # new (with the package files)
library/authentication/templates/authentication/*.html
library/authentication/test_access.py, library/authentication/tests.py
docs/deployment/raspberry-pi-portainer.md    # "Create the first administrator"
README.md, .specify/memory/constitution.md (MINOR), docs/shared/changelog.md

# PR 12: debt register (KAN-71)
docs/shared/debt-register.md                 # new
docs/adr/README.md, README.md
specs/003-priority-tech-debt/                # spec Implemented; Measurements complete; tasks done
docs/shared/changelog.md
```

**Structure Decision**: the existing Django project under `library/`, with its Compose stacks and
CI. The feature adds:
- one Django app, `audit`;
- one Compose service, `backup`;
- two scripts, `scripts/smoke_reservation_load.py` and `scripts/a11y/check_pages.mjs`;
- two documentation folders, `docs/adr/` and `docs/features/`.

Every other change extends the file that already owns the concern.

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

There are no violations. The rows below are the justifications that Principle I (a new app) and
Principle VI (a new component, process or pinned tool) require.

| Change | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| New Django app `audit` (Principle I) | Audit entries record critical changes in three apps (accounts, loans and reservations, books). They must be written in the same transaction as each change (FR-037, FR-040). No existing app owns that record. | The `events` app keeps best-effort records that the worker writes after commit, the opposite guarantee (Principle V); one app would then hold both kinds. Three copies of the model, one per domain app, would break "one implementation per rule". |
| `backup` service in both stacks, on the database image, with the `pgbackups` volume (Principle VI: a new component and background process) | FR-025 to FR-027 require automatic daily backups that are checked, kept for 7 days and stored apart from the database's own storage | Cron on the Pi runs outside the stack, so Portainer cannot reproduce it. `pg_dump` from the app image through Celery fails because the image has no PostgreSQL 18 client; adding one grows the image and ties backups to the app. A third-party backup image is one more image to trust and keep current. |
| Celery beat inside the existing worker (Principle VI: a background process) | FR-014 and FR-037 require each due reservation to become expired, with an audit entry, even when nobody looks at it | A beat container is another Python process with Django loaded, about 70 to 100 MB, for one task. Cron on the Pi runs outside the stack. Expiring a reservation when it is read leaves unread ones without an entry, and makes reads write. |
| CI-only tools: coverage and diff-cover (`requirements-dev.txt`); Playwright and @axe-core/playwright (`scripts/a11y` lockfile) (Principle VI: exact pins) | FR-051 needs coverage of added and changed lines on every PR. FR-042 needs automated WCAG 2.2 A and AA checks in CI. | Manual accessibility checks cannot run in CI, and FR-042 requires them there. pa11y-ci also needs Node and a browser, with less control over signing in. Python Playwright in `requirements-dev.txt` would make the lint job install a browser driver it never uses. |
