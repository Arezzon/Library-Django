---

description: "Task list for closing the priority technical debt of v1.0 (KAN-62)"
---

# Tasks: Close the Priority Technical Debt of v1.0

**Input**: Design documents from `specs/003-priority-tech-debt/`

**Prerequisites**:
- [plan.md](plan.md) and [spec.md](spec.md);
- [research.md](research.md), cited as R1 to R30;
- [data-model.md](data-model.md);
- [contracts/](contracts/);
- [quickstart.md](quickstart.md).

**Tests**: required. Principle III makes tests non-negotiable, and the spec asks for them (FR-047,
FR-049, FR-050, SC-001, SC-002). In every phase, write the tests first and see them fail before the
implementation tasks.

**Organization**: one phase per pull request (FR-059), each labeled with the user story it delivers.
- The phases follow the recommended merge order in research.md R1, not the stories' priority. The
  pull request is the unit of delivery, and this order avoids reworking the reservation stages for
  the audit trail.
- Four stories span two phases each:
  - Story 1: PR 1 and PR 11;
  - Story 2: PR 4 and PR 5;
  - Story 3: PR 6 and PR 7;
  - Story 8: PR 3 and the repository settings.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel with the other [P] tasks of its phase. They touch different files and
  wait for no unfinished task, other than the tasks listed before them.
- **[Story]**: the user story in spec.md, US1 to US9.
- **Markers**:
  - **(manual)**: done by a person, in a browser or with a screen reader.
  - **(Pi)**: done by the operator on the Raspberry Pi.
  - **(Arsen)**: a repository setting that only the repository administrator can change.
  - **(Jira)**: a change in Jira, made by the issue's assignee or with their approval.

## Conventions for every pull request phase

- **Paths and shorthand**:
  - Paths are from the repository root. Django code lives in `library/`, and management commands run
    from there.
  - `DC="docker compose -f docker-compose-dev.yml"` and `APPS="authentication author book order
    events"`, as in quickstart.md. PR 8 adds `audit` to `APPS`.
- **Branch and pull request**:
  - A phase starts by creating its branch with `.agents/skills/fresh-feature-branch/SKILL.md`.
  - It ends by preparing the pull request:
    - `ruff check .` and `black --check .` from the root;
    - the Django tests of the affected apps, and the diff-coverage check (quickstart.md §0.1);
    - one entry in `docs/shared/changelog.md`, in the format of the existing entries (a date line, a
      title line, one paragraph);
    - a description that follows `.github/PULL_REQUEST_TEMPLATE.md`.
  - Commit and push only when the user asks, through `.agents/skills/preview-commit/SKILL.md` and
    `.agents/skills/preview-pr/SKILL.md` (AGENTS.md).
- **Scope**: each commit and pull request holds only its phase's files (FR-062). Keep the `.specify/`
  bridge files (the handoff, the events and the snapshots) out of feature pull requests. They ride
  only with the spec-folder commits, T029 and T169.
- **Constitution amendments** (PRs 7 to 11):
  1. Set the Superpowers handoff to `blocked`.
  2. Amend with `/speckit-constitution`, and add its changelog entry.
  3. Set the handoff back to `executing` (R29).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: a known-good starting point, and the disclosure hold that FR-060 requires.

- [x] T001 Start from a freshly fetched `origin/main` and check the baseline (quickstart.md §0.1):
  - start the development stack with demo data (`DJANGO_SEED=true $DC up --build -d --wait`);
  - run `python manage.py collectstatic --noinput`;
  - run the full Django test command, `ruff check .` and `black --check .`.

  Record any failure that already exists on `main` before changing anything.
- [x] T002 [P] Keep the planning documents private until PR 1 is deployed (FR-060). Add two lines to
  the local, untracked `.git/info/exclude`:
  - `specs/003-priority-tech-debt/`;
  - `.specify/bridge-snapshots/`. The bridge copies `spec.md`, `plan.md` and `tasks.md` into each new
    snapshot. The 40 snapshot files already tracked are unaffected.

  No `git add` then picks either up. T027 removes both lines.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: work every story depends on.

No story-free foundation exists. The blocking prerequisite is PR 1 (Phase 3, Story 1): FR-060
requires it to merge first, and PRs 3, 4, 8 and 11 build on its permission classes. No task belongs
here.

**Checkpoint**: Phase 1 is done. Start Phase 3.

---

## Phase 3: User Story 1, part 1: only librarians grant access or change data. PR 1, KAN-24 and KAN-62 (Priority: P1) 🎯 MVP

**Goal**:
- Sign-up always creates a reader, and only librarians change roles and account status.
- Every API operation declares its audience, and anything undeclared is refused.
- Refusals say whether to sign in or that the action is not permitted.

**Independent Test**:
- Without signing in, register as a librarian and call every operation of the API.
- As a reader, change your own role, open another user's record, and change a book, an author and
  someone else's loan through the web, the API and the admin site.
- As a librarian, perform every librarian task.

Only the librarian's attempts and the reader's own reads succeed (spec Story 1).

### Tests for User Story 1 (PR 1)

> Write these first and make sure they fail on `main`.

- [x] T003 [US1] Create branch `fix/kan-24-access-control` from a freshly fetched `origin/main` with
  the fresh-feature-branch skill. (Jira) Move KAN-24 to In Progress.
- [x] T004 [US1] Create `library/authentication/test_access.py` with a test that resolves every URL
  pattern under `/api/v1/`, walking `django.urls.get_resolver()` and the router's routes.
  - It fails when a view class or viewset does not declare `permission_classes` in its own
    `__dict__`, that is, when it inherits DRF's default.
  - A new endpoint without an audience then fails CI (R2).
- [x] T005 [US1] In `library/authentication/test_access.py`, add table-driven tests for every row of
  "API operations" in contracts/access-control.md.
  - Call each path and method as an anonymous client, a reader (`role=0`, active) and a librarian
    (`role=1`), and assert the status the table gives:
    - 401 with the header `WWW-Authenticate: Session` for anonymous callers;
    - 403 for a caller with the wrong role;
    - 404 for another reader's account or loan, the same response as for an id that does not exist;
    - 200, 201, 202 or 204 otherwise.
  - Cover a reader's `POST /api/v1/order/` for themselves (201) and for another reader (403).
  - Cover a reader's `PATCH /api/v1/user/<own id>/` with `role`, `is_active`, `email` or `password`:
    403, and nothing changes.
  - Assert that no refused response contains a field of the record (FR-004).
  - Use `book.testing.FakeEncoderMixin` so search runs without the model.
- [x] T006 [US1] In `library/authentication/test_access.py`, add a schema test (FR-005). Fetch
  `/api/schema/?format=json` and assert that every operation has:
  - `x-audience`, one of `anonymous`, `signed-in`, `signed-in-read`, `self-or-librarian` or
    `librarian`;
  - a description ending with an `Audience:` sentence;
  - 401 and 403 responses, unless its audience is `anonymous`.
- [x] T007 [P] [US1] In `library/authentication/tests.py`, add tests for the web:
  - The sign-up form has no `role` or `is_active` field. A POST that adds `role=1` and
    `is_active=false` creates an active reader (FR-001, Story 1 scenario 1).
  - A reader's POST to `/authentication/users/<own id>/update/` with `role` or `is_active` gets 403
    and changes nothing, not even the names sent with it (scenario 2).
  - A reader's POST with names only is saved.
  - A librarian can change role and status (scenario 3).
  - An anonymous request to a protected page redirects to `/authentication/login/?next=<path>`, and
    the sign-in page shows "Sign in to continue.".
  - A reader on a librarian page gets 403 with "You don't have permission to do this." (scenario 6).
  - `/authentication/` redirects anonymous callers to sign-in, and signed-in callers home.

### Implementation for User Story 1 (PR 1)

- [x] T008 [US1] Create `library/authentication/permissions.py` (R2):
  - `DenyAll` refuses every caller.
  - `IsSignedIn` admits any active, signed-in account.
  - `ReadOnlyOrLibrarian` lets signed-in accounts use safe methods, and librarians anything.
  - `IsSelfOrLibrarian` requires sign-in at the view level. At the object level the object must be,
    or belong to, `request.user`, unless the caller is a librarian.
  - `IsLibrarian` requires `request.user.is_librarian`.
  - Each class has an `audience` attribute holding its `x-audience` value, and a plain-language
    `audience_description`.
  - A subclass of DRF's `SessionAuthentication` whose `authenticate_header()` returns `"Session"`.
- [x] T009 [US1] In `library/library/settings.py`, extend `REST_FRAMEWORK`:
  - `"DEFAULT_PERMISSION_CLASSES": ["authentication.permissions.DenyAll"]`;
  - `"DEFAULT_AUTHENTICATION_CLASSES": ["authentication.permissions.SessionAuthentication"]`, which
    drops Basic authentication;
  - `DEFAULT_SCHEMA_CLASS` pointing at `library.schema.AutoSchema`.
- [x] T010 [US1] Create `library/library/schema.py`, a subclass of
  `drf_spectacular.openapi.AutoSchema` that overrides `get_operation()` (R5, contracts/access-control.md
  "Schema annotation"). It:
  - reads `audience` and `audience_description` from the view's permission classes, mapping DRF's
    `AllowAny` to `anonymous`;
  - appends `Audience: <description>` to the description, and sets `x-audience`;
  - adds 401 and 403 responses with a `{"detail": string}` body, plus 404 for views that limit
    readers to their own records.
- [x] T011 [US1] In `library/library/api_urls.py`, register the routes on a subclass of
  `DefaultRouter` whose `APIRootView` is a subclass with `permission_classes = [AllowAny]`, so
  `/api/v1/` stays anonymous (FR-003).
- [x] T012 [US1] Create `library/authentication/services.py` (R3, FR-002):
  - `may_change_role(actor, account)` and `may_change_status(actor, account)`, both true when
    `actor.is_librarian`;
  - `update_account(actor, account, changes)`. It raises `django.core.exceptions.PermissionDenied`
    and changes nothing when `changes` includes `role` or `is_active` that the actor may not change,
    or `email` or `password` from someone who is not a librarian. Otherwise it applies the changes
    and saves.
- [x] T013 [US1] In `library/authentication/forms.py`:
  - remove `role` from `RegistrationForm.Meta.fields`, along with its label;
  - make `save()` always pass `role=ROLE_VISITOR`;
  - add `ProfileForm`, with `first_name`, `middle_name` and `last_name`, beside the existing
    `UserUpdateForm`.
- [x] T014 [US1] In `library/authentication/views.py`:
  - `user_update` uses `UserUpdateForm` when `may_change_role` or `may_change_status` allows it, and
    `ProfileForm` otherwise;
  - a POST that contains `role` or `is_active` from someone not allowed raises `PermissionDenied`,
    and saving goes through `update_account`;
  - `index` redirects to `login` for anonymous callers and to `home` otherwise.
- [x] T015 [US1] In `library/authentication/decorators.py`, change `librarian_required`,
  `librarian_or_owner_required` and `role_required`:
  - an anonymous caller gets `messages.info(request, "Sign in to continue.")` and
    `redirect_to_login(request.get_full_path(), "login")`;
  - a signed-in caller without the right role gets `raise PermissionDenied`;
  - librarian checks use `request.user.is_librarian`.
