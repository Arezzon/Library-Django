# Feature Specification: Django 5.2 LTS Upgrade and Dependency Refresh

**Feature Branch**: `chore/kan-17-django-5.2-lts`

**Created**: 2026-10-20

**Status**: Implemented

**Input**: User description: "Complete https://arsensworkspace-47040086.atlassian.net/browse/KAN-17 task from Jira. Also get rid of duplicated `requirements.txt` in `./library`"

**Source task**: KAN-17, "Upgrade Django from 4.1 to the supported LTS line (5.2 LTS)", priority Highest,
labels `security` and `tech-debt`, epic KAN-2 "Modernize the base system". The task asks to update
the dependency pins, check deprecation warnings, run the tests and confirm compatibility with
Django REST Framework and drf-spectacular. Django 4.1 stopped receiving security updates in
December 2023, which the task calls a critical risk, and the upgrade must land before work on the
AI features starts.

## Clarifications

### Session 2026-10-20

- Q: Should the constitution be amended with the changes this spec describes? → A: Yes. Amend it
  so that Technology & Platform Constraints name the Django 5.2 LTS line and Principle VI no
  longer requires a second dependency list under `library/`.
- Q: Should only the dependencies that do not support Django 5.2 change, or all of them? → A: Bump
  every runtime dependency to its latest release. Where the latest release is not compatible with
  Django 5.2 LTS, use the highest release that is.
- Q: Does "bump everything" also cover the lint and format tools and the database and broker
  images? → A: Yes, all three, each in its own pull request: (1) runtime dependencies, (2) lint
  and format tools, with any reformatting and lint fixes in the same pull request, (3) the
  PostgreSQL and Redis service images in both Compose files.
- Q: How should the server's PostgreSQL 15 data move to the new major database release? → A: It
  is not moved. The server database holds only seeded demo data, so it is dropped completely
  during the update and repopulated afterwards from the current seed script.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The library keeps working on a security-supported framework (Priority: P1)

Readers, librarians and API clients use the site exactly as they do today: browse and search the
catalog, borrow and return books, manage authors, books and orders, view analytics, and call the
REST API. After the upgrade, nothing they do changes. The difference is that the web framework under
the site receives security fixes again, so a published vulnerability can be patched by a routine
release instead of an emergency migration.

**Why this priority**: The site currently runs on a framework release that has had no security
fixes for almost three years. This story removes that risk without changing user-visible behavior,
and every later feature, including the planned AI work, builds on it.

**Independent Test**: Build the upgraded release, run the full automated regression suite and the
CI smoke checks on both supported processor architectures, then deploy it over a copy of the
current production data and walk through the main journeys: sign in as a reader and as a
librarian, search the catalog in English and Ukrainian, borrow and return a book, edit a book, open
the analytics dashboard and open the interactive API documentation.

**Acceptance Scenarios**:

1. **Given** the upgraded release, **When** the CI pipeline runs, **Then** lint, the full regression
   suite including the real embedding-model tests, the endpoint checks, the event-tracking smoke
   tests and the memory budget check all pass on both processor architectures.
2. **Given** a database created and populated by the current release, **When** the upgraded release
   starts against it, **Then** it starts without manual steps and every user, author, book, order,
   event and book vector is still present and unchanged.
3. **Given** an existing account, **When** its owner signs in with their current password after the
   upgrade, **Then** the sign-in succeeds and the user has the same role and access as before.
4. **Given** an API client written against the current API, **When** it calls the same endpoints
   with the same requests, **Then** it receives the same status codes and response shapes, and the
   published API schema still describes every endpoint, parameter and non-default response.
5. **Given** the site running in production mode, **When** a visitor opens any page or the admin
   site, **Then** all styles and scripts load, and changed static files still reach browsers under
   new versioned addresses so that no browser keeps a stale copy.
6. **Given** a visitor who is not allowed to perform an action today, **When** they try it after the
   upgrade, **Then** it is still refused in the same way.

---

### User Story 2 - Maintainers start from a clean deprecation baseline (Priority: P2)

A maintainer runs the test suite and the framework's system checks and sees no deprecation warnings
raised by the project's own code. Any warning that comes from a third-party package is listed in the
feature documentation with the package that raises it and how it is expected to be resolved. The
next framework upgrade can then be planned from a known list instead of being discovered when a
release removes a feature.

**Why this priority**: Moving from 4.1 to 5.2 crosses several releases that removed or changed
features. A clean baseline confirms that nothing the project relies on is about to disappear, but
the site is already safe once Story 1 ships.

