2026-10-28
The reservation model, and books kept while they have history (KAN-55)
The order app adds the reservation: a reader's 48-hour hold on one unit of a book's stock, not on a particular copy. A reservation is active, issued, cancelled or expired, and only an active one changes: to issued or cancelled before its deadline, and to expired from then on. The deadline is set once, 48 hours after creation, and the database refuses any other, in any time zone. It also allows one active reservation per reader and book, and requires a cancellation to record its time. Bulk writes of a reservation's state, loan or cancellation are refused. Librarians read reservations, with each one's current state, in the admin site, which allows no change. Nobody can reserve yet; that arrives with KAN-56. A book with any loan or reservation can no longer be deleted: the edit page says why, the API answers 409 with the same message, and the admin site lists the records that protect the book. Before, the API and the admin site deleted a book with its loans. The tracking smoke test now deletes its account before its book. ADR 0001 records the design.

2026-10-28
Technical logs and an audit trail of critical changes (KAN-67)
The web service, Gunicorn, the worker and the startup script write one log line format: UTC time with milliseconds, level, service, request identifier and logger. Every response carries an X-Request-ID, and background work started by a request logs the same identifier, so one search finds a request in both services, traceback included. Passwords, secrets, session identifiers, connection passwords and search text are redacted, a failed sign-in names only the account id, and Gunicorn's access log stays off. Every service's log rotates at 5 files of 10 MB, and LOG_LEVEL sets the level. A new audit app records each change of role, account status, loan or book stock, and each deletion of an account, loan or book, in the same transaction as the change; entries cannot be edited or deleted, and librarians read them in the admin site. CI runs the audit tests, checks that the worker's log carries the smoke test's request identifier, and scans every log for secrets and search text. ADR 0002 records the design, and the constitution is amended to v2.3.0.

2026-10-28
Tests for the book, author and loan rules, and a coverage report (KAN-21)
The author app gets its first tests, and books, authors and loans are now tested through the web, the API and the admin site: creating, editing and deleting, the field limits, every change of a loan, and a reader refused at each step. A new table checks every web route for an anonymous visitor, a reader and a librarian. CI measures coverage on one runner and reports how many of a pull request's added and changed lines the tests cover, in the job summary and in a comment on the pull request; the target is 85%. Three defects the tests found are fixed: saving an account no longer changes its creation time, a book's number of copies can no longer be negative, and an author attached to books can no longer be deleted through the API or the admin site, where the API now answers 409.

2026-10-28
A fixed number of queries for every list (KAN-18)
Every page and API list of books, authors, accounts, loans and analytics events now has a test that loads it with 1 row and with 50 and fails if the number of database queries differs. The API's author list read each author's books with a separate query, 53 queries for 50 authors; it now loads them together and uses 4 at any size. The other lists already used a fixed number. The query count of every list, before and after, is recorded in the feature's research notes. The memory budget script also times 60 loads of the signed-in catalog page and reports the first load and the 95th percentile; --max-catalog-p95-ms sets its limit, and the operator guide documents it. This change also publishes the planning documents of KAN-62 in specs/003-priority-tech-debt.

2026-10-28
Daily database backups with a trial restore (KAN-68)
Both Compose stacks add a backup service on the database's own image. Every day it takes a pg_dump of the whole database into the new pgbackups volume, reads the archive back to check it, and writes a SHA-256 checksum. It keeps 7 days of backups and always keeps the 7 newest. A failed run logs its cause and keeps every earlier backup. BACKUP_HOUR and BACKUP_KEEP_DAYS set the schedule and the retention. CI takes a backup on every run, restores it into a scratch database and compares every table's row count. The operator guide adds the daily backups, a weekly copy to another machine, a restore into a separate database, a restore after losing the database, the rehearsal record, and persistence and limit checks. ADR 0003 records the design. The constitution is amended to v2.2.1: the stacks list the backup service, and the smoke test includes the trial restore.

2026-10-28
Access by role for every account and API operation (KAN-24, KAN-62)
Sign-up always creates a visitor account, and only librarians change an account's role or status, on the web and through the API; a visitor's profile page edits the names only. Every API operation declares who may call it, and an operation without a declaration refuses everyone. The API accepts session sign-in only: it answers 401 when signing in is needed, 403 when the account's role does not allow the action, and 404 for another user's record. Web pages that need another role answer 403 with a page that says what to do next, and the sign-in page says why it appeared. The API schema states each operation's audience. CI's endpoint checks and the memory budget script sign in as the demo reader, and the operator guide adds a review of librarian accounts.

2026-10-20
Remove Render hosting integration
Removed the Render Blueprint, launcher, Render-only scripts, CI checks, proxy settings and documentation references. Docker Compose remains the deployment path for Raspberry Pi and Portainer.

2026-10-20
Django 5.2 LTS feature complete
Recorded the Raspberry Pi measurements after the Django 5.2 upgrade and after the move to PostgreSQL 18 and Redis 8 in research.md: peak memory 2.669 GiB, search p95 243 ms and book save p95 173 ms, all within the 4 GB, 500 ms and 2 s targets. The one-time reset on the Pi is confirmed complete. The spec is marked Implemented, every task is done with the success criteria evidence recorded, and the Spec Kit bridge handoff is complete.

2026-10-20
PostgreSQL 18 and Redis 8
Both Compose stacks now run pgvector/pgvector:0.8.7-pg18 (PostgreSQL 18) and redis:8.10.2-alpine on new volumes, pgdata18 mounted at /var/lib/postgresql and redisdata8. PostgreSQL 18 cannot read PostgreSQL 15 files and the server held only demo seed data, so the upgrade is a one-time reset: the stack starts empty and reseeds. The old volumes stay until the operator deletes them, so reverting brings the previous stack back. The operator guide has the steps, including the seed-only check before merging. A test keeps both stacks on the same exact images. The constitution is amended to v2.2.0 (PostgreSQL 18).