- [x] T016 [P] [US1] Create `library/library/templates/403.html`, extending `base.html`, with:
  - the heading "You don't have permission to do this.";
  - one sentence on what to do next;
  - a link home.

  Also render `messages` in `library/authentication/templates/authentication/login.html`.
- [x] T017 [US1] In `library/authentication/models.py`, make `is_staff`, `is_superuser`, `has_perm`
  and `has_module_perms` use `self.is_librarian`. Then run `grep -rn "ROLE_LIBRARIAN" library
  --include=*.py`, skipping tests, migrations and `seed_db.py`, and replace every remaining `role ==
  ROLE_LIBRARIAN` comparison with `is_librarian` (R3).
- [x] T018 [US1] In `library/authentication/serializers.py` and `library/authentication/api_views.py`:
  - make `role`, `is_active` and `email` read-only, and leave out `password`, unless the requester
    is a librarian;
  - answer 403 before validation when the body contains one of those fields, through
    `update_account`;
  - give `CustomUserViewSet` `permission_classes` per action: `IsLibrarian` for `list`, `create` and
    `destroy`; `IsSelfOrLibrarian` for `retrieve`, `update` and `partial_update`;
  - limit the queryset to the caller for anyone who is not a librarian.
- [x] T019 [P] [US1] In `library/book/api_views.py`, set `permission_classes = [ReadOnlyOrLibrarian]`
  on `BookViewSet`, and `[IsSignedIn]` on `BookSearchView`.
- [x] T020 [P] [US1] In `library/author/api_views.py`, set `permission_classes =
  [ReadOnlyOrLibrarian]` on `AuthorViewSet`.
- [x] T021 [US1] In `library/order/api_views.py` (contracts/access-control.md):
  - `OrderViewSet`:
    - `IsSignedIn` for `list` and `retrieve`, with a reader's queryset limited to their own loans;
    - `create` allowed for librarians, and for a reader only when `user` is themselves. Anything else
      gets 403 until KAN-57.
    - `IsLibrarian` for `update`, `partial_update` and `destroy`.
  - `UserOrderViewSet`:
    - `IsSelfOrLibrarian`;
    - 404 for a reader whose `user_id` is not their own;
    - a reader's `create` allowed for themselves.
- [x] T022 [US1] Update the existing tests to sign in with the role the new rules require:
  - the API calls in `library/book/tests.py` and `library/order/tests.py`, including the API path of
    `ConcurrentIssuanceTests.worker`, which signs in as the borrowing reader;
  - the tests in `library/book/test_delete.py`, `library/events/tests.py` and
    `library/authentication/tests.py` that expect a redirect home for a refused reader. They now
    expect 403.
- [x] T023 [US1] In `.github/workflows/docker-build.yml`, step "Verify key endpoints respond" (FR-006,
  R6):
  - assert that an anonymous `GET /api/v1/books/search/?q=detective` returns 401;
  - sign in as the seeded demo reader (`reader@library.com`, `reader123password`) with a curl cookie
    jar: GET `/authentication/login/` for `csrftoken`, then POST `email`, `password` and
    `csrfmiddlewaretoken` with a `Referer` header;
  - assert that the signed-in search returns 200;
  - keep `/api/docs/`, `/api/schema/`, `/api/v1/version/` and `/api/v1/` anonymous.
- [x] T024 [US1] Make the memory budget check sign in:
  - In `scripts/smoke_stack_budget.py`, sign in through the sign-in form with a cookie-jar opener
    before searching.
  - Add `--email`. Read the password from the `BUDGET_CHECK_PASSWORD` environment variable, or from
    `getpass` when it is unset, and never from the command line.
  - In `.github/workflows/docker-build.yml`, step "Verify the stack stays within the 4 GiB memory
    budget", pass `--email reader@library.com`, with `BUDGET_CHECK_PASSWORD: reader123password` in the
    step's `env`.
- [x] T025 [P] [US1] Update the docs. Describe the rules, not the earlier behavior (FR-060).
  - In `README.md`, add an Audience column to the REST API table, from contracts/access-control.md.
  - In `docs/deployment/raspberry-pi-portainer.md`:
    - update "Measure the stack on the Pi" for `--email` and `BUDGET_CHECK_PASSWORD`;
    - add "Review librarian accounts after an update" (R7): the admin filter
      `/admin/authentication/customuser/?role__exact=1`, what to change and what to record.
- [x] T026 [US1] Verify and prepare the pull request:
  - run quickstart.md §1.1 to §1.4 (tests, the anonymous and reader checks, the browser checks);
  - run lint, format and the local diff coverage (§0.1);
  - add the changelog entry;
  - write the description with the title `fix(authentication): require the right role for every
    account and API operation (KAN-24, KAN-62)`. Say what is enforced, and nothing about how the old
    behavior could be used.

  When the user asks, commit only this phase's files and open the pull request.
- [x] T027 [US1] (Pi) After the merge and deployment:
  - confirm that `/api/v1/version/` reports the merge commit;
  - review every librarian account (R7), and record the date, the number reviewed and each change in
    a comment on the pull request (FR-007);
  - delete the `specs/003-priority-tech-debt/` and `.specify/bridge-snapshots/` lines from
    `.git/info/exclude`, which ends the FR-060 hold.

**Checkpoint**: Story 1's live gap is closed in production, and the planning documents may now be
published.

---

## Phase 4: User Story 7: catalog pages stay fast as the catalog grows. PR 2, KAN-18 (Priority: P7)

**Goal**:
- Every list of books, authors, loans or accounts uses a fixed number of queries.
- The API's author list stops reading each author's books separately.
- The counts and the catalog's speed on the Pi are recorded.

**Independent Test**:
- Count each list's queries with 1 row and with 50, and compare them.
- Time the catalog pages on the Pi.

### Tests for User Story 7 (PR 2)

- [x] T028 [US7] Create branch `perf/kan-18-query-counts` from a freshly fetched `origin/main` after
  PR 1 is deployed. (Jira) Move KAN-18 to In Progress.
- [x] T029 [US7] When the user asks to commit, add `specs/003-priority-tech-debt/` as its own commit on
  this branch: the spec, the checklists, the plan, the research, the data model, the quickstart, the
  contracts and these tasks. Include the feature's bridge records: `.specify/superpowers-handoff.json`,
  `.specify/bridge-events.jsonl`, and the new `.specify/bridge-snapshots/` folders. It is the first
  commit after PR 1's deployment (FR-060, R1).
- [x] T030 [US7] Create `library/library/testing.py` with a helper (R8). It takes a test case, a client,
  a URL and a function that creates N rows, and:
  1. creates 1 row and records the query count with `django.test.utils.CaptureQueriesContext`;
  2. raises the total to 50 rows;
  3. asserts the same count.
- [x] T031 [P] [US7] Create `library/book/test_queries.py`. As a signed-in reader, with 1 and 50 books,
  these lists use the same number of queries:
  - the web book list, with and without `?author_id=`;
  - the API book list;
  - the API search, with `FakeEncoderMixin`.
- [x] T032 [P] [US7] Create `library/author/test_queries.py`. With each author linked to 3 books, the
  web author list (as a librarian) and the API author list use the same number of queries for 1 and
  50 authors. The API test fails until T036.
- [x] T033 [P] [US7] Create `library/authentication/test_queries.py`: the web user list and the API
  user list, as a librarian, with 1 and 50 accounts.
- [x] T034 [P] [US7] Create `library/order/test_queries.py`, with 1 and 50 loans:
  - all loans;
  - my loans;
  - a reader's books (`/book/user/<id>/`);
  - the API loan list;
  - the API list of one user's loans.
- [x] T035 [P] [US7] Create `library/events/test_queries.py`: the analytics dashboard, as a librarian,
  with 1 and 50 events.

### Implementation for User Story 7 (PR 2)

- [x] T036 [US7] In `library/author/api_views.py`, set `queryset =
  Author.objects.prefetch_related("books").order_by("id")` (FR-046). Record in
  `specs/003-priority-tech-debt/research.md` "Measurements", with the date and the method (FR-048):
  - the author list's query counts on `main` and after the fix;
  - the query count of every list.
- [x] T037 [US7] In `scripts/smoke_stack_budget.py`, add `--max-catalog-p95-ms` (SC-010):
  - load the signed-in catalog page `/book/` 60 times;
  - report the first load and the p95 in the JSON summary, and fail above the limit;
  - document it in `docs/deployment/raspberry-pi-portainer.md`, "Measure the stack on the Pi".
- [x] T038 [US7] Verify and prepare the pull request:
  - run quickstart.md §2 steps 1 and 2, lint, format and the local diff coverage;
  - add the changelog entry;
  - use the title `perf(author): load every list in a fixed number of queries (KAN-18)`.

  Commit and open it when the user asks.
- [ ] T039 [US7] After deployment:
  - (Pi) Run `smoke_stack_budget.py` with `--max-catalog-p95-ms 2000` (quickstart.md §2 step 3) and
    record the result in research.md "Measurements".
  - (Jira) Correct KAN-18's description to match the product (FR-058): availability is the total
    copies minus active loans, and, from KAN-56, minus active reservations; there is no order status
    field.

**Checkpoint**: Story 7 is done, and every list's query count is fixed by a test.

---

## Phase 5: User Story 8, part 1: tests catch regressions. PR 3, KAN-21 (Priority: P8)

**Goal**:
- Unit, integration and channel tests for books, authors, loans and every web route.
- Coverage of added and changed lines, reported on every pull request.
- The two defects found while planning are fixed.

**Independent Test**: read the coverage report on a pull request, and confirm that the author app has
tests.

### Tests for User Story 8 (PR 3)

- [x] T040 [US8] Create branch `test/kan-21-business-rules` from a freshly fetched `origin/main`, with
  PR 1 merged. (Jira) Move KAN-21 to In Progress.
- [x] T041 [P] [US8] Create `library/author/tests.py`:
  - creating, editing and deleting authors through the web (as a librarian), the API and the admin
    site;
  - `name`, `surname` and `patronymic` of 21 characters refused, since the limit is 20;
  - deletion refused, with its message, while books are attached;
  - the books an author is linked to, through the form and the API;
  - a reader refused for each change.
- [x] T042 [P] [US8] In `library/book/tests.py`:
  - add creating, editing and deleting books through the web, the API and the admin site;
  - test the limits: a 129-character name, a 257-character description and a negative `count` are
    refused. The negative count fails until T047.
  - refuse a reader for each change.
- [x] T043 [P] [US8] In `library/order/tests.py`, add every change of a loan in each channel, each with
  a permitted and a refused caller:
  - start: the web self-loan, the API, the admin site;
  - return: the web close action, the API, the admin site;
  - reopen;
  - reassign to another book, and to another reader;
  - delete: the API, the admin site.
- [x] T044 [P] [US8] Create `library/authentication/test_routes.py`: every web route in "Web routes" of
  contracts/access-control.md, with at least one permitted and one refused caller (FR-049).
- [x] T045 [P] [US8] In `library/authentication/tests.py`, add a test that saving a profile keeps the
  account's `created_at`. It fails until T046.

### Implementation for User Story 8 (PR 3)