**Independent Test**: Run the full test suite and the system checks with deprecation warnings shown,
and confirm that none originates in the project's code and that every remaining warning appears in
the feature's warning list.

**Acceptance Scenarios**:

1. **Given** the upgraded code, **When** the full test suite and the system checks run with
   deprecation warnings enabled, **Then** no warning originates in the project's own code.
2. **Given** a deprecation warning raised by a third-party package, **When** a maintainer reads the
   feature documentation, **Then** the warning is listed with the package that raises it, the
   release that will remove the feature and the expected resolution.
3. **Given** project configuration that the previous framework release honored, **When** the
   upgraded release runs, **Then** no configuration option is silently ignored: each removed option
   has been replaced by its supported equivalent, so its effect is preserved.

---

### User Story 3 - One runtime dependency list for every environment (Priority: P3)

A developer setting up the project locally, a maintainer bumping a dependency and the image build
all use the same single runtime dependency list at the repository root. The duplicate list in the
`library/` directory is gone, so the two lists can no longer drift apart and a version bump touches
one file.

**Why this priority**: The duplicate list is a maintenance hazard: an update applied to one file but
not the other gives local setups and the published image different dependencies. It does not
affect users of the site, and removing it is easiest in the same change that rewrites every pin.

**Independent Test**: From a clean checkout, follow the README's local setup instructions and confirm
that they install every runtime dependency in one step from the root list. Confirm that the image
build uses the same list and that no other runtime dependency list exists in the repository.

**Acceptance Scenarios**:

1. **Given** the repository after this change, **When** anyone looks for the runtime dependencies,
   **Then** exactly one list exists, at the repository root, and the duplicate under `library/` is
   removed.
2. **Given** a new developer following the README, **When** they set up a local environment on
   Windows or on Linux/macOS, **Then** the instructions point to the root list and the setup
   succeeds without editing any path.
3. **Given** the project's governing rules and guides, **When** a maintainer reads them, **Then**
   none of them still requires keeping a second copy of the dependency list in sync.

---

### User Story 4 - Maintainers lint and format with current tools (Priority: P4)

Maintainers and CI check the code with the latest releases of the lint and format tools. The code
already passes them when the tools are bumped, because any reformatting and lint fixes the new
releases call for ship together with the version bump. Nothing the site does changes.

**Why this priority**: Current tools catch more problems and keep pace with the language, but they
carry no security risk for the site, so they follow the runtime upgrade.

**Independent Test**: Install the pinned tools and run the lint and format checks from the
repository root. Both report no findings, and the full test suite still passes unchanged.

**Acceptance Scenarios**:

1. **Given** the bumped tool pins, **When** the CI lint job runs, **Then** lint and format checks pass
   with no findings.
2. **Given** the reformatting and lint fixes in this pull request, **When** the full regression suite
   runs, **Then** it passes with no test assertion changed, so no behavior changed.
3. **Given** a lint rule that the new tool release renamed or removed, **When** the tools read the
   project's lint settings, **Then** they load without errors or warnings about unknown rules.

---

### User Story 5 - The database and message broker run on current releases (Priority: P5)

The database and the message broker in both the local development stack and the server stack run on
their latest stable releases. The server's database holds only seeded demo data, so the update drops
it and fills a fresh database from the seed script. After a short maintenance window, visitors see
the same demo catalog and demo accounts as before.

**Why this priority**: The database holds the catalog and the broker holds queued analytics events,
so both benefit from current security and bug fixes. A new major database release cannot read the
old release's files, so this pull request resets the server's data. That makes it the most
disruptive of the three, so it comes last, once the application already runs on Django 5.2.

**Independent Test**: Start the development stack with the new images and run the full CI smoke
test. Then follow the operator guide's reset steps on the server and confirm that the site serves the
freshly seeded catalog, that search works over it, and that the demo passwords were changed again.

**Acceptance Scenarios**:

1. **Given** the new service images, **When** the CI pipeline runs, **Then** every CI gate passes on
   both processor architectures, including the event-queue recovery check and the 4 GiB memory
   budget check.
2. **Given** the server's PostgreSQL 15 database holding only seeded demo data, **When** the operator
   follows the guide's reset steps and the stack is redeployed with the new images, **Then** the old
   data is gone, the new database holds exactly what the seed script creates, and every seeded book
   has a vector from the current embedding model, so semantic search works over the whole catalog.