2026-10-20
Current lint and format tools
Bumped black from 26.5.1 to 26.10.1 and ruff from 0.16.10 to 0.17.1 in requirements-dev.txt. The code already passes both, so no reformatting or lint fixes were needed, and the pyproject.toml settings are unchanged.

2026-10-20
Django 5.2 LTS and current runtime dependencies (KAN-17)
Upgraded Django from 4.1, which no longer receives security fixes, to 5.2.18 LTS, and moved every runtime dependency to its latest release compatible with it. The exception is redis-py, held at 6.4.0 by kombu. The root requirements.txt now pins the complete resolved set and is the only runtime dependency list; library/requirements.txt is removed. STORAGES replaces the removed STATICFILES_STORAGE setting, so WhiteNoise keeps serving compressed, hash-named static files, and USE_L10N is gone. Two migrations that had never been generated now ship: the role choice label and order.id as bigint. The API schema is unchanged, and no deprecation warnings remain. The constitution is amended to v2.1.0: the Django 5.2 LTS line, a single dependency list, and patch releases as routine updates.

2026-10-20
Deployment hardening follow-ups
Behind the HTTPS proxy (TRUST_X_FORWARDED_PROTO), session and CSRF cookies are now sent over HTTPS only. Version tags only publish images and no longer redeploy the Raspberry Pi, so the production GitHub environment needs only the main branch. The operator guide adds a step to change seeded demo passwords before the site is reachable from the internet, and a first-deployment check that Portainer's webhook, forced redeploy, image re-pull and failed-pull behaviour work as the setup expects. The spec records the clarifications behind these changes.

2026-10-20
Raspberry Pi measurements recorded
Recorded the stack budget check from the first Raspberry Pi 5 deployment in research.md §R1: peak memory 2.45 GiB, search p95 237 ms and book save p95 199 ms with two web workers and two inference threads, all within the 4 GB, 500 ms and 2 s targets. This closes the last task of the Raspberry Pi deployment feature, and the Spec Kit handoff is marked complete.

2026-10-20
Raspberry Pi deployment and portable embeddings
Moved hosting from Render to a Raspberry Pi 5: docker-compose.yml is now the server stack that Portainer Business Edition deploys from Git using multi-architecture GHCR images only, and local development moved to docker-compose-dev.yml. CI runs lint and the full smoke test on native amd64 and arm64 runners, publishes both architectures under one manifest, moves the main tag only forward in history, calls the Portainer webhook from the production environment, and confirms through the new /api/v1/version/ endpoint that the site runs the new commit; a webhook that times out during a large image pull falls back to that confirmation. TRUST_X_FORWARDED_PROTO accepts the usual true/false spellings and stops startup on any other value. Search now uses bge-m3 int8 (1024 dimensions), defined once in library/book/embedding_config.py and fetched by scripts/fetch_embedding_model.py; vectors live in an untyped column and are re-encoded on startup after a model change, an 18-query evaluation set runs on both architectures, and a stack budget check keeps the whole stack within 4 GiB. Render files, checks and settings were removed, docs/deployment/raspberry-pi-portainer.md guides the operator, and the constitution was amended to v2.0.0.

2026-10-19
Lint and format checks in CI
Added ruff and black settings in pyproject.toml with pinned versions in requirements-dev.txt, and a CI lint job that must pass before the image is published. Formatted the code with black and fixed the lint findings without changing behavior; migrations are excluded.

2026-10-19
Secrets only from environment variables
Removed default secrets: Django refuses to start without SECRET_KEY, DEBUG is off unless explicitly enabled, the database password has no default, and DATABASE_URL is supported ahead of the DB_* values. The Docker image no longer bakes in a SECRET_KEY, Compose requires SECRET_KEY and DB_PASSWORD from .env, CI generates disposable secrets and checks that the image refuses to start without a key, and .env.example and the README document the required values.

2026-10-19
CodeQL code scanning
Added a CodeQL workflow that scans GitHub Actions workflows, JavaScript and Python code for security and quality issues on pushes and pull requests to main and every Saturday, and reports findings as code scanning alerts in the repository's Security tab.

2026-10-18
Code ownership by module
Assigned owners for borrowing, books, and events; grouped business analysis and shared documentation; and updated test ownership so Dima and Arezzon can review test changes.

2026-10-18
Delete books from the edit page
Added a librarian-only delete action beside the edit controls using the logout button style, with confirmation, CSRF protection, a borrowing-history guard, and focused tests for deletion and access control.

2026-10-13
Template guidance for GitHub contributions
Updated the repository guidance and PR delivery skill to follow the pull request template and use the bug report template when drafting GitHub defects.

2026-10-13
GitHub review and bug-report templates
Added a pull request template with a Definition of Done checklist and a bug-report template with reproduction, expected result, actual result, and environment fields. Existing CODEOWNERS already assigns repository, documentation, and test owners.

2026-10-08
README and mobile analytics navigation
Reworked the README with Docker and venv quick starts, prerequisites, platform-specific commands, Memurai/Redis guidance, troubleshooting, API and analytics documentation. Added the mobile Analytics icon to match the other navigation items.

2026-10-07
Fresh base for feature branches
Added a skill and repository rule to create feature branches from an updated origin/main, with a verified feature branch base when a dependency requires it.

2026-10-06
Code ownership by role
Limited Anastasiia's code ownership to documentation and Dima's to test files and test directories. The other four collaborators remain owners across the repository.

2026-10-06
Repository guidance and delivery skills
Added AGENTS.md and two skills for reviewing commits and pull requests. PR guidance covers changelog updates, readable titles, descriptions, and assignees.