- [x] T046 [US8] Fix defect 1 (R9). In `library/authentication/models.py`, declare `created_at =
  models.DateTimeField(editable=False, auto_now_add=True)`. Run `python manage.py makemigrations
  authentication` to create `library/authentication/migrations/0004_alter_customuser_created_at.py`,
  which changes Django's state only.
- [x] T047 [US8] Fix defect 2 (R9). In `library/book/models.py`, declare `count =
  models.IntegerField(default=DEFAULT_COUNT, validators=[MinValueValidator(0)])`; data-model.md §3
  says "`count` must be 0 or more".
  - Run `python manage.py makemigrations book` to create
    `library/book/migrations/0005_alter_book_count.py`.
  - Confirm that the web form, the API and the admin site refuse -1.
- [x] T048 [US8] Set up coverage:
  - pin `coverage==7.16.2` and `diff-cover==10.6.0` in `requirements-dev.txt`;
  - add `[tool.coverage.run]` to `pyproject.toml`: `relative_files = true`; `source` set to the app
    folders under `library/`; `omit` covering migrations, `tests.py`, `test_*.py` and `testing.py`;
  - add `[tool.coverage.report]` with `show_missing = true`;
  - ignore `library/.coverage`, `library/coverage.xml` and `diff-coverage.md` in `.gitignore`.
- [x] T049 [US8] In `.github/workflows/docker-build.yml`, on the `ubuntu-latest` leg only (R9, FR-051):
  1. check out with full history;
  2. in the web container, install the coverage version pinned in `requirements-dev.txt`;
  3. run the test command under `coverage run --rcfile=/app/pyproject.toml`, writing
     `library/coverage.xml` through the bind mount;
  4. on the runner, install diff-cover and run `diff-cover coverage.xml --compare-branch=origin/main
     --markdown-report ../diff-coverage.md` from `library/`;
  5. append the report to `$GITHUB_STEP_SUMMARY`;
  6. post or update one comment on the pull request with `gh pr comment --edit-last`, falling back to
     a new comment, with `continue-on-error: true` for forks.

  The other legs run the tests as today, and the report never fails the job.
- [x] T050 [US8] Review what the new tests found (FR-053):
  - fix in this branch any further defect that is small;
  - for a larger one, file a bug report with `.github/ISSUE_TEMPLATE/bug_report.md`, and note it for
    the register.
- [x] T051 [P] [US8] In `README.md`, "Tests and checks", document the coverage command, the report on
  every pull request, and the 85% target with its listed exceptions (SC-011).
- [x] T052 [US8] Verify and prepare the pull request:
  - run quickstart.md §3, lint and format;
  - record the pull request's diff coverage in research.md "Measurements";
  - add the changelog entry;
  - in the description, record the constitution review that a CI change requires. No amendment is
    needed, because the report is not a gate (R29).
  - use the title `test(order): cover the book, author and loan rules and report coverage (KAN-21)`.

  Commit and open it when the user asks.

**Checkpoint**: every business rule has a test, and every later pull request gets a coverage report.

---

## Phase 6: User Story 8, part 2: merge rules on `main`. KAN-72, KAN-73 and KAN-74, repository settings (Priority: P8)

**Goal**: lint, code scanning and a code owner's approval become merge requirements (FR-052).

**Independent Test**: a pull request that breaks one rule cannot be merged.

These tasks change repository settings, not files. They can run at any time, in parallel with the
other phases.

- [ ] T053 [US8] (Arsen) KAN-72: add `lint` to the required status checks of ruleset 23898585 for
  `main`, beside `smoke-test` (R27). The check's name comes from the `lint` job in
  `.github/workflows/docker-build.yml`.
- [ ] T054 [US8] (Arsen) KAN-73: add the ruleset's "Require code scanning results" rule for CodeQL,
  with security alerts set to "High or higher" and alerts set to "Errors". The analysis comes from
  `.github/workflows/codeql.yml`.
- [ ] T055 [US8] (Arsen) KAN-74: turn on "Require review from Code Owners" in ruleset 23898585, so that
  `.github/CODEOWNERS` is enforced.
- [ ] T056 [US8] Record the evidence (SC-012, quickstart.md §12):
  - save the output of `gh api repos/Arezzon/Library-Django/rulesets/23898585` after each change;
  - open one draft pull request per rule: a lint error, a failing test, a new CodeQL alert, and one
    without a code owner's approval;
  - confirm that each shows merging as blocked;
  - link them in research.md "Measurements", then close them.

**Checkpoint**: Story 8 is done.

---

## Phase 7: User Story 4: the library keeps its data and can be restored. PR 9, KAN-68 (Priority: P4)

**Goal**:
- Daily, checked backups, kept in their own volume for 7 days, with a weekly copy to another machine.
- A restore that is rehearsed in CI on every run, and once on the Pi.
- Persistence and the hosting limits, measured.

**Independent Test**:
- Count the records, then restart every service, redeploy and reboot. The counts must match each
  time.
- Restore the latest backup into a separate database by following the guide. Check the counts, a
  librarian sign-in and a search.

### Tests for User Story 4 (PR 9)

- [x] T057 [US4] Create branch `feat/kan-68-backups` from a freshly fetched `origin/main`. (Jira) Move
  KAN-68 to In Progress. This branch may open before PR 1 merges, but it merges after it (FR-060).
- [x] T058 [P] [US4] In `library/authentication/tests.py`, `ComposeServiceImagesTests`, add tests
  (FR-026):
  - both stacks define a `backup` service with the same `image` as `db`, and the same `entrypoint`,
    `command` and `environment` keys;
  - it mounts `pgbackups:/backups`;
  - `pgbackups` is a declared volume, distinct from `pgdata18`.

  They fail until T060.

### Implementation for User Story 4 (PR 9)

- [x] T059 [US4] Add the `backup` service and the `pgbackups` volume to `docker-compose.yml`
  (contracts/backups.md).
  - **Service settings**:
    - image `pgvector/pgvector:0.8.7-pg18`;
    - `restart: unless-stopped`;
    - `depends_on` the `db` service being healthy;
    - environment: `PGHOST: db`, `PGDATABASE: ${DB_NAME:-library_db}`, `PGUSER:
      ${DB_USER:-postgres}`, `PGPASSWORD: ${DB_PASSWORD:?Set DB_PASSWORD in the Portainer stack
      environment}`, `BACKUP_HOUR: ${BACKUP_HOUR:-1}`, `BACKUP_KEEP_DAYS: ${BACKUP_KEEP_DAYS:-7}`;
    - volume `pgbackups:/backups`.
  - **Entrypoint**: an inline POSIX `sh` script, with `$$` for shell variables. It writes
    `/usr/local/bin/library-backup` and runs `library-backup loop`.
  - **`library-backup once`** runs one backup with `umask 077` (FR-025, FR-027):
    1. `pg_dump --format=custom` to `/backups/library-<UTC %Y%m%dT%H%M%SZ>.dump.partial`;
    2. `pg_restore --list`, then `pg_restore --file=/dev/null`;
    3. `sha256sum` of the file name, run inside `/backups`, into `<file>.sha256`;
    4. the rename;
    5. pruning: only files older than `BACKUP_KEEP_DAYS` that are not among the 7 newest are deleted.
  - **Its log line on success**: `<UTC ms>Z INFO backup - backup: created … (<size>) in <s> s; check
    passed; <n> kept, <m> removed`.
  - **On any failure**: it logs `… ERROR backup - backup: failed at <step>: <message>; earlier
    backups kept`, deletes the partial file, and exits non-zero.
  - **`library-backup loop`** checks every 600 s. It runs `once` when no backup from today (UTC)
    exists and the UTC hour is at least `BACKUP_HOUR`.
- [x] T060 [US4] Add the identical `backup` service and `pgbackups` volume to `docker-compose-dev.yml`,
  with the `.env` wording for the required `DB_PASSWORD`, so that T058 passes.
- [x] T061 [US4] In `.github/workflows/docker-build.yml`, add "Verify a backup restores" on every
  smoke-test runner, after the stack starts (contracts/backups.md, "CI check"):
  1. run `docker compose -f docker-compose-dev.yml exec -T backup library-backup once`;
  2. create `library_restore`;
  3. from the backup container, restore the newest file into it with `pg_restore --no-owner
     --exit-on-error`;
  4. compare the exact row count of every table in schema `public` between `library_db` and
     `library_restore`;
  5. drop `library_restore`.

  Fail on any difference.
- [x] T062 [P] [US4] In `docs/deployment/raspberry-pi-portainer.md`:
  - Replace "Backup and restore" with the sections in contracts/backups.md:
    - daily backups: the schedule, the files, their status and running one now. Backups hold password
      hashes and personal data, and only the operator can read them (FR-028).
    - the weekly copy to another machine;
    - restoring into a separate database;
    - restoring after losing the database;
    - the rehearsal record.
  - Add "Check data persistence and limits", with quickstart.md §9.4.
  - Add `BACKUP_HOUR` and `BACKUP_KEEP_DAYS` to the environment table.
- [x] T063 [P] [US4] Create `docs/adr/0003-database-backups.md`, covering the sidecar on the database
  image, the checks and retention, and the weekly manual off-device copy with its risk. Create
  `docs/adr/README.md` with an index if it does not exist yet.
- [x] T064 [P] [US4] Document `BACKUP_HOUR` and `BACKUP_KEEP_DAYS`, commented and with their defaults,
  in `.env.example` and in the "Configuration" table of `README.md`. Describe backups in the
  "Deployment" section of `README.md`.
- [x] T065 [US4] Constitution PATCH amendment (R29), in `.specify/memory/constitution.md`. With the
  handoff set to `blocked`, use `/speckit-constitution` to add:
  - `backup` to Principle VI's list of the stack's services;
  - the backup-and-restore check to the smoke-test in workflow item 4.

  Add its changelog entry, then set the handoff back.
- [x] T066 [US4] Verify and prepare the pull request:
  - run quickstart.md §9.1 to §9.3: one backup and a trial restore, retention with fake files, and a
    failure with `db` stopped;
  - confirm that CI's memory check includes the new service;
  - run lint and format, and add the changelog entry;
  - use the title `feat(deploy): back up the database daily and rehearse a restore (KAN-68)`.

  Commit and open it when the user asks.
- [ ] T067 [US4] (Pi) After deployment, follow quickstart.md §9.4 and record each result in
  research.md "Measurements":
  - the next day's backup log line;
  - a weekly copy, checked on another machine;
  - the restore rehearsal: date, operator, file and size, duration, counts, sign-in, search and peak
    memory (FR-029, SC-006);
  - persistence after restarting each service, after a redeploy and after a reboot, with the time
    until pages are served (FR-030, SC-005);
  - the first catalog load after 24 hours idle;
  - memory; the disk used by the volumes and the logs; free space; and confirmation that the old
    hosting is gone (FR-031, FR-033);
  - that no uploaded files exist (FR-032).

**Checkpoint**: Story 4 is done once the rehearsal and the persistence checks are recorded.

---

## Phase 8: User Story 5: failures and critical changes can be traced without exposing secrets. PR 8, KAN-67 (Priority: P5)

**Goal**:
- One log line format with a request identifier that follows the request into the worker.
- Redaction, rotation and a configurable level.
- An unchangeable audit entry for every critical change, written with the change.