3. **Given** the reset, **When** the new broker starts, **Then** it starts with an empty queue, and an
   event recorded after the deploy is stored end to end.
4. **Given** the two Compose stacks, **When** a maintainer compares them, **Then** both use the same
   database and broker image versions.
5. **Given** the freshly seeded server, **When** the site becomes reachable again, **Then** the
   operator has replaced the published demo passwords, as the operator guide already requires after
   seeding.

---

### Edge Cases

- **Signed-in users during the deploy**: users who are signed in when the upgraded release goes live
  stay signed in. If a session cannot be carried over, the user is asked to sign in again and never
  sees an error page.
- **Older password hashes**: passwords stored with the previous release's hashing parameters still
  verify. The stronger parameters are applied automatically the next time each user signs in.
- **Rolling back**: if the upgraded release must be reverted on the server, the previous release can
  be redeployed against the same database. If the upgrade adds a schema change that makes that
  impossible, the operator guide states it before the upgrade is deployed. Rolling back the service
  image pull request means another reset and reseed on the previous images, which is acceptable
  only while the server holds seed data alone.
- **Schema drift detected by the new framework**: if the new framework reports model changes that
  have no migration, they ship as a new migration. Migrations that already reached `main` are not
  edited.
- **A dependency with no release that supports the target framework**: the upgrade stops and the
  incompatibility is reported. The project never ships an unsupported combination of framework and
  dependency.
- **A dependency upgrade that changes the generated API schema**: every difference between the old and
  new schema is reviewed. Differences that would change what clients send or receive are corrected;
  cosmetic differences are recorded as non-breaking.
- **Open automated dependency pull requests**: the existing Dependabot pull requests that bump Django
  to 5.2.17 and Django REST Framework to 3.17.2 edit both dependency lists and leave incompatible
  pins in place. This feature supersedes them, and they are closed once it merges.
- **Existing local environments**: a developer whose virtual environment was installed from the removed
  `library/` list reinstalls from the root list. The README states this once, where it describes
  local setup.
- **Semantic search quality**: the upgrade must not change search results. The English and Ukrainian
  evaluation set that runs in CI keeps passing.
- **A runtime dependency whose latest release changes inference or memory use**: the embedding
  runtime and model-download libraries also move to their latest releases. The search evaluation
  set and the memory budget check catch any change in results or memory.
- **New lint findings from a newer tool release**: they are fixed in the lint and format tools pull
  request with changes that keep behavior identical. A finding that cannot be fixed without
  changing behavior is suppressed at that line, with the reason given next to the suppression.
- **Database data across a major release**: the new database release cannot read the old release's
  files. The server holds only seeded demo data, so that data is dropped instead of carried over.
- **Real data on the server by the time of the deploy**: if anything other than seed data has been
  stored by then (accounts that people registered, books or orders entered by hand), the reset MUST
  NOT run. The service image pull request waits until a way to carry the data over is specified.
- **Events still queued in the broker**: queued events point to users of the dropped database, and a
  fresh database reuses those user numbers, so old events would attach to the wrong reseeded users.
  The broker's stored queue is therefore cleared together with the database. Analytics are derived
  data that the constitution allows to be lost.
- **Reseeded demo passwords**: seeding recreates the demo accounts with their published passwords,
  so the operator changes them again before the site is reachable, as the guide requires for any
  seeding.
- **Local development stacks**: developers drop their local database and broker volumes and reseed
  in the same way. The README states this once.

## Requirements *(mandatory)*

### Functional Requirements

**Framework and dependencies**

- **FR-001**: The application MUST run on the Django 5.2 LTS release line, pinned to the latest
  5.2 security release available when the work is implemented.
- **FR-002**: Every runtime dependency MUST be pinned to one exact version that officially supports
  Django 5.2 and Python 3.12. Django REST Framework and drf-spectacular MUST be checked explicitly,
  as KAN-17 requires. The task queue, static file serving, vector search integration, database
  driver and the framework's own support libraries MUST be checked as well.
- **FR-003**: Every pinned runtime dependency MUST move to its latest stable release. Where the
  latest release does not support Django 5.2 LTS, the dependency MUST move to the highest release
  that does. The chosen version of each dependency MUST be recorded, and for any dependency left
  below its latest release, so MUST the reason.

**Unchanged behavior and data**

- **FR-004**: All pages, forms, role checks, borrowing rules, semantic search and activity tracking
  MUST behave as they do before the upgrade. The existing automated tests MUST pass without being
  removed or weakened. A test MAY change only where a framework API it calls has changed, and it
  MUST still verify the same behavior.