**Independent Test**:
- Find every log line of a failing request, from web and worker, by its identifier.
- Make each critical change and find its audit entry.
- Search every log line and audit entry from the tests and the smoke test for secrets and search
  text.

### Tests for User Story 5 (PR 8)

- [x] T068 [US5] Create branch `feat/kan-67-logs-and-audit` from a freshly fetched `origin/main`, with
  PR 1 merged. (Jira) Move KAN-67 to In Progress.
- [x] T069 [P] [US5] Create `library/authentication/test_logging.py` (contracts/logs-and-audit.md):
  - **Format**: a record renders `<UTC time with ms>Z <LEVEL> <service> <request id or -> <logger>:
    <message>`, and every traceback line repeats the header followed by `| `.
  - **Request id**:
    - a request without `X-Request-ID` gets a 32-character hex id in the response header;
    - a valid incoming id (`[A-Za-z0-9._-]{8,64}`) is kept, and an invalid one is replaced;
    - the `before_task_publish` handler copies the id into the headers, and `task_prerun` restores
      it, using the task id when there is none.
  - **Redaction** covers:
    - `password=`;
    - the literal `SECRET_KEY` and `DB_PASSWORD` values;
    - the `sessionid`, `csrftoken`, `Authorization` and `Cookie` values;
    - the password in `postgres://user:pass@host`;
    - the `q` parameter in URLs.
  - **Failed sign-in**: it logs "Sign-in failed for account #<id>" or "Sign-in failed for an unknown
    account", and never the email or the password.
  - **Existing test**: update `ProductionErrorLoggingTests` in `library/authentication/tests.py` to
    capture the new handler.
- [x] T070 [P] [US5] Create `library/audit/tests.py`:
  - **One entry each**: exactly one entry for each action in data-model.md §5, when made through the
    web, the API, the admin site and a management command. Each records the actor, the channel, the
    before and after values of the changed fields only, and the request id.
  - **Rollback**: no entry when an outer transaction rolls the change back (Story 5 scenario 3).
    Patching `AuditEntry.objects.create` to raise rolls the change back (FR-040).
  - **No changes**: entries cannot be updated or deleted through the model, the queryset or the admin
    site, and no URL under `/api/` exposes them (FR-038).
  - **Survival**: entries outlive the account or book they describe.
  - **No secrets**: no `before` or `after` value holds a password or a hash (FR-039).
  - **Readers**: a reader cannot open `/admin/audit/auditentry/`.
  - **Account guard**: `CustomUser.objects.filter(…).update(role=…)`, and the same for `is_active`,
    raises `ValueError`.
- [x] T071 [P] [US5] Add guard tests:
  - In `library/book/tests.py`, change the two tests that bulk-update `count` (the availability test
    and the "bulk stock updates" test) to use `save()`. Add a test that
    `Book.objects.filter(…).update(count=…)` raises `ValueError`.
  - In `library/order/tests.py`, test that `Order.objects.filter(…).update(end_at=…)` raises, and the
    same for `book` and `user` and for `bulk_create()`.

### Implementation for User Story 5 (PR 8)

- [x] T072 [US5] Create `library/library/logs.py` (R18, R19, FR-034, FR-035, FR-039):
  - a request-id `ContextVar`;
  - a filter that adds `request_id` (or `-`) and `service`;
  - a formatter that:
    - writes the header in UTC, with milliseconds;
    - repeats it, followed by `| `, on every continuation line;
    - applies the redaction rules in contracts/logs-and-audit.md to messages and exception text;
  - `build_logging_config(service, level)`, which returns a `dictConfig` with one stream handler for
    the root logger, `django`, `django.request` (at WARNING), `celery`, `gunicorn.error` and the app
    loggers, all at `level`.
- [x] T073 [US5] Create `library/library/middleware.py` with `RequestIdMiddleware`. It accepts an
  `X-Request-ID` that matches `^[A-Za-z0-9._-]{8,64}$` and otherwise uses `uuid.uuid4().hex`. It
  sets the context variable, adds the response header, and resets the variable afterwards. In
  `library/library/settings.py`:
  - put `RequestIdMiddleware` first in `MIDDLEWARE`;
  - replace `LOGGING` with `build_logging_config("web", os.getenv("LOG_LEVEL", "INFO"))`.
- [x] T074 [US5] In `library/library/celery.py`, connect these signals:
  - `setup_logging`, which applies `build_logging_config("worker", LOG_LEVEL)`;
  - `before_task_publish`, which adds the current request id to the message headers;
  - `task_prerun`, which sets the context variable from the task's headers, or from its task id;
  - `task_postrun`, which resets it.
- [x] T075 [P] [US5] In `library/gunicorn.conf.py`, set `logconfig_dict = build_logging_config("web",
  …)` and `loglevel` from `LOG_LEVEL`. Keep the access log off, with a comment that URLs can carry
  search text.
- [x] T076 [P] [US5] In `entrypoint.sh`, add a `log` function that prints `$(date -u
  +%Y-%m-%dT%H:%M:%S.%3NZ) INFO web - entrypoint: <message>`, and use it for every startup message.
- [x] T077 [P] [US5] Create `library/authentication/signals.py` with a `user_login_failed` receiver.
  It logs at WARNING "Sign-in failed for account #<id>" when the normalized email matches an account,
  and "Sign-in failed for an unknown account" otherwise. Connect it in `AuthenticationConfig.ready()`
  in `library/authentication/apps.py`.
- [x] T078 [US5] Create the `audit` app: `library/audit/__init__.py`, `library/audit/apps.py` and
  `library/audit/models.py`.
  - **`AuditEntry` fields**, as in data-model.md §5:

    | Field | Definition |
    |---|---|
    | `occurred_at` | "`DateTimeField`, default `timezone.now`, indexed" |
    | `actor_id` | "`PositiveBigIntegerField`, nullable" |
    | `actor_label` | "`CharField(150)`" |
    | `action` | "`CharField(32)`", with the 16 actions |
    | `target_type` | "`CharField(16)`, choices `account`, `loan`, `reservation`, `book`" |
    | `target_id` | "`PositiveBigIntegerField`" |
    | `target_label` | "`CharField(200)`" |
    | `before`, `after` | "`JSONField`, default `{}`" |
    | `reason` | "`CharField(500)`, blank" |
    | `channel` | "`CharField(8)`, choices `web`, `api`, `admin`, `command`, `system`" |
    | `request_id` | "`CharField(64)`, blank" |

  - **Indexes**: `(target_type, target_id)`, `(occurred_at)` and `(actor_id, occurred_at)`.
  - **No changes**: `save()` refuses updates and `delete()` refuses. A custom queryset's `update()`
    and `delete()` also refuse.
  - **Install**: add `"audit"` to `INSTALLED_APPS` in `library/library/settings.py`, then run `python
    manage.py makemigrations audit` to create `library/audit/migrations/0001_initial.py`.
- [x] T079 [US5] Wire the audit context and service (FR-037):
  - Create `library/audit/context.py`: a context variable holding the actor, the channel and the
    request id, and `audit_context(actor=None, channel="command", reason=None)`. By default the
    channel is `command` and there is no actor.
  - Create `library/audit/services.py` with `record(action, target_type, target_id, target_label,
    before, after, reason="")`. It writes inside the caller's transaction, with the context's channel
    and request id and the actor label "First Last (#id)", or "system".
  - Add `library/audit/middleware.py`, after `AuthenticationMiddleware` in settings. It sets the actor
    to the signed-in user, and the channel from the path: `/admin/` is admin, `/api/` is api,
    anything else is web.
  - In `task_prerun` in `library/library/celery.py`, set the channel to `system`, with no actor.
- [x] T080 [P] [US5] Create `library/audit/admin.py` with a read-only `AuditEntryAdmin`:
  - it lists the time, action, actor, target and channel;
  - it filters by action, channel and date, and searches the labels;
  - `has_add_permission`, `has_change_permission` and `has_delete_permission` return `False`.
- [x] T081 [US5] In `library/authentication/models.py`:
  - wrap `CustomUser.save()` in `transaction.atomic`, and compare with the previous row, locked with
    `select_for_update`;
  - record `role_granted` or `role_removed`, including for an account created as a librarian, and
    `account_activated` or `account_deactivated`;
  - add a `post_delete` receiver that records `account_deleted`;
  - give `CustomUserManager` a queryset, through `from_queryset`, whose `update()` refuses `role` and
    `is_active`.
- [x] T082 [US5] In `library/order/models.py` (data-model.md §2):
  - inside `Order.save()`'s existing atomic block, also read `user_id` and `plated_end_at` from the
    locked previous row;
  - record `loan_started`, `loan_returned`, `loan_reopened` or `loan_reassigned`;
  - add a `post_delete` receiver that records `loan_deleted`. It also covers loans deleted along with
    their account.
  - make `OrderQuerySet` the manager. It refuses `update()` of `end_at`, `book` and `user`, and
    `bulk_create()`.
- [x] T083 [US5] In `library/book/models.py`:
  - `Book.save()` records `book_copies_changed` when `count` differs from the locked previous row;
  - a `post_delete` receiver records `book_deleted`;
  - `BookQuerySet.update()` refuses `count`, with "Book stock update bypasses the audit trail; use
    save().".
- [x] T084 [P] [US5] Make the request id visible in the worker:
  - in `library/events/tasks.py`, log "Persisted event <id>" at INFO in `persist_event`, without the
    payload;
  - in `library/events/management/commands/smoke_test_tracking.py`, send every request with a known
    `X-Request-ID` (`smoke-` followed by a UUID4 hex), and print `REQUEST_ID=<id>`.
- [x] T085 [US5] In `docker-compose.yml` and `docker-compose-dev.yml` (FR-036):
  - add an `x-logging` anchor to every service: `driver: json-file`, with options `max-size: "10m"`
    and `max-file: "5"`;
  - add `LOG_LEVEL: ${LOG_LEVEL:-INFO}` to the shared app environment;
  - let the worker's level follow it.
- [x] T086 [US5] In `.github/workflows/docker-build.yml`:
  - add `audit` to the test command, and `tee` its output to a file;
  - after `smoke_test_tracking`, assert that the worker's log holds its `REQUEST_ID` (SC-008);
  - add "Verify the logs hold no secrets or search text" (SC-007). It searches `docker compose logs
    --no-color` for every service, plus the test output, for:
    - the run's `SECRET_KEY` and `DB_PASSWORD`;
    - the four demo passwords;
    - the search word `detective`.

    It fails on any match.
- [x] T087 [P] [US5] Update ownership and docs:
  - add `/library/audit/ @fazelukario @Arezzon` to `.github/CODEOWNERS`;
  - add `audit` to the test command in `AGENTS.md` and `README.md`, and to "Project layout" in the
    README;
  - document `LOG_LEVEL` in `.env.example` and in the README's "Configuration";
  - in "Viewing logs" in `docs/deployment/raspberry-pi-portainer.md`, describe:
    - the line format;
    - finding a request by its identifier in web and worker;
    - rotation and its limit;
    - `LOG_LEVEL`;
    - where librarians read audit entries.
- [x] T088 [P] [US5] Create `docs/adr/0002-audit-trail.md`: audit entries as part of the business
  record, their own app, where they are written, and the alternatives rejected in R21. Create
  `docs/adr/README.md` if it does not exist yet.
- [x] T089 [US5] Constitution MINOR amendment (R29), in `.specify/memory/constitution.md`. With the
  handoff set to `blocked`, use `/speckit-constitution` to make these changes:
  - Principle I lists `audit`.
  - Principle V adds "a critical change with its audit entry" to the writes that succeed or fail
    together, and says that audit entries are part of the business record.
  - In workflow item 4, the test command includes `audit`, and the smoke-test checks the logs for
    secrets.

  Add the changelog entry, then set the handoff back.
- [x] T090 [US5] Verify and prepare the pull request:
  - run quickstart.md §8, CI's memory check, lint, format and the diff coverage;
  - add the changelog entry;
  - use the title `feat(audit): add technical logs and an audit trail of critical changes (KAN-67)`.

  Commit and open it when the user asks.

**Checkpoint**: Story 5 is done. Every reservation stage from here on writes its own audit entries.

---

## Phase 9: User Story 2, part 1: the reservation model. PR 4, KAN-55 (Priority: P2)

**Goal**:
- The reservation, its four states, its constraints and ADR 0001.
- Books with loans or reservations cannot be deleted in any channel.

**Independent Test**:
- Migrate a seeded database: no existing row changes.
- Try to delete a book that has a loan through the web, the API and the admin site: all three
  refuse.

### Tests for User Story 2 (PR 4)

- [ ] T091 [US2] Create branch `feat/kan-55-reservation-model` from a freshly fetched `origin/main`,
  with PR 1 merged. (Jira) Move KAN-55 to In Progress.
- [ ] T092 [P] [US2] Create `library/order/test_reservations.py` with model tests:
  - `expires_at` is exactly 48 hours after `created_at`, and the database refuses any other value
    (`reservation_lasts_48_hours`);
  - only active to issued, cancelled or expired is allowed, and the final states refuse every change;
  - a second active reservation of the same book by the same reader violates
    `one_active_reservation_per_reader_and_book`;
  - a cancelled reservation without `cancelled_at` violates `cancelled_reservation_has_time`;
  - `Reservation.objects` refuses `update()`, `bulk_update()` and `bulk_create()` of `state`, `loan`
    and the `cancel*` fields.
- [ ] T093 [P] [US2] In `library/book/test_delete.py`, add that a book with a loan or a reservation
  cannot be deleted in any channel (FR-024):
  - the ORM raises `ProtectedError`;
  - the web shows the history message;
  - the API answers 409;
  - the admin site shows its protected-objects page.

  The book and its loans remain.

### Implementation for User Story 2 (PR 4)

- [ ] T094 [US2] In `library/order/models.py`, add `ReservationState` (TextChoices `active`, `issued`,
  `cancelled`, `expired`), `RESERVATION_HOURS = 48`, the guarded `ReservationQuerySet`, and
  `Reservation`.
  - **Fields**, as in data-model.md §1:

    | Field | Definition |
    |---|---|
    | `user` | "FK `CustomUser`, `CASCADE`, `related_name="reservations"`" |
    | `book` | "FK `Book`, `PROTECT`, `related_name="reservations"`" |
    | `state` | "`CharField(16)`, choices `active`, `issued`, `cancelled`, `expired`; default `active`" |
    | `created_at` | "`DateTimeField`, default `timezone.now`, not editable" |
    | `expires_at` | "`DateTimeField`": `created_at` plus 48 hours, set once in `save()` on creation |
    | `loan` | "`OneToOneField(Order)`, `SET_NULL`, nullable, `related_name="reservation"`" |
    | `cancelled_by` | "FK `CustomUser`, `SET_NULL`, nullable, `related_name="+"`" |
    | `cancelled_at` | "`DateTimeField`, nullable" |
    | `cancel_reason` | "`CharField(500)`, blank" |
    | `cancellation_seen_at` | "`DateTimeField`, nullable" |

  - **Constraints and indexes**: the three constraints, and indexes on `(book, state, expires_at)`,
    `(user, state)` and `(state, expires_at)`.
  - **Methods**: `effective_state(now)`, and one transition method that allows only the changes in
    FR-014.
  - **Loans**: change `Order.book` to `on_delete=models.PROTECT`.
- [ ] T095 [US2] Run `python manage.py makemigrations order` to create
  `library/order/migrations/0004_reservation.py`. Confirm that it holds only the new model, with its
  constraints and indexes, and the `Order.book` change (FR-022).
- [ ] T096 [P] [US2] In `library/order/admin.py`, add a read-only `ReservationAdmin` showing the reader,
  the book, the state, the creation time and the deadline, with no add, change or delete.
- [ ] T097 [US2] Make deleting a book refuse in every channel:
  - In `library/book/views.py`, make `book_delete` catch `ProtectedError` instead of querying loans,
    with the message "This book cannot be deleted because it has borrowing or reservation history.".
  - In `library/book/api_views.py`, make `BookViewSet.destroy` answer 409 with the same message, and
    document the 409 with `extend_schema`.
- [ ] T098 [P] [US2] Create `docs/adr/0001-reservations-hold-a-unit-of-stock.md`. It ships with the
  reservation model (FR-008, FR-057), and covers:
  - the context and the decision;
  - the rejected alternative of tracking physical copies;
  - how active loans and reservations reduce availability;
  - the states and the transitions.

  Add it to `docs/adr/README.md`, creating the index if it does not exist yet.
- [ ] T099 [US2] Verify and prepare the pull request:
  - run quickstart.md §4: migrate a seeded `main` database and compare the counts, and check that
    deletion is refused in every channel;
  - run lint, format and the diff coverage;
  - add the changelog entry;
  - use the title `feat(order): add the reservation model and its states (KAN-55)`.

  Commit and open it when the user asks.

**Checkpoint**: the model is in place, with no change of behavior for readers, so the site stays
usable (FR-061).

---

## Phase 10: User Story 2, part 2: a reader reserves an available book for 48 hours. PR 5, KAN-56 (Priority: P2)

**Goal**:
- Readers reserve through the web and the API.
- Availability counts reservations, and the limits and the overdue block hold under simultaneous
  requests.
- Expiry works with no job running, and a schedule records it.
- Times are shown in Kyiv time.

**Independent Test**:
- Give a book exactly one copy, and have two readers reserve it at the same moment.
- Check that the held copy cannot be lent to someone else.
- Let the deadline pass, and check availability again.

### Tests for User Story 2 (PR 5)

- [ ] T100 [US2] Create branch `feat/kan-56-reserve-a-book`, either from a freshly fetched `origin/main`
  with PR 4 merged, or from PR 4's verified branch. (Jira) Move KAN-56 to In Progress.
- [ ] T101 [P] [US2] In `library/order/test_reservations.py`, add Story 2's scenarios through the web
  and the API:
  - A reservation is active at once, with a deadline exactly 48 hours later. The available count
    drops by one on the catalog, the book page, search and the API (scenario 1, FR-010).
  - Refusals carry their 409 codes and messages from contracts/reservations-api.md (scenarios 2, 6, 8
    and 9):
    - `no_copy_available`;
    - `already_reserved`;
    - `already_on_loan`;
    - `reservation_limit`, for a 4th reservation;
    - `overdue_loan`, naming the book and its due date. A loan counts as overdue the moment its due
      date passes.
  - My reservations shows the state, the deadline in Kyiv time with its zone, and the next step
    (scenario 7).
  - With `django.utils.timezone.now` patched, an expired reservation stops reducing availability at
    exactly 48 hours, with no task run, and reads `expired` (scenario 5, FR-013, SC-004).
  - A reader's own loan of a book they reserved issues the reservation, and leaves the count
    unchanged (FR-061).
  - With the event broker unavailable, reserving still works.
- [ ] T102 [US2] In `library/order/test_reservations.py`, add races in a `TransactionTestCase`, using
  `threading.Barrier`, `ThreadPoolExecutor` and `connections.close_all()` as in
  `ConcurrentIssuanceTests` (FR-050, SC-002):
  - 20 readers reserving the last copy succeed exactly once, in each of 20 repeated runs;
  - a reservation racing a loan of the last copy succeeds exactly once;
  - one reader sending 5 reservations for 5 books at once ends with at most 3 active.
- [ ] T103 [P] [US2] In `library/book/tests.py`, add tests that:
  - `with_availability()` and `available_count` subtract active, unexpired reservations, never go
    below 0, and keep the query count constant;
  - lowering a book's total below its active loans and reservations shows a warning on the edit
    page.
- [ ] T104 [P] [US2] In `library/order/test_queries.py`, add the reader's reservation page and the API
  reservation list, with 1 and 50 reservations.

### Implementation for User Story 2 (PR 5)

- [ ] T105 [US2] In `library/book/models.py` (FR-009, R12):
  - make `with_availability(now=None)` also annotate
    `active_reservation_count=Count("reservations", filter=Q(reservations__state="active",
    reservations__expires_at__gt=now), distinct=True)`;
  - make `available_count` subtract it, never going below 0, with the fallback aggregate when the
    queryset is not annotated.
- [ ] T106 [US2] Create `library/order/services.py`:
  - **`ReservationRefused(code, message, **context)`**, with the codes, and the readers' and
    librarians' messages, from contracts/reservations-api.md.
  - **`eligibility(reader, book, now)`**: the same rules without locks, for display.
  - **`reserve(reader, book, *, now=None)`**, in `transaction.atomic`. These are the one implementation
    of FR-011 and FR-012:
    1. lock the reader's account row, then the book row;
    2. expire the reader's and the book's due reservations;
    3. check the rules in R13's order;
    4. create the reservation.
  - **`lend(actor, reader, book, days, *, now=None)`**:
    1. lock the reader, then the book;
    2. apply the overdue block and the on-loan check;
    3. issue the reader's effectively active reservation of the book if there is one, and otherwise
       create the loan through `Order.save()`.

    In this PR, a reader may lend only to themselves.
  - **`expire_due(now)`**.
  - **Audit**: record `reservation_created`, `reservation_issued` and `reservation_expired` with
    `audit.services.record`. Expiries have no actor and channel `system`.
- [ ] T107 [US2] Schedule the expiry and switch to Kyiv time (R16):
  - Create `library/order/tasks.py` with the `expire_reservations` task. It calls
    `expire_due(timezone.now())`, locking rows with `skip_locked=True`, and logs the count.
  - In `library/library/settings.py`, add `CELERY_BEAT_SCHEDULE` to run
    `order.tasks.expire_reservations` every 300 seconds, and set `TIME_ZONE = "Europe/Kyiv"`.
  - Adjust the analytics tests in `library/events/tests.py` that assume UTC days.
- [ ] T108 [US2] In `docker-compose.yml` and `docker-compose-dev.yml`, add `--beat
  --schedule=/tmp/celerybeat-schedule` to the worker's command, and update the comment that says it
  only runs queued events (R11).
- [ ] T109 [US2] In `library/order/views.py` and `library/order/urls.py`:
  - add `reserve`: POST `/order/reserve/<book_id>/`, for signed-in callers. Success redirects to My
    reservations, with the deadline in the message. A refusal returns to the book page with its
    message.
  - add `reservation_my`: GET `/order/reservations/`, the reader's reservations with their effective
    state;
  - make `order_create` lend through `services.lend()`.