- **FR-005**: The REST API contract MUST stay the same: the same endpoints under `/api/v1/`, the same
  request and response shapes and status codes, and an API schema and interactive documentation
  that still describe every endpoint, parameter and non-default response.
- **FR-006**: Upgrading a running installation to the new runtime dependencies MUST preserve all
  existing data: accounts, roles, authors, books, orders, analytics events and book vectors. Any
  data or schema change MUST be applied automatically at startup, with no manual operator step.
- **FR-007**: Existing accounts MUST be able to sign in with their current passwords after the
  upgrade.
- **FR-008**: In production mode, static files MUST be served with the same compression and
  versioned, cache-safe addresses as before the upgrade.
- **FR-009**: Any schema change the upgrade requires MUST ship as a new migration. Existing
  migrations MUST NOT be edited. The previous release MUST remain deployable against the upgraded
  database, unless the operator guide documents why it is not.

**Deprecations**

- **FR-010**: The project's own code and configuration MUST raise no deprecation warnings during a
  full test run and the framework's system checks.
- **FR-011**: The project MUST NOT depend on configuration options that the target framework removed.
  Each such option MUST be replaced by its supported equivalent so that its effect is preserved.
- **FR-012**: Deprecation warnings raised by third-party packages MUST be listed in the feature
  documentation with the package, the framework release that removes the feature and the expected
  resolution.

**Quality gates and deployment**

- **FR-013**: All CI gates the constitution defines MUST pass on both `linux/amd64` and
  `linux/arm64`: lint and format, the full regression suite including the real embedding-model
  tests, the endpoint checks, the event-tracking smoke test, the broker and worker recovery check
  and the 4 GiB stack memory budget check.
- **FR-014**: The runtime dependency and lint tool pull requests MUST deploy to the Raspberry Pi
  through the existing pipeline with no new operator step and no new configuration value.

**Single dependency list**

- **FR-015**: The duplicate runtime dependency list under `library/` MUST be removed. The list at
  the repository root MUST be the only runtime dependency list, used by both the image build and
  local development.
- **FR-016**: The README's local setup instructions for Windows and for Linux/macOS, its project
  layout and the root list's own header comment MUST point to the single root list. No current
  document or tool may refer to the removed file. Historical records such as past feature specs,
  bridge snapshots and earlier changelog entries stay as written.

**Governance and documentation**

- **FR-017**: The constitution MUST be amended through the project's amendment process, with a
  version bump and a changelog entry, by the pull request whose change each amendment describes.
  The runtime dependency pull request MUST change Technology & Platform Constraints to name the
  Django 5.2 LTS line and to require a feature spec only for moving Django to another release
  line or DRF to another minor release, so that patch releases are routine updates. It MUST also
  change Principle VI so that it no longer requires a second dependency list kept identical to
  the root one. The service image pull request MUST change the
  database version named in Technology & Platform Constraints.
- **FR-018**: The README's description of the stack MUST name the new framework line and database
  version. Each pull request MUST add its own entry to the project changelog.

**Lint and format tools**

- **FR-019**: The lint and format tools MUST be pinned to their latest stable releases. The whole
  codebase MUST pass them with no findings. All reformatting and lint fixes needed for that MUST be
  in the same pull request, and they MUST NOT change behavior.
- **FR-020**: The project's lint and format settings MUST change only where a new tool release
  renamed, removed or replaced a setting or rule the project uses.

**Database and broker images**

- **FR-021**: The database image (PostgreSQL with the `vector` extension) and the broker image in
  both Compose stacks MUST be pinned to their latest stable releases. Where the latest release is
  not supported by Django 5.2 LTS or the task queue, they MUST be pinned to the highest release
  that is. Both stacks MUST use the same versions, and the images MUST exist for both `linux/amd64`
  and `linux/arm64`.
- **FR-022**: Replacing the database and broker images on the server MUST reset their data. The old
  database and the broker's stored queue are dropped. The new database is created by the
  application's migrations and populated once by the seed script on `main` at deploy time. Every
  seeded book is encoded with the current embedding model before the site serves traffic.
- **FR-023**: Demo seeding MUST stay off by default in the server stack. The reset turns it on for
  the reseed only, and the operator replaces the published demo passwords before the site is
  reachable.
- **FR-024**: The operator deployment guide MUST give the one-time reset as ordered steps, timed with
  the merge so that the webhook redeploy never starts the new database on the old data. The steps
  MUST start with a check that the server holds only seed data. The README's service table, its
  local setup notes and `.env.example` MUST describe the new images, and all of this MUST be in
  place before the change reaches the server.