- [ ] T110 [US2] Add the pages (FR-023, FR-061):
  - Create `library/order/templates/order/reservation_my.html`. It shows the state, the creation time,
    the deadline and the next step, with times as `|date:"j M Y, H:i T"`, plus messages and an empty
    state.
  - In `library/book/templates/book/book_detail.html`:
    - add the Reserve button, a POST form with CSRF that carries `data-track-event="borrow_intent"`
      and `data-book-id`;
    - show the reason from `eligibility()` when reserving is not possible;
    - keep the self-loan link, without tracking attributes, until PR 6.
- [ ] T111 [US2] Add the reservation API, in `library/order/serializers.py` and
  `library/order/api_views.py`:
  - `ReservationSerializer`, with the fields in contracts/reservations-api.md. `state` is the
    effective state, and `cancelled_by` is shown only to librarians.
  - `ReservationViewSet`, with `list`, `retrieve` and `create`, and `permission_classes =
    [IsSignedIn]`:
    - readers see their own reservations;
    - active ones come first, by deadline, then the rest, newest first;
    - `?state=` filters the list;
    - `create` calls `services.reserve(request.user, book)` and answers 201, or 409 with `code` and
      `detail`.
  - `extend_schema` for the query parameter and the 409.
  - `reservation`, registered in `library/library/api_urls.py`.
- [ ] T112 [P] [US2] In `library/book/views.py`, warn the librarian after saving a book whose total is
  below its active loans plus active reservations. In `library/book/admin.py`, show the available
  count from `with_availability()`.
- [ ] T113 [P] [US2] Document the reader's side:
  - create `docs/features/reservations.md` with the reader's side: reserving, the 48 hours, the limit
    of 3, the overdue block, collecting the book, and expiry;
  - add reservations, with their audiences, to the README's "Features" and its REST API table;
  - note in the README that API datetimes now carry the Kyiv offset.
- [ ] T114 [US2] Verify and prepare the pull request:
  - run quickstart.md §5;
  - run CI's memory check with beat running, and record the result in research.md "Measurements";
  - run lint, format and the diff coverage;
  - add the changelog entry;
  - use the title `feat(order): let readers reserve an available book for 48 hours (KAN-56)`.

  Commit and open it when the user asks.

**Checkpoint**: Story 2 works on its own. Readers can still get books, either by lending to
themselves or by reserving (FR-061).

---

## Phase 11: User Story 3, part 1: a librarian issues a reserved book or cancels with a reason. PR 6, KAN-57 (Priority: P3)

**Goal**:
- Only librarians issue and lend.
- Issuing a reservation is one atomic step that never starts a second loan.
- Cancellations by the library carry a reason, and the reader sees them.
- A loan a librarian starts counts as the reader's borrow.

**Independent Test**:
- As a librarian, issue a reservation twice; exactly one loan results.
- Try to issue an expired reservation.
- Cancel one with a reason, and check the copy, the audit entry and the reader's notice.
- As a reader, try to lend, to issue, and to cancel someone else's reservation.

### Tests for User Story 3 (PR 6)

- [ ] T115 [US3] Create branch `feat/kan-57-issue-at-the-desk`, either from a freshly fetched
  `origin/main` with PR 5 merged, or from PR 5's verified branch. (Jira) Move KAN-57 to In Progress.
- [ ] T116 [P] [US3] In `library/order/test_reservations.py`, add Story 3's scenarios:
  - Issuing creates exactly one loan with the chosen period (14 days by default, 1 to 30) and leaves
    the available count unchanged (scenario 1).
  - A second issue, and two librarians issuing at once in a `TransactionTestCase` race, leave one
    loan and answer `already_issued` with the loan's id (scenario 2).
  - An expired reservation answers `reservation_expired` (scenario 3).
  - Issuing one second before the deadline succeeds, and at the deadline it is refused (scenario 9).
  - A librarian's cancellation needs a reason of 1 to 500 characters. It frees the copy and is
    audited with the librarian, the time and the reason (scenarios 4 and 5).
  - A reader's own cancellation needs no reason, and another reader's attempt answers 404 (scenario 8,
    FR-018).
  - A reader cannot start a loan, issue a reservation, or cancel another reader's, through the web or
    the API (scenario 7).
  - An overdue reader can neither be issued a reserved book nor be lent one, and the librarian sees
    the overdue book (scenario 11).
  - The overdue rule does not block reopening or reassigning a loan.
  - A loan that a reader started before this PR can still be returned.
  - Issuing and cancelling work while the event broker is unavailable.
- [ ] T117 [US3] In `library/order/test_reservations.py`, add the notice (FR-017, R15):
  - after a librarian's cancellation, the reader's next page shows the book, the time and the reason;
  - GET requests write nothing;
  - the Dismiss POST sets `cancellation_seen_at`, and the notice disappears;
  - a reader's own cancellation shows no notice.
- [ ] T118 [P] [US3] In `library/events/tests.py`, add that a loan started by a librarian records
  `order_created` for the reader, with `properties.issued_by` set to the librarian's id, and that the
  dashboard counts it as the reader's borrow (FR-023, scenario 10).

### Implementation for User Story 3 (PR 6)

- [ ] T119 [US3] In `library/order/services.py`:
  - add `issue(actor, reservation, days, *, now=None)` (FR-015):
    1. lock the reservation row, then the reader, then the book;
    2. check the state, the deadline at commit, and the overdue block;
    3. mark the reservation issued;
    4. create the loan with `plated_end_at = now + days`, and link it;
    5. audit `reservation_issued`.
  - add `cancel(actor, reservation, reason="", *, now=None)`:
    - the owner cancels without a reason;
    - a librarian cancelling someone else's reservation gives a reason of 1 to 500 characters;
    - anyone else is not permitted;
    - it records `cancelled_by`, `cancelled_at` and `cancel_reason`, and audits
      `reservation_cancelled` with the reason.
  - make `lend()` librarian-only, under the same availability rule (FR-016).
- [ ] T120 [US3] In `library/order/forms.py`, add:
  - `IssueForm`: `days`, from 1 to 30, initial 14;
  - `CancelForm`: `reason`, up to 500 characters, required when a librarian cancels someone else's
    reservation;
  - `LendForm`: reader, book and days.
- [ ] T121 [US3] In `library/order/views.py` and `library/order/urls.py`, add:
  - the desk list `/order/reservations/desk/`, for librarians: active reservations by deadline, with
    the reader, the book and the time left;
  - issue `/order/reservations/<id>/issue/`, for librarians: the form on GET, the issue on POST;
  - cancel `/order/reservations/<id>/cancel/`, for the owner or a librarian: a confirmation on GET,
    the cancellation on POST;
  - dismiss `/order/reservations/<id>/notice/dismiss/`, a POST for the owner;
  - lend `/order/lend/`, for librarians, where `?book=` preselects the book.

  Make `/order/create/<book_id>/` redirect readers to the book page, and librarians to
  `/order/lend/?book=<id>`.
- [ ] T122 [US3] Add the desk pages:
  - create `library/order/templates/order/reservation_desk.html`, `reservation_issue.html`,
    `reservation_cancel.html` and `order_lend.html`;
  - in `library/library/templates/base.html`, add navigation to My reservations, and to the desk for
    librarians;
  - in `library/book/templates/book/book_detail.html`, remove the reader's self-loan link and offer
    librarians "Lend directly".
- [ ] T123 [US3] Create `library/order/middleware.py` with `ReservationNoticeMiddleware`, after
  `MessageMiddleware` in settings.
  - It sets a lazy `request.reservation_notices` for signed-in readers: their reservations with state
    `cancelled`, a `cancelled_by` other than themselves, and no `cancellation_seen_at`.
  - In `base.html`, show the notices in a `role="status"` region, each with the book, the time, the
    reason and a Dismiss form (POST with CSRF).
- [ ] T124 [US3] In `library/order/api_views.py` and `library/order/serializers.py`:
  - add two `ReservationViewSet` actions, documented with `extend_schema` (400, 409):
    - `cancel`: POST, for a signed-in owner or a librarian, with the reason rules; answers 200;
    - `issue`: POST, `IsLibrarian`, with `days` from 1 to 30 (default 14); answers 201 with the
      reservation and the loan, or a 409 code.
  - make loan creation in `OrderViewSet` and `UserOrderViewSet` librarian-only, and route it through
    `services.lend()`;
  - update the API concurrency test in `library/order/tests.py` to sign in as a librarian.
- [ ] T125 [US3] In `library/events/signals.py`, record `ORDER_CREATED` for the loan's reader (`user=`
  the reader), and add `issued_by`, the signed-in librarian's id, to its properties when the two
  differ.
- [ ] T126 [P] [US3] Document the librarian's side in `docs/features/reservations.md`: the desk,
  issuing, lending directly, cancelling with a reason, the overdue block and corrections. Update the
  README's "Features" for issuing by librarians.
- [ ] T127 [US3] Verify and prepare the pull request:
  - run quickstart.md §6, lint, format and the diff coverage;
  - add the changelog entry;
  - use the title `feat(order): issue and cancel reservations at the desk (KAN-57)`.

  Commit and open it when the user asks.

**Checkpoint**: Stories 2 and 3 work end to end, and every loan now starts with a librarian.

---

## Phase 12: User Story 3, part 2: the complete reservation pages. PR 7, KAN-58 (Priority: P3)

**Goal**:
- Finished pages and messages.
- End-to-end journeys.
- The concurrency burst in CI, and the load results from the Pi.

**Independent Test**:
- Follow the whole journey from both sides of the desk.
- The CI burst holds exactly one copy in each of its 20 runs.

### Tests for User Story 3 (PR 7)

- [ ] T128 [US3] Create branch `feat/kan-58-reservation-pages`, either from a freshly fetched
  `origin/main` with PR 6 merged, or from PR 6's verified branch. (Jira) Move KAN-58 to In Progress.
- [ ] T129 [P] [US3] Create `library/order/test_reservation_journeys.py` (FR-021), running these
  journeys through the web and the API:
  - A reader reserves. A librarian issues it from the desk, the loan appears in the reader's loans,
    the librarian records the return, and the copy is available again.
  - A reader reserves. A librarian cancels with a reason, and the reader sees and dismisses the
    notice.
  - A reservation passes its deadline. It reads expired, the copy is free, and the expiry task
    records it.

  Every form field on these pages has a label.
- [ ] T130 [P] [US3] In `library/order/test_queries.py`, add the desk list with 1 and 50 active
  reservations.

### Implementation for User Story 3 (PR 7)

- [ ] T131 [US3] Finish the pages in `library/order/templates/order/*.html` and
  `library/book/templates/book/book_detail.html` (FR-019, FR-020):
  - the time left, such as "1 day 3 hours left";
  - every deadline with its zone;
  - the next step for each state;
  - a confirmation step before cancelling;
  - the services' plain messages, shown on every reservation page;
  - empty states.
- [ ] T132 [US3] Create `scripts/smoke_reservation_load.py` (R17):
  - **Options**: `--compose-file` or `--project-name`, `--base-url`, `--burst`, `--runs` and
    `--readers`.
  - **Setup**: through `docker exec <web> python manage.py shell -c`, it creates:
    - temporary readers `load-check-<uuid>@example.invalid`, with sessions and CSRF tokens;
    - a temporary librarian;
    - books `load-check-<uuid>`.
  - **Burst mode**: it sends `--burst` simultaneous `POST /api/v1/reservation/` requests for a book
    with 1 copy, and requires exactly 1 success in each of `--runs` runs.
  - **Load mode**: `--readers` readers reserve at once, then the reservations are issued and
    cancelled. It reports each operation's p95 against 3000 ms.
  - **Output and cleanup**: it prints a JSON summary ending in `"result": "PASS"` or `"FAIL: …"`. It
    deletes its accounts, whose reservations and loans go with them, and then its books.
- [ ] T133 [US3] In `.github/workflows/docker-build.yml`, on the `ubuntu-latest` leg, run `python
  scripts/smoke_reservation_load.py --compose-file docker-compose-dev.yml --burst 100 --runs 20`
  after the stack starts (SC-002).
- [ ] T134 [P] [US3] Finish the docs:
  - complete `docs/features/reservations.md`: both sides of the desk, the API summary and the refusal
    codes;
  - add "Check reservations under load", with the Pi command, to
    `docs/deployment/raspberry-pi-portainer.md`;
  - update the README.
- [ ] T135 [US3] Constitution PATCH amendment (R29), in `.specify/memory/constitution.md`. With the
  handoff set to `blocked`, use `/speckit-constitution` to add the reservation burst to the
  smoke-test in workflow item 4. Add its entry to `docs/shared/changelog.md`, then set the handoff
  back.
- [ ] T136 [US3] Verify and prepare the pull request:
  - run quickstart.md §7 steps 1 and 2, lint, format and the diff coverage;
  - add the changelog entry;
  - use the title `feat(order): complete the reservation pages and messages (KAN-58)`.

  Commit and open it when the user asks.
- [ ] T137 [US3] (Pi) After deployment, at a quiet time, run `scripts/smoke_reservation_load.py
  --burst 100 --readers 30` (quickstart.md §7 step 3), and record its JSON in research.md
  "Measurements" (SC-002, SC-003).

**Checkpoint**: Story 3 is done.

---

## Phase 13: User Story 1, part 2: the administrator role. PR 11, KAN-70 (Priority: P1)

**Goal**:
- Only administrators grant or remove the librarian role, and they hold every librarian right.
- The operator creates the first administrator on the server.
- Every role change is audited (FR-063).

**Independent Test**: as a librarian, try to grant or remove the librarian role through the web, the
API and the admin site; every attempt is refused. As an administrator, do the same; each change
takes effect and leaves an audit entry (spec Story 1 scenario 8).

### Tests for User Story 1 (PR 11)

- [ ] T138 [US1] Create branch `feat/kan-70-administrator-role` from a freshly fetched `origin/main`,
  with PRs 1 and 8 merged. (Jira) Move KAN-70 to In Progress.
- [ ] T139 [P] [US1] In `library/authentication/test_access.py`, add Story 1 scenario 8:
  - a librarian trying to grant or remove the librarian role is refused through the web (403), the
    API (403) and the admin site, where the field is read-only and a crafted POST changes nothing;
  - an administrator's change takes effect, keeps the account, and leaves an audit entry;
  - administrators keep every librarian right, such as creating books and using the desk;
  - the role choices offered are reader and librarian.
- [ ] T140 [P] [US1] In `library/authentication/tests.py`, test that:
  - `createsuperuser` creates an administrator;
  - `set_administrator <email>` grants the role, and `--remove` makes the account a librarian;
  - each keeps the account and records an audit entry with channel `command`.

### Implementation for User Story 1 (PR 11)

- [ ] T141 [US1] In `library/authentication/models.py` (data-model.md §4):
  - add `ROLE_ADMINISTRATOR = 2`, and set `ROLE_CHOICES` to `(0, "reader")`, `(1, "librarian")`,
    `(2, "administrator")`;
  - make `is_librarian` true for librarians and administrators, and add `is_administrator`;
  - make `create_superuser` set `role=ROLE_ADMINISTRATOR`.

  Run `python manage.py makemigrations authentication` to create
  `library/authentication/migrations/0005_alter_customuser_role.py`, which changes Django's state
  only.
- [ ] T142 [US1] In `library/authentication/services.py`, make `may_change_role` true only for
  administrators, and limit the roles that the web, the API and the admin site can assign to reader
  and librarian. In `library/authentication/permissions.py`, add `IsAdministrator`, with audience
  `administrator`.
- [ ] T143 [US1] Apply the rule in:
  - `library/authentication/forms.py`, where `UserUpdateForm` shows `role` only to administrators;
  - `library/authentication/views.py`;
  - `library/authentication/serializers.py`, where `role` is writable only by administrators, and
    anyone else gets 403;
  - `library/authentication/admin.py`, where `role` is read-only unless the user is an administrator,
    its choices are limited to reader and librarian, and saving goes through `update_account`.
- [ ] T144 [US1] Create `library/authentication/management/__init__.py`,
  `library/authentication/management/commands/__init__.py` and
  `library/authentication/management/commands/set_administrator.py`. The command is
  `set_administrator <email> [--remove]`: `--remove` sets the role to librarian, the command prints
  the result, and it is audited with channel `command`.
- [ ] T145 [P] [US1] Update the role labels in `library/authentication/templates/authentication/*.html`
  and any other template that says "visitor" (`grep -rn "visitor" library/*/templates`).
- [ ] T146 [P] [US1] In `docs/deployment/raspberry-pi-portainer.md`, replace "Create the first
  librarian account" with "Create the first administrator": `createsuperuser` for a new account, and
  `set_administrator` for an existing one. Describe the roles in the README, and replace "visitor"
  in the docs.
- [ ] T147 [US1] Constitution MINOR amendment (R29), in `.specify/memory/constitution.md`. With the
  handoff set to `blocked`, use `/speckit-constitution` to add the administrator audience
  (`ROLE_ADMINISTRATOR`) to Principle II as the only role that grants or removes the librarian role.
  Add its entry to `docs/shared/changelog.md`, then set the handoff back.
- [ ] T148 [US1] Verify and prepare the pull request:
  - run quickstart.md §11, lint, format and the diff coverage;
  - add the changelog entry;
  - use the title `feat(authentication): add the administrator role (KAN-70)`.

  Commit and open it when the user asks.
- [ ] T149 [US1] (Pi) After deployment, create or promote the designated administrator on the server.
  Record who and when in the pull request and in `specs/003-priority-tech-debt/research.md`
  "Measurements".

**Checkpoint**: Story 1 is complete, including the LR2 roles requirement.

---

## Phase 14: User Story 6: people with any level of digital experience can use the main pages. PR 10, KAN-69 (Priority: P6)

**Goal**:
- The main pages meet WCAG 2.2 AA, and automated checks in CI keep them there.
- Plain language, confirmations, and every time shown with its zone.
- Keyboard, screen-reader and walkthrough results are recorded.

**Independent Test**:
- Run the automated checks on every main page.
- Complete each main task with the keyboard alone and with a screen reader.
- Run a short walkthrough with people who are new to the system.

### Tests for User Story 6 (PR 10)

- [ ] T150 [US6] Create branch `fix/kan-69-accessibility` from a freshly fetched `origin/main`, with
  PR 7 merged. (Jira) Move KAN-69 to In Progress.
- [ ] T151 [P] [US6] Create `scripts/a11y/package.json`: private, `"type": "module"`, with the exact
  devDependencies `playwright` `1.64.0` and `@axe-core/playwright` `4.13.0`. Run `npm install --prefix
  scripts/a11y` to produce `scripts/a11y/package-lock.json`, and ignore `scripts/a11y/node_modules/`
  in `.gitignore`.