**Delivery**

- **FR-025**: The work MUST ship as three pull requests, each passing every CI gate on its own and
  merged in this order:
  1. runtime dependencies: Stories 1–3, the Django 5.2 LTS line, every runtime dependency at its
     latest compatible release, removal of the duplicate dependency list and its constitution
     amendments;
  2. lint and format tools: Story 4, with all reformatting and lint fixes;
  3. database and broker images: Story 5, in both Compose stacks, with its constitution amendment.

  Each pull request MUST contain only its own part, so that each can be reviewed and reverted on
  its own.

### Key Entities

- **Runtime dependency list**: the single, root-level list of exact runtime package versions. The
  image build and local setups install from it. It replaces the root list and the duplicate copy
  under `library/` that exist today.
- **Production data**: accounts and roles, authors, books with their vectors, orders and analytics
  events stored by the current release. Today it is only seeded demo data. It must survive the
  runtime dependency upgrade unchanged, and the service image pull request replaces it with freshly
  seeded data.
- **Deprecation list**: the documented list of deprecation warnings that remain after the upgrade,
  all from third-party packages, with the source and expected resolution of each.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the existing automated regression tests pass on both processor architectures,
  and none is removed or skipped to make the upgrade pass.
- **SC-002**: A full test run and the system checks produce 0 deprecation warnings that originate in
  the project's own code.
- **SC-003**: After the upgraded release starts against a copy of production data, the number of
  users, authors, books, orders, events and stored book vectors matches the number before the
  upgrade, and 100% of tested existing accounts sign in with their current passwords.
- **SC-004**: The published API schema lists the same operations before and after the upgrade, with
  0 operations removed or renamed and 0 changes to request or response fields.
- **SC-005**: On the Raspberry Pi 5, the whole stack stays within 4 GB of memory and 95% of searches
  answer in under 500 ms, measured with the procedure in the operator deployment guide.
- **SC-006**: The site runs on a framework line that receives upstream security fixes until at least
  April 2028.
- **SC-007**: The repository contains exactly one runtime dependency list, and a developer following
  the README installs every runtime dependency in a single step.
- **SC-008**: With the lint and format tools at their latest releases, the lint and format checks
  report 0 findings, and 100% of the regression tests pass with no test assertion changed.
- **SC-009**: After the service image pull request is deployed to the Raspberry Pi, the database
  holds exactly the records the seed script creates, 100% of seeded books are found by semantic
  search, 0 published demo passwords remain in use, and SC-005's memory and search targets still
  hold.

## Assumptions

- The target is the 5.2 LTS line, as KAN-17 states. A newer non-LTS release would give less support
  time. Moving to the next LTS line, expected in April 2027, is a later task.
- Python stays at 3.12, which Django 5.2 supports, and the image's Python base is not part of this
  feature. PostgreSQL 15 is supported by Django 5.2 and stays in place until the service image pull
  request moves it.
- The lint and format tools and the service images go beyond KAN-17. They are part of this feature
  at the assignee's request, in separate pull requests so that KAN-17's own change stays small.
- Each pull request gets its own branch, created from `main` after the previous pull request has
  merged.
- This feature upgrades Django, Django REST Framework and every other runtime dependency. The
  constitution's Technology & Platform Constraints list moving Django to another release line or
  DRF to another minor release as a change that the feature spec must identify and the plan must
  justify under Principle VI. Moving from 4.1 to 5.2 and from DRF 3.15 to a newer minor release
  are both such changes. The upgrade adds no
  new dependency, model or background process.
- `pyproject.toml` holds only the lint and format tool settings and names no framework version, so
  the runtime dependency pull request leaves it unchanged. The lint tool pull request changes it
  only as FR-020 allows.
- No new user-facing behavior is added. Existing behavior that the new framework leaves supported,
  such as the current sign-out link, is kept, and changing it is out of scope.
- Each constitution amendment ships in the pull request whose change it describes (FR-017), so the
  constitution never names a version the repository does not use yet.
- If the upgrade must be reverted on the server, the operator pins the previous image, as the
  operator deployment guide's "Pin, roll back and unpin" section describes. A rollback does not
  revert migrations, which is why FR-009 keeps the previous release compatible with the upgraded
  database.
- KAN-17 is complete when the runtime dependency pull request merges. The assignee updates the Jira
  issue's status as that pull request is opened and merged.