- [ ] T152 [US6] Create `scripts/a11y/check_pages.mjs`:
  - **Options**: `--base-url`.
  - **Sign-in**: as the seeded reader and the seeded librarian. `A11Y_READER_EMAIL`,
    `A11Y_READER_PASSWORD`, `A11Y_LIBRARIAN_EMAIL` and `A11Y_LIBRARIAN_PASSWORD` override them.
  - **Pages**: every main page of FR-041.
    - For readers: sign-in, registration, the catalog with a search and an author filter, a book
      page, my loans, my reservations and my profile.
    - For librarians: the desk, all loans with editing and return, the user list and user editing,
      creating and editing books and authors, and the analytics dashboard.
  - **Check**: `AxeBuilder`, with the tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` and
    `wcag22aa`.
  - **Output**: each violation with its rule, impact, page and target. It exits 1 if there is any.
- [ ] T153 [P] [US6] Create `library/authentication/test_templates.py` (FR-044). It scans every
  template under `library/` and fails on a `|date:` format that shows a time (`H`, `G`, `i`, `A`,
  `a` or `P`) without a zone (`T`, `e` or `O`).
- [ ] T154 [US6] Run `check_pages.mjs` against the development stack with demo data, and list the
  current violations in the pull request description as the baseline.

### Implementation for User Story 6 (PR 10)

- [ ] T155 [US6] Fix the shared layout in `library/library/templates/base.html`:
  - a skip link to `<main id="main">`;
  - visible focus on links and buttons, with `focus-visible` rings on `.nav-link`, `.btn-*` and
    `.mobile-nav-link`;
  - one message region with `role="status"`, replacing the message loops in
    `author/author_list.html`, `book/book_detail.html`, `book/book_list.html`, `order/order_all.html`
    and `order/order_my.html`;
  - a footer note: "Times are shown in Kyiv time (EET/EEST).".
- [ ] T156 [US6] In `library/library/templates/includes/form_snippet.html` and
  `library/library/forms_mixins.py` (FR-043):
  - give every field a label;
  - tie its help text and errors to it with `aria-describedby`;
  - mark invalid fields with `aria-invalid="true"`;
  - make each error say what is wrong and how to fix it;
  - mark required fields;
  - keep the values typed.
- [ ] T157 [US6] Fix the pages under `library/*/templates/`:
  - contrast of at least 4.5:1 for light grey text;
  - names for every link and button;
  - table headers;
  - plain-language labels and messages;
  - a confirmation step before each action that cannot be undone: deleting authors, books and loans,
    closing loans, and cancelling reservations;
  - a text or table equivalent for the bars in
    `library/events/templates/events/_analytics_content.html`.

  Show every date and time in the format with the zone, so that T153 passes.
- [ ] T158 [US6] Re-run `check_pages.mjs` until it reports 0 violations (SC-009).
- [ ] T159 [US6] In `.github/workflows/docker-build.yml`, on the `ubuntu-latest` leg after the stack is
  healthy, run (FR-042):
  1. `npm ci --prefix scripts/a11y`;
  2. `npx --prefix scripts/a11y playwright install --with-deps chromium`;
  3. `node scripts/a11y/check_pages.mjs --base-url http://localhost:8000`.
- [ ] T160 [P] [US6] Add `/scripts/a11y/ @Dima22820 @Arezzon` to `.github/CODEOWNERS`, and document the
  accessibility check in the README's "Tests and checks".
- [ ] T161 [US6] Constitution PATCH amendment (R29), in `.specify/memory/constitution.md`. With the
  handoff set to `blocked`, use `/speckit-constitution` to add the accessibility check to the
  smoke-test in workflow item 4. Add its entry to `docs/shared/changelog.md`, then set the handoff
  back.
- [ ] T162 [US6] (manual) Complete each main task of Story 6 with the keyboard alone, and with NVDA in
  Firefox or Chrome. Fix what fails, and record the results in research.md "Measurements" (SC-009).
- [ ] T163 [US6] (manual) Run the walkthrough (FR-045):
  - at least 3 people who are new to the system, at least 1 of them with little digital experience;
  - each attempts every main task without help;
  - record the anonymous results in `specs/003-priority-tech-debt/research.md` "Measurements": the
    task, whether it finished without help, and the problems seen;
  - fix each problem, or note it for the register with an owner and a plan.

  At least 80% of the attempts must finish without help.
- [ ] T164 [US6] Verify and prepare the pull request:
  - run quickstart.md §10, lint, format and the diff coverage;
  - add the changelog entry;
  - use the title `fix(ui): make the main pages meet WCAG 2.2 AA (KAN-69)`.

  Commit and open it when the user asks.

**Checkpoint**: Story 6 is done.

---

## Phase 15: User Story 9: the team sees what debt remains, who owns it, and the proof. PR 12, KAN-71 (Priority: P9)

**Goal**:
- The debt register, with evidence or a plan for every item.
- The README and ADRs, matching the product.
- KAN-62 closed, with no P1 item open.

**Independent Test**: pick any item KAN-62 names, follow its link to the evidence, and confirm that no
P1 item is open.

### Implementation for User Story 9 (PR 12)

- [ ] T165 [US9] Create branch `docs/kan-71-debt-register` from a freshly fetched `origin/main`, with
  PRs 1 to 11 merged. (Jira) Move KAN-71 to In Progress.
- [ ] T166 [US9] Create `docs/shared/debt-register.md`, following contracts/debt-register.md (FR-054,
  FR-055):
  - the columns and the status rules;
  - rows TD-01 to TD-27, with their evidence: pull request links, CI runs, tests, anchors in
    research.md "Measurements", the ruleset JSON, the librarian account review, and the restore
    record;
  - owners named as people. Start from the risk register's roles: the senior engineer for R2, the QA
    lead for R3, and the product owner with the tech lead for R7. Ask the user for the others.
  - plans with target sprints for open items;
  - rows for unfixed walkthrough problems, and for defects filed under FR-053.
- [ ] T167 [US9] Check the register in `docs/shared/debt-register.md` (FR-056, SC-013):
  - every item that KAN-62 names has a row;
  - every closed row's evidence link works;
  - every open row has an owner, a priority, a plan and a target sprint;
  - no P1 row is open or blocked.
- [ ] T168 [P] [US9] Review `README.md` and `docs/adr/README.md`. They must describe reservations,
  issuing by librarians, the roles, backups and logs as delivered, and list ADRs 0001 to 0003 (Story
  9 scenario 6).
- [ ] T169 [P] [US9] In `specs/003-priority-tech-debt/`, set the spec's Status to Implemented, complete
  research.md "Measurements", and mark every task done in tasks.md. Mark the handoff complete with
  the bridge, and commit its records in `.specify/` with these files.
- [ ] T170 [US9] Verify and prepare the pull request:
  - run quickstart.md §13 and lint;
  - add the changelog entry;
  - use the title `docs(shared): add the debt register and close KAN-62 (KAN-71)`.

  Commit and open it when the user asks.
- [ ] T171 [US9] (Jira) With the assignee (FR-056, FR-058):
  - correct KAN-19's description: issuing locks the book and rechecks the derived availability, and
    no stored counter decreases;
  - confirm KAN-18's description;
  - link the register (`docs/shared/debt-register.md` on `main`) and the evidence from KAN-62;
  - make every sub-task's status match its pull request;
  - move KAN-62 to Done only when no P1 item is open or blocked.

**Checkpoint**: every story is done, and KAN-62 can close.

---

## Phase 16: Polish & Cross-Cutting Concerns

**Purpose**: checks across the whole feature after the last pull request merges.

- [ ] T172 (Pi) With everything running, run `smoke_stack_budget.py` with the memory, search and
  catalog limits. Record that the stack stays within 4 GB and that search p95 stays under 500 ms
  (SC-014).
- [ ] T173 Review the combined changes for security with the code-review or security-review skill:
  the access rules, redaction, backup file permissions, and how the scripts handle passwords. Fix
  what it finds, or record it in `docs/shared/debt-register.md`.
- [ ] T174 Run every automated check in quickstart.md once more on the final `main`. Confirm that each
  pull request met FR-062: the template, a changelog entry, the code owners' review and CI. Note any
  gap in the register.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)** has no dependency. **Phase 2** holds no tasks.
- **PR 1 (Phase 3)** depends on Setup and blocks everything else. It must be the first of this feature
  to merge, and nothing describing the gap is published before it deploys (FR-060).
- **After PR 1 merges**, these can proceed in parallel:
  - PR 2 (Phase 4), which opens after PR 1 deploys, because it carries the spec folder;
  - PR 3 (Phase 5);
  - PR 9 (Phase 7);
  - PR 8 (Phase 8).
- **The settings (Phase 6)** can be applied at any time.
- **The reservation stages run in sequence**: PR 4 (Phase 9), then PR 5 (Phase 10), then PR 6 (Phase
  11), then PR 7 (Phase 12). Each later stage may branch from the previous stage's verified branch
  before it merges.
- **PR 11 (Phase 13)** needs PR 1. The recommended order also waits for PR 8, so that role changes are
  audited.
- **PR 10 (Phase 14)** needs PR 7, because it audits the finished reservation pages.
- **PR 12 (Phase 15)** needs all the others, and **Polish (Phase 16)** follows it.

### Minimum dependencies (spec FR-059) and the recommended order (R1)

| PR | Phase | Story | Needs | Recommended slot |
|---|---|---|---|---|
| 1 | 3 | US1 | — | 1st |
| 2 | 4 | US7 | PR 1 deployed (FR-060) | 2nd wave |
| 3 | 5 | US8 | PR 1 | 2nd wave |
| 9 | 7 | US4 | — (merges after PR 1) | 2nd wave |
| 8 | 8 | US5 | PR 1 | 3rd |
| 4 | 9 | US2 | PR 1 | 4th |
| 5 | 10 | US2 | PR 4 | 5th |
| 6 | 11 | US3 | PR 5 | 6th |
| 7 | 12 | US3 | PR 6 | 7th |
| 11 | 13 | US1 | PR 1 (and PR 8 recommended) | 8th |
| 10 | 14 | US6 | PR 7 | 9th |
| 12 | 15 | US9 | all | last |
| settings | 6 | US8 | — | any time |

If the reservation stages merge before PR 8, PR 8 must also add audit entries to the reservation
transitions in `library/order/services.py` (FR-059).

### Within Each Pull Request Phase

1. The branch task comes first.
2. Tests are written next, and must fail before the implementation.
3. Then the models and migrations, then the services, then the views, the API and the templates.
4. Then CI and the docs, and any constitution amendment.
5. Verification and the pull request come last.
6. The tasks marked (Pi) follow the deployment.

---

## Parallel Examples

### PR 1 (User Story 1)

```text
# After T004–T006 (same file, in order), in parallel:
Task: "T007 Web tests for sign-up, profile and refusals in library/authentication/tests.py"
Task: "T016 403 page in library/library/templates/403.html and messages on login.html"
# After T008 (permissions.py), in parallel:
Task: "T019 permission_classes in library/book/api_views.py"
Task: "T020 permission_classes in library/author/api_views.py"
Task: "T025 README audience column and the operator guide's account review"
```

### PR 2 (User Story 7)

```text
# After T030 (library/library/testing.py), in parallel:
Task: "T031 library/book/test_queries.py"
Task: "T032 library/author/test_queries.py"
Task: "T033 library/authentication/test_queries.py"
Task: "T034 library/order/test_queries.py"
Task: "T035 library/events/test_queries.py"
```

### PR 8 (User Story 5)

```text
# Tests, in parallel:
Task: "T069 library/authentication/test_logging.py"
Task: "T070 library/audit/tests.py"
Task: "T071 queryset guard tests in library/book/tests.py and library/order/tests.py"
# After T072–T074 (logs.py, middleware, celery.py), in parallel:
Task: "T075 library/gunicorn.conf.py"
Task: "T076 entrypoint.sh log function"
Task: "T077 library/authentication/signals.py"
```

### PR 5 (User Story 2)

```text
# Tests, in parallel with T101 (T102 shares its file and follows it):
Task: "T103 availability tests in library/book/tests.py"
Task: "T104 reservation list query counts in library/order/test_queries.py"
# Late in the phase, in parallel:
Task: "T112 book edit warning and admin availability"
Task: "T113 docs/features/reservations.md and README"
```

### Across the team

After PR 1 merges, four branches can be worked on at the same time, each by the assignee of its issue:
- PR 2, `perf/kan-18-query-counts`;
- PR 3, `test/kan-21-business-rules`;
- PR 9, `feat/kan-68-backups`;
- PR 8, `feat/kan-67-logs-and-audit`.

The reservation stages, from PR 4 onwards, follow one after another.

---

## Implementation Strategy

### MVP first: User Story 1, part 1 (PR 1)

1. Complete Phase 1. Phase 2 has no tasks.
2. Complete Phase 3, PR 1. It closes the live access-control gap.
3. **Stop and validate**: run quickstart.md §1, deploy, and review the librarian accounts (T027).
4. Publish the planning documents (T029).

### Incremental delivery

1. **Second wave**: PR 2, PR 3 and PR 9. Each is independent, testable on its own, and deployed when
   it merges.
2. **PR 8**: the audit trail and the logs, in place before any reservation changes state.
3. **PRs 4, 5, 6 and 7**: the reservations. The site stays usable after each merge (FR-061).
4. **PR 11, then PR 10**, which audits the finished pages.
5. **PR 12**: the register, and the closing of KAN-62.

Each pull request adds value without breaking the earlier ones. Its CI run and its quickstart.md
section are the gate.

### Parallel team strategy

- One person carries PR 1 to merge quickly, while others prepare PR 9, which has no code dependency.
- After PR 1 merges, the people assigned to KAN-18, KAN-21, KAN-68 and KAN-67 work in parallel.
- Arsen applies KAN-72 to KAN-74 at any point.
- The reservation stages, KAN-55 to KAN-58, then run in sequence.

---

## Notes

- Within a phase, [P] tasks touch different files, and none of them waits for another [P] task of the
  same phase.
- The `[US#]` labels map each task to spec.md's user stories for traceability.
- Verify that each test fails before implementing (Principle III).
- Commit after each task or logical group, but only when the user asks, and only with the phase's own
  files.
- Stop at any checkpoint to validate a story on its own.
- Version pins (coverage, diff-cover, Playwright, axe) were chosen on 2026-10-27. Re-check them when
  their pull request opens, choosing the newest release that is at least two weeks old, and record
  any change in research.md.
- KAN-72, KAN-73 and KAN-74 sit in the closed "Lab 3" sprint, inherited from their parents. Whether to
  move them is for the user or Arsen to decide.
