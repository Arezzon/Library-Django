# Research: Close the Priority Technical Debt of v1.0

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Date**: 2026-10-27

Pull requests (PRs) are numbered as in FR-059. Tool versions were checked on 2026-10-27, choosing
the newest release that is at least two weeks old. Re-check them when their pull request opens,
and record any change here.

## R1. Delivery: branches, merge order and disclosure

**Decision**:

- Each PR gets its own branch, created with the fresh-feature-branch skill. The base is a freshly
  fetched `origin/main`. When a PR depends on an unmerged stage, the base is that stage's branch,
  verified current first (FR-062).

  | PR | Jira | Branch | Title |
  |---|---|---|---|
  | 1 | KAN-24, KAN-62 | `fix/kan-24-access-control` | `fix(authentication): require the right role for every account and API operation (KAN-24, KAN-62)` |
  | 2 | KAN-18 | `perf/kan-18-query-counts` | `perf(author): load every list in a fixed number of queries (KAN-18)` |
  | 3 | KAN-21 | `test/kan-21-business-rules` | `test(order): cover the book, author and loan rules and report coverage (KAN-21)` |
  | 4 | KAN-55 | `feat/kan-55-reservation-model` | `feat(order): add the reservation model and its states (KAN-55)` |
  | 5 | KAN-56 | `feat/kan-56-reserve-a-book` | `feat(order): let readers reserve an available book for 48 hours (KAN-56)` |
  | 6 | KAN-57 | `feat/kan-57-issue-at-the-desk` | `feat(order): issue and cancel reservations at the desk (KAN-57)` |
  | 7 | KAN-58 | `feat/kan-58-reservation-pages` | `feat(order): complete the reservation pages and messages (KAN-58)` |
  | 8 | KAN-67 | `feat/kan-67-logs-and-audit` | `feat(audit): add technical logs and an audit trail of critical changes (KAN-67)` |
  | 9 | KAN-68 | `feat/kan-68-backups` | `feat(deploy): back up the database daily and rehearse a restore (KAN-68)` |
  | 10 | KAN-69 | `fix/kan-69-accessibility` | `fix(ui): make the main pages meet WCAG 2.2 AA (KAN-69)` |
  | 11 | KAN-70 | `feat/kan-70-administrator-role` | `feat(authentication): add the administrator role (KAN-70)` |
  | 12 | KAN-71 | `docs/kan-71-debt-register` | `docs(shared): add the debt register and close KAN-62 (KAN-71)` |

- **Recommended merge order**:
  1. PR 1.
  2. PRs 2, 3 and 9, in any order.
  3. PR 8.
  4. PRs 4, 5, 6 and 7, in that order.
  5. PR 11.
  6. PR 10.
  7. PR 12.

  FR-059 sets only the minimum dependencies; this order adds three choices:
  - PR 8 lands before the reservation stages, so each stage writes its own audit entries from its
    first commit. Otherwise PR 8 would have to retrofit them.
  - PR 3 lands early, so every later PR gets a coverage report.
  - PR 11 lands after PR 8, so role changes are audited from the day the administrator role ships.
- **Disclosure** (FR-060):
  - PR 1 opens first and merges as soon as review allows. It then deploys through the normal
    pipeline.
  - Until `/api/v1/version/` on the server reports PR 1's merge commit, two things stay off GitHub:
    - `specs/003-priority-tech-debt/` stays untracked;
    - no branch, commit or description mentions the gap.
  - Other branches may be pushed, and their PRs opened, before then. They merge only after PR 1.
  - PR 1's description says what the change enforces, not how the old behavior could be used.
  - The spec folder is committed as its own commit in the first PR that opens after the deployment.
    In the recommended order that is PR 2. Feature 002 also shipped its spec folder with its first
    PR.
- **Jira**:
  - Each title names its Jira key.
  - The assignee moves each issue to In Progress when its PR opens and to Done when it merges
    (FR-058).
  - Arsen applies KAN-72 to KAN-74 when ready (R27). They block no PR.
- **Handoff**: a constitution amendment (R29) needs the Superpowers handoff set to `blocked` while
  `constitution.md` changes. It goes back to `executing` afterwards (constitution, Governance).

**Rationale**:
- The access-control gap is live on a public repository with a reachable server, so it is closed
  first and quietly.
- The rest of the order minimizes rework.

**Alternatives considered**:
- One branch for the whole feature, which FR-062 forbids.
- The reservation stages before PR 8. FR-059 allows it, but PR 8 would then have to add audit
  entries to four stages' transitions after they merge.

## R2. A fail-closed API: every operation declares its audience (PR 1)

**Decision**:

- `REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]` becomes `["authentication.permissions.DenyAll"]`.
  A view that declares nothing refuses every caller, librarians included (FR-003).
- Every API view sets `permission_classes` from the new `authentication/permissions.py`:

  | Class | Audience | Used for |
  |---|---|---|
  | `AllowAny` (DRF) | anonymous | version check, API index, schema and docs |
  | `IsSignedIn` | any signed-in account | search, activity events, own account, own loans |
  | `ReadOnlyOrLibrarian` | signed-in accounts read, librarians change | books, authors |
  | `IsSelfOrLibrarian` | the account itself, or a librarian | one account; one account's loans |
  | `IsLibrarian` | librarians | the user list, creating and deleting accounts, all loans, changing loans |

- Readers' querysets hold only their own records. A reader asking for another reader's record gets
  404, as for a missing one (FR-004).
- `DEFAULT_AUTHENTICATION_CLASSES` becomes `["authentication.permissions.SessionAuthentication"]`.
  This is DRF's session class with `authenticate_header()` returning `Session`, which has two
  effects:
  - DRF answers 401 to a caller who is not signed in, and 403 to a signed-in caller without the
    role (R4).
  - DRF's other default, Basic authentication, is dropped. It accepts a password on every request
    and no client uses it.
- The router's index (`/api/v1/`) uses a subclass of DRF's `APIRootView` with `AllowAny`, because
  FR-003 lists the index as anonymous.
- A test walks every URL pattern under `/api/v1/` and fails if a view inherits its permissions from
  the default. Principle II: "Relying on a framework default is not a declaration".
- A second test calls every operation as an anonymous caller, a reader and a librarian. The expected
  results come from [contracts/access-control.md](contracts/access-control.md) (SC-001).

**Rationale**:
- DRF lets anonymous callers use any endpoint that declares nothing, so the gap returns whenever a
  declaration is forgotten.
- A default that refuses everyone turns that mistake into a failing test.

**Alternatives considered**:
- `IsAuthenticated` as the default. Any reader could still change data through a forgotten
  endpoint.
- `IsAdminUser`. Librarians are staff, so undeclared operations would quietly work for them, and the
  test would not notice.
- DRF's 403 for every refusal, with only the message differing. Clients could not tell the two
  cases apart without parsing text.

## R3. One rule for roles and account status (PR 1)

**Decision**:

- `authentication/services.py` (new) holds the rule (FR-002):
  - `may_change_role(actor, account)` and `may_change_status(actor, account)`: true for librarians
    in PR 1. PR 11 moves the role right to administrators (R26).
  - `update_account(actor, account, changes)`: applies a change, or refuses all of it with
    `PermissionDenied` when it touches a field the actor may not change. A hand-crafted request that
    sends a role together with a new name changes nothing (Story 1 scenario 2).
- **Web**:
  - The sign-up form drops `role`, and `save()` always creates a reader, so a posted `role` or
    `is_active` is ignored (FR-001).
  - The profile page uses `ProfileForm` (name fields) for readers and `UserUpdateForm` (names, role,
    status) for librarians.
  - A reader's POST that contains `role` or `is_active` gets the 403 page.
- **API**: `CustomUserSerializer` makes `role`, `is_active` and `email` read-only, and leaves
  `password` out, unless the requester may change them. A forbidden field in the body gets 403
  before validation.
- **Admin site**: no change in PR 1, because only librarians reach it today. PR 11 makes `role`
  read-only there for librarians.
- **One predicate**: the decorators and every `role == ROLE_LIBRARIAN` comparison use the model's
  `is_librarian` property, so PR 11 changes one predicate. The templates and the events app already
  use it.
- **Existing tests**:
  - The tests that call the API without signing in now sign in with the role the new rules require:
    `book/tests.py` and `order/tests.py`, including the parallel API issuance test.
  - Tests that expect a redirect home for a refused reader now expect 403.

**Rationale**: Principle I requires one implementation of a domain rule for the web, the API and the
admin site, so the forms and the serializer cannot drift.

**Alternatives considered**:
- Hide the fields in the templates only. A crafted POST would still work.
- Separate checks in each form and serializer: two implementations of one rule.

## R4. Refusals that people and programs can tell apart (PR 1)

**Decision**:

| Caller | Web page | API |
|---|---|---|
| Not signed in | Redirect to the sign-in page with `next`, which shows "Sign in to continue." | 401, `{"detail": "Authentication credentials were not provided."}`, header `WWW-Authenticate: Session` |
| Signed in, not allowed | 403 page: "You don't have permission to do this." with a link home | 403, `{"detail": "You do not have permission to perform this action."}` |
| A record the caller may not read | The same 403, because the decorators run before the record is looked up | 404, the same as for a record that does not exist |

- The decorators raise `PermissionDenied`, which renders the new `library/library/templates/403.html`.
  They no longer redirect home without a word.
- The sign-in page shows messages.
- `/authentication/` renders a template that does not exist, so anyone who opens it gets a server
  error. It now redirects: anonymous callers go to sign-in and signed-in ones go home. It turned up
  while listing the routes, and PR 1 gives every route an audience.

**Rationale**: FR-004 and Story 1 scenario 6. Checking the role before the lookup keeps the response
the same whether or not the record exists.

**Alternatives considered**: answering refused web requests with 404 everywhere. That hides
existence too, but tells a signed-in reader nothing about what to do.

## R5. The schema states every audience and refusal (PR 1)

**Decision**:
- `library/library/schema.py` (new) subclasses drf-spectacular's `AutoSchema` and becomes
  `DEFAULT_SCHEMA_CLASS`.
- Each permission class carries an `audience` label. For every operation, the schema class reads the
  labels of the view's permission classes and:
  - appends "Audience: …" to the description;
  - adds an `x-audience` extension;
  - adds the 401 and 403 responses, and 404 where readers see only their own records, all with
    DRF's error body.
- A test generates the schema and fails if any operation lacks `x-audience` (FR-005).
- Later operations appear the same way: reservations in PRs 5 and 6, the administrator audience in
  PR 11.

**Alternatives considered**:
- `extend_schema` on every view: dozens of repeated decorators that drift from `permission_classes`.
- A postprocessing hook. It sees the generated schema but not the views.

## R6. Clients that call the API without signing in today (PR 1)

**Decision**:
- **CI**: the "Verify key endpoints respond" step:
  - checks that anonymous search now returns 401;
  - signs in as the seeded demo reader with a cookie jar and checks that search returns 200. The
    demo reader, `reader@library.com`, has a documented public password.
  - `/api/docs/`, `/api/schema/`, `/api/v1/version/` and `/api/v1/` stay anonymous.
- **`scripts/smoke_stack_budget.py`** signs in through the sign-in form before searching:
  - `--email` names the account;
  - the password comes from the `BUDGET_CHECK_PASSWORD` environment variable, or a prompt. It never
    comes from the command line, where it would reach the shell history and the process list.
  - CI passes the demo reader.
- **Other smoke tests**: `smoke_test_tracking` already signs in, and `smoke_tracking_recovery.py`
  calls no API.
- No rule is weakened for any of them (FR-006).

## R7. Librarian accounts made through the open sign-up (PR 1, operator)

**Decision**:
- Right after PR 1 deploys, the operator opens the admin site's user list filtered to librarians:
  `/admin/authentication/customuser/?role__exact=1`.
- Every account that is not an authorized librarian loses the role or is deactivated.
- The operator records the date, the number of accounts reviewed and each change (FR-007). The
  record goes in PR 1's deployment comment, and PR 12 moves it into the register.
- `created_at` cannot date an account (R9 finding 1), so the review relies on the email and
  `last_login`.

**Alternatives considered**: a command that demotes every librarian outside a list. It acts in bulk,
and undoing it without a record is guesswork.

## R8. Query counts (PR 2)

**Decision**:
- **Lists in scope** (FR-046):
  - Web: the book list, with and without the author filter; the author list; the user list; all
    loans; my loans; a reader's books; the analytics dashboard's event table.
  - API: books, authors, users, loans, one user's loans, and search.
  - The reservation lists join with the PRs that add them (5 to 7).
- **Test helper**: `library/library/testing.py` (new) loads a list with 1 row and with 50 rows and
  asserts the same number of queries, using `CaptureQueriesContext`.
  - Each list gets one test, in its app's new `test_queries.py` (FR-047).
  - Search runs with the mocked encoder (Principle III).
- **The fix**: `AuthorViewSet` prefetches `books` (Story 7 scenario 2). PR 2 records the author
  list's query counts before and after.
- **Catalog timing on the Pi**: `smoke_stack_budget.py --max-catalog-p95-ms 2000` loads the
  signed-in catalog page 60 times and reports the 95th percentile (SC-010). Results go into
  [Measurements](#measurements), with the method and the date (FR-048).
- **Jira**: the assignee corrects KAN-18's description (FR-058). Availability is the total minus
  active loans, plus, from PR 5, active reservations. No order status field exists.

## R9. Tests for the existing rules, coverage and the defects they find (PR 3)

**Decision**:

- **New tests** (FR-049), each in its app:
  - `author/tests.py`, a new file. Creating, editing and deleting authors through the web, the API
    and the admin site; the 20-character limits; deletion refused while books are attached; links
    to books.
  - Books through all three channels, with their limits: name 128 characters, description 256,
    copies not negative.
  - Every change of a loan through each channel: start, return, reopen, reassign, delete.
  - `authentication/test_routes.py`. Every web route with at least one permitted and one refused
    caller. It complements PR 1's table of API operations.
- **Coverage**:
  - Tools: coverage 7.16.2 and diff-cover 10.6.0, pinned in `requirements-dev.txt`. They are the
    newest releases at least two weeks old (7.17.0 and 11.0.0 are newer).
  - Settings: `[tool.coverage.*]` in `pyproject.toml` sets the sources to the Django apps, omits
    migrations and tests, and uses relative paths.
  - CI, on the `ubuntu-latest` leg:
    - installs coverage in the web container;
    - runs the test command under it;
    - writes `library/coverage.xml` through the bind mount;
    - runs diff-cover against `origin/main` on the runner, from `library/`, so the report's
      relative paths match git's.
  - The Markdown report goes to the job summary and into one PR comment that each push updates. A
    fork's read-only token skips the comment without failing the job.
- **The 85% target** (SC-011): the report does not block a merge, because FR-051 allows exceptions listed with
  their reasons, and a hard gate cannot. Reviewers hold each PR to 85%, and the PR lists its
  uncovered lines. PRs 1 and 2 merge before the report exists, so they record coverage measured
  locally with the same command ([quickstart.md](quickstart.md)).
- **Defects found** while reading the code for this plan. PR 3's tests confirm them, and PR 3 fixes
  them because they are small (FR-053):
  1. `CustomUser.created_at` is declared with `auto_now=datetime.datetime.now()`. The value is
     truthy, so the field behaves as `auto_now=True` and changes on every save. The fix is
     `auto_now_add=True`, a state-only migration (`authentication/0004`). Past creation times
     cannot be recovered, and the register records that.
  2. `Book.count` accepts negative numbers through the form, the API and the admin site. The fix is
     `MinValueValidator(0)`, a state-only migration (`book/0005`).
- **Concurrency tests** (FR-050): the loan races already exist. PRs 5 and 6 add the reservation races
  (R13).

## R10. Reservation model (PR 4)

**Decision**:

- `Reservation` lives in the `order` app. It owns borrowing, and CODEOWNERS already calls that path
  "Borrowing and reservations". The fields are in [data-model.md](data-model.md).
- **Deadline**: `expires_at` is stored, set once to `created_at` plus 48 hours. A check constraint
  keeps it at exactly 48 hours (FR-010).
- **States**: active, issued, cancelled and expired. One model method allows only the transitions
  in FR-014. `ReservationQuerySet` refuses `update()`, `bulk_update()` and `bulk_create()` on state
  fields, as `BookQuerySet` already does for book text, so every transition goes through the
  service.
- **Uniqueness**: a partial unique constraint allows one stored-active reservation per reader and
  book. It is a backstop; the service checks first (R13).
- **Deleting books** (FR-024): `Reservation.book` and `Order.book` use `on_delete=PROTECT`.
  - Today only the web view refuses to delete a book with loans. The API and the admin site delete
    the book and its loans with it.
  - PROTECT makes the rule hold in every channel, with no SQL change, because Django applies
    `on_delete` in Python.
  - The web view catches `ProtectedError` instead of running its own check, and the API answers 409.
- **ADR 0001**, `docs/adr/0001-reservations-hold-a-unit-of-stock.md`, records:
  - the choice of a unit of stock over physical copies, and why copies were rejected;
  - how active loans and reservations reduce availability;
  - the states and the allowed transitions.
- **Migration**: `order/0004` creates the table and alters `Order.book`, and no existing row changes
  (FR-022). The quickstart compares record counts before and after migrating a seeded database.

**Alternatives considered**:
- Tracking physical copies. The product keeps only a count per book, and the LR2 feasibility review
  says so (spec Assumptions).
- Deriving the deadline instead of storing it. Queries could not index it.

## R11. Expiry: derived at once, recorded on a schedule (PR 5)

**Decision**:
- Every availability and eligibility check counts a reservation only while it is active and
  `expires_at > now`. A reservation therefore stops holding a copy at its deadline, with no job
  running (FR-013, SC-004).
- `order.tasks.expire_reservations` runs every 5 minutes:
  - it marks due active reservations as expired, locking rows with `skip_locked`;
  - each one gets an audit entry made by the system.
- Celery beat runs inside the existing worker (`--beat`, with its schedule file in `/tmp`). The stack
  has one worker, so an embedded scheduler is safe. The task uses the existing `events` queue.
- The reserve and issue services also expire the reader's and the book's due reservations under
  their locks. The uniqueness rule and the 3-reservation limit then count correctly between runs.
- Pages derive "expired" from the deadline, and no GET request writes.

**Alternatives considered**:
- A separate beat container: another Python process with Django loaded, about 70 to 100 MB, for one
  task.
- Cron on the Pi. It runs outside the stack, so Portainer cannot reproduce it.
- Expiring only when a reservation is read. A reservation nobody looks at again would never get its
  audit entry, and reads would write.

## R12. Availability counts reservations (PR 5)

**Decision**:
- `BookQuerySet.with_availability(now)` annotates `active_reservation_count` beside
  `active_order_count`. Both are `Count(…, distinct=True)` over reverse relations in the same
  query, so every list keeps its query count.
- `Book.available_count` is the total minus active loans minus active, unexpired reservations. It is
  never below 0, and it falls back to aggregates when the queryset is not annotated.
- Every reader of availability already goes through these two: the catalog, the book page, search,
  the API serializers, the admin site, and the locked recheck in `Order.save()`. Lending therefore
  respects reservations without new code in the loan path (FR-016).
- `now` is taken once per request or service call from `timezone.now()`, so tests control time.
- Lowering a book's total below its active loans and reservations is allowed. The edit form warns
  the librarian, and availability shows 0 (spec edge case).

## R13. One service for reserving, lending and issuing (PRs 5 and 6)

**Decision**:

- `order/services.py` (new) holds `reserve()`, `lend()`, `issue()`, `cancel()` and `expire_due()`.
  Each runs in `transaction.atomic`. The web views, the API and the admin site all call them.
- **Lock order**: the reservation row (issue and cancel) first, then the reader's account row, then
  the book row.
  - The account row lock makes the duplicate checks and the 3-reservation limit hold when one reader
    sends several requests at once (FR-012).
  - The book row lock serializes copies, as loans already do (FR-011).
- **Checks**, in this order. Each refusal is typed and carries a code and a message:
  1. not permitted;
  2. overdue loan, which names the book and its due date;
  3. already on loan;
  4. already reserved;
  5. 3 active reservations;
  6. no copy available;
  7. expired;
  8. already issued.
- **Overdue loans**:
  - A loan is overdue when it is unreturned and its due date (`plated_end_at`) has passed (spec edge
    case).
  - Corrections through the loan edit form, the API and the admin site keep using `Order.save()`.
    They are exempt from the overdue block, but still respect availability (spec Assumptions).
- **Lending to a reader who holds the book's reservation**: `lend()` issues that reservation
  instead of refusing, so the held copy becomes the lent copy.
  - In PR 5, a reader's self-loan also goes through `lend()`. FR-003 allows it until KAN-57. A reader
    who reserved can then still collect the book before librarians can issue it in PR 6 (FR-061).
- **Repeat requests**: issuing twice finds the reservation already issued and answers "already
  issued" (Story 3 scenario 2).
- **Messages and API codes**: each refusal becomes a web message (FR-020) and an API 409 with a
  `code` ([contracts/reservations-api.md](contracts/reservations-api.md)).
- **Race tests** (`TransactionTestCase` with a barrier, FR-050), with 20 contenders where the race
  involves many:
  - two readers on the last copy;
  - a reservation racing a loan;
  - one reader sending 5 reservations at once;
  - a double issue;
  - issuing 1 second before the deadline, which succeeds, and at the deadline, which is refused.
  The tests that involve many contenders repeat 20 times. SC-002's 100 simultaneous attempts run
  against the HTTP stack (R17), because 100 test threads would need more database connections than
  PostgreSQL's default of 100.

**Alternatives considered**:
- Advisory locks. They add a second locking scheme beside the row locks already in use.
- SERIALIZABLE isolation. Every caller would have to retry.
- A database constraint for the limit. A partial unique index can enforce "one per book", but not
  "at most 3".

## R14. Issuing moves to librarians (PR 6)

**Decision**:
- **Who issues**: only librarians call `lend()` and `issue()`, through the web, the API and the admin
  site.
  - Readers who open `/order/create/<book_id>/` go to the book page and its reserve button (spec
    edge case).
  - Creating loans through the API becomes librarian-only.
- **Existing data**: loans that readers started stay valid and can be returned. Seeded loans are
  unchanged.
- **Analytics** (FR-023):
  - `events/signals.py` records `order_created` for the reader (`user=reader`) and adds
    `issued_by` (the librarian's id) to its properties.
  - The reserve button carries `data-track-event="borrow_intent"` from PR 5, so the borrow-intent
    signal follows the reserve action.
  - Reservations never wait for the broker.
- **Desk pages**: PR 6's desk pages work (list, issue, cancel, lend directly), and PR 7 finishes them.

## R15. Cancellation reasons and the reader's notice (PR 6)

**Decision**:
- A librarian's cancellation requires a reason of 1 to 500 characters. It is stored on the
  reservation (`cancelled_by`, `cancelled_at`, `cancel_reason`) and in its audit entry.
- A reader who cancels their own reservation gives no reason and gets no notice. Only that reader
  or a librarian can cancel a reservation (FR-018).
- **The notice**: a small middleware in `order` adds the reader's unseen library cancellations to
  the page context.
  - `base.html` shows them in a status region with a Dismiss button (POST with CSRF), which sets
    `cancellation_seen_at`.
  - Showing a notice writes nothing, because Principle II puts data changes on POST.
  - My reservations always shows each cancellation's time and reason.

**Alternatives considered**:
- Marking a notice seen when it is shown. That is a write on GET.
- Email or text messages. They need an external service and are out of scope.

## R16. Local time (PRs 5 and 10)

**Decision**:
- `TIME_ZONE = "Europe/Kyiv"` from PR 5, the first PR that shows a deadline. Storage stays UTC
  (`USE_TZ = True`).
- Every date and time shown includes the zone abbreviation: `|date:"j M Y, H:i T"` gives "29 Oct
  2026, 14:05 EET".
  - PR 5 uses it for reservations.
  - PR 10 converts the other templates. It adds a test that fails on any `|date:` format that shows
    a time without a zone (FR-044).
- **Side effects**:
  - The analytics dashboard's days run from midnight to midnight Kyiv time.
  - API datetimes carry the +02:00 or +03:00 offset instead of `Z`, for the same instants.
    [contracts/reservations-api.md](contracts/reservations-api.md) and the changelog say so.

## R17. Reservation pages and acceptance results (PR 7)

**Decision**:
- **Pages**:
  - My reservations: the state, the creation time, the deadline and the next step.
  - The desk list: active reservations by deadline, with the reader, the book, the time left, and
    issue and cancel buttons.
  - The issue form: the loan period, 14 days by default, 1 to 30.
  - The cancel form: the reason, then a confirmation step.
  - The lend form.
  - The book page says why reserving is not possible when it is not.
- The messages live in one place: the refusal types in `order/services.py` carry them (FR-020).
- End-to-end tests run the whole journey through the web and the API (FR-021).
- **`scripts/smoke_reservation_load.py`** (new):
  - Setup: temporary readers with sessions, made through `manage.py shell` in the web container, and
    one book with one copy.
  - Burst mode: fires simultaneous reservations for the copy.
  - Load mode: times reserve, issue and cancel while 30 readers reserve at once.
  - Output: a JSON summary ending in PASS or FAIL.
  - Cleanup: deletes the readers, whose reservations and loans go with them, and then the book.
- **Where it runs**:
  - CI, on the `ubuntu-latest` leg: the burst, 100 attempts with exactly 1 success, 20 times
    (SC-002).
  - The Pi: the operator runs both modes (SC-003).
  - The results, with the date and the method, go into [Measurements](#measurements).
- **Docs**: `docs/features/reservations.md` (new) describes the journey from both sides of the desk,
  and the README is updated (FR-021).

## R18. Technical log format and the request identifier (PR 8)

**Decision**:

- **Format**: one line per record, the same in the web, worker and backup services:

  ```text
  2026-10-27T10:15:30.123Z WARNING web 8f14e45fceea167a5a36dedd4bea2543 django.request: Forbidden: /api/v1/user/
  ```

  The fields are UTC time with milliseconds, level, service, request identifier (`-` outside a
  request), logger and message.
  - A traceback or multi-line message repeats the header on every continuation line, followed by
    `| `. One search for the identifier finds the error and its whole traceback.
  - User input cannot start a line of its own, which also stops forged log lines.
- **Where it is set up**: `library/library/logs.py` (new) holds the formatter, the filters, the
  context variable and one function that builds the logging configuration. Three places use it:
  - `settings.LOGGING`;
  - gunicorn's `logconfig_dict`;
  - Celery's `setup_logging` signal, which applies the same configuration as service `worker`.
  `entrypoint.sh` writes its startup messages in the same format through a small shell function.
- **The identifier**: `RequestIdMiddleware` (new, first in `MIDDLEWARE`) accepts an incoming
  `X-Request-ID` that matches `[A-Za-z0-9._-]{8,64}`. Otherwise it makes a UUID4 hex. It returns the
  value in the `X-Request-ID` response header.
- **Into background work**:
  - Celery's `before_task_publish` signal adds the identifier to the message headers.
  - `task_prerun` restores it in the worker.
  - A task with no identifier, such as a scheduled one, uses its Celery task id.
  - `smoke_test_tracking` runs against the real worker and checks that the worker's line for the
    persisted event carries the HTTP request's identifier (SC-008).
- **What is logged** (FR-035):

  | Event | Source |
  |---|---|
  | Unhandled errors with traceback | `django.request` at ERROR; Celery's task failures |
  | Refused access | `django.request` at WARNING. Django already logs every 4xx response; its level drops from ERROR to WARNING. |
  | Failed sign-ins | A `user_login_failed` receiver in `authentication`. It logs the account id if the email matches an account, and "unknown account" otherwise; never the email or the password. |
  | Failures and retries of background work | Celery |
  | Broker outages | `events.services`, as today |
  | Embedding failures | `book.embeddings` |
  | Startup steps | `entrypoint.sh` |
  | Backup results | the backup service (R22) |

**Alternatives considered**:
- JSON lines. They are machine-friendly, but the entrypoint and the backup script could not easily
  write them, and they are harder to read in Portainer.
- `python-json-logger`, which would be a new runtime dependency.
- A request-logging package, which would also be a new dependency.

## R19. Keeping secrets and search text out of logs and audit entries (PR 8)

**Decision**:
- **Redaction**: the formatter redacts before it writes, in messages and in exception text:
  - values whose key looks like a password, secret, token, key, CSRF value or session;
  - `Authorization` and `Cookie` headers;
  - the password in a connection URL, written as `scheme://user:***@host`;
  - the `q` parameter in any URL;
  - the literal values of `SECRET_KEY` and `DB_PASSWORD`, wherever they appear.
- **Gunicorn's access log** stays off, because it would record full URLs, search text included.
- **Audit entries** record only the changed fields (role, status, loan dates, copies, reservation
  state) and labels (name and id). They never hold passwords or hashes (FR-039).
- **Tests**:
  - One test performs a failed sign-in with a known password, a search with known text, an
    unhandled error and a role change. It asserts that neither the captured log output nor the audit
    entries contain any of them.
  - A CI step runs after the smoke tests. It searches `docker compose logs` for web, worker and
    backup, and the test output, for:
    - the run's disposable `SECRET_KEY` and `DB_PASSWORD`;
    - the demo passwords;
    - the smoke tests' search words.
    Any match fails the step (SC-007).
- **Analytics search events** keep their text, as KAN-30 designed. The register asks the business
  analyst whether they should (FR-055).

## R20. Log rotation and level (PR 8)

**Decision**:
- **Rotation**: both Compose files get an `x-logging` anchor with the `json-file` driver, `max-size:
  10m` and `max-file: "5"`.
  - That is at most 50 MB per container, and 250 MB for the five containers, well under the 500 MB
    limit (FR-036).
  - `json-file` is Docker's default driver, so `docker logs` and Portainer's log view keep working.
- **Level**: `LOG_LEVEL` sets the level of the application loggers, gunicorn and the worker. It
  defaults to INFO and is documented in `.env.example`, the README and the operator guide.

**Alternatives considered**:
- The `local` driver. It keeps 100 MB per container by default, 500 MB for five, which is exactly the
  limit.
- Log files in a volume, rotated by logrotate. It adds another process, and Portainer's log view
  would go blank.
- A log collector such as Loki. It does not fit the memory budget (spec Assumptions).

## R21. Audit trail: its own app, written with the change (PR 8)

**Decision**:

- **The app**: `library/audit/` is new (see Complexity Tracking). It holds the `AuditEntry` model,
  the `record()` service, the audit context and a read-only admin. It imports no domain app; the
  domain apps call it.
- **Where entries are written**: in the same transaction as the change (FR-037, FR-040), at points
  that every channel already passes through:

  | Change | Written in |
  |---|---|
  | Role granted or removed; account activated or deactivated | `CustomUser.save()`, made atomic, comparing with the locked row |
  | Account deleted | A `post_delete` receiver, which also fires for the admin site's bulk delete |
  | Loan started, returned, reopened or reassigned | `Order.save()`, which is already atomic and locks the row |
  | Loan deleted, including through its account's deletion | A `post_delete` receiver |
  | Reservation created, issued, cancelled or expired | The transitions in `order/services.py` |
  | Book's total copies changed | `Book.save()`, which is already atomic |
  | Book deleted | A `post_delete` receiver |

- **Bulk paths that would skip these points** are refused, as `BookQuerySet` already refuses text
  updates:
  - `count` in a book queryset's `update()`;
  - `end_at`, `book` and `user` in a loan queryset's `update()`, and loans' `bulk_create()`;
  - role and status in an account queryset's `update()`.
  Two existing book tests that bulk-update `count` switch to `save()`.
- **Actor, channel and request id** come from a context variable:
  - The request middleware sets the signed-in user and the channel from the path: `/admin/` is the
    admin site, `/api/` the API, and everything else the web.
  - Celery tasks use channel `system` and no actor.
  - Everything else, such as management commands, scripts and the shell, defaults to channel
    `command` and no actor.
  - A reason is passed explicitly, for cancellations.
- **Unchangeable and readable** (FR-038):
  - `AuditEntry.save()` refuses updates. `delete()`, and the queryset's `update()` and `delete()`,
    refuse.
  - The admin site has no add, change or delete permission, and no API exposes the entries.
  - The admin site is where entries are read, and only librarians reach it.
  - Actor and target are stored as ids and labels, not foreign keys, so entries outlive the account
    or book they describe.
- **Request id**: each entry stores it, which links the entry to the technical logs.
- **Retention**: entries are kept indefinitely. They hold names, so the register asks the product
  owner and the business analyst to set a retention period.
- **ADR 0002** records:
  - audit entries as part of the business record (atomic), unlike analytics (best effort);
  - why the trail gets its own app;
  - the points where entries are written.

**Alternatives considered**:
- Audit rows in the `events` app. Its records are best effort and written by the worker; keeping
  transactional records in the same app invites the wrong guarantee.
- Signals only. `CustomUser.save()` is not atomic, so a failed audit insert could leave the change
  committed.
- `ATOMIC_REQUESTS`. It does not cover commands and tasks, and it wraps every request in a
  transaction.
- A third-party audit package: a new runtime dependency, and its generic diffs record more personal
  data than needed.

## R22. Backups: a sidecar on the database image (PR 9)

**Decision**:

- **The service**: a `backup` service in both Compose files.
  - Image: `pgvector/pgvector:0.8.7-pg18`, the database image. It carries the same major version of
    `pg_dump` as the server, runs on both architectures, and is not a new image.
  - Entrypoint: a POSIX shell script, inline in the Compose file. It installs itself as
    `library-backup` and runs `library-backup loop`.
  - Storage: the `pgbackups` volume, mounted at `/backups` and separate from `pgdata18` (FR-026).
- **When it runs**: every 10 minutes the loop checks two things. If today's (UTC) backup is missing
  and the hour is at or after `BACKUP_HOUR` (default 1, which is 03:00 or 04:00 in Kyiv), it runs a
  backup.
- **Each run**:
  1. `pg_dump --format=custom` to `library-<UTC time>.dump.partial`. One snapshot keeps the backup
     consistent at a point in time (FR-025).
  2. `pg_restore --list`, then `pg_restore --file=/dev/null`, which reads the whole archive (the
     FR-025 check).
  3. `sha256sum` writes `<file>.sha256`, naming the file without its folder so the check also works
     on another machine, and the partial file is renamed.
  4. Pruning: a backup is deleted only when it is older than `BACKUP_KEEP_DAYS` (default 7) and not
     among the 7 newest (FR-026, Story 4 scenario 6).
  5. One log line in the common format (service `backup`), with the file, its size, the duration and
     the result.
- **A failure** logs an ERROR line with `pg_dump`'s message and deletes the partial file. It keeps
  every older backup, and the next check retries (FR-027).
- **Access**: `umask 077`. On the Pi the files are readable only by root, which means the operator.
  They are never in the repository or the image (FR-028).
- **Running one now**: `docker exec <backup container> library-backup once` runs one backup and
  returns its result, for the operator and for CI.
- **CI**: in the development stack, CI runs one backup, restores the file into a scratch database
  and compares its table counts with the live database. That is KAN-62's reproducible trial restore,
  on both architectures.
- **Consistency**: a test keeps the two stacks' backup services identical, like the existing test
  for images.
- **Memory**: an idle shell loop, plus `pg_dump` while it runs. `smoke_stack_budget.py` measures it
  in CI and on the Pi (FR-033).
- **ADR 0003** records the design and the off-device copy decision.

**Alternatives considered**:
- Cron on the Pi. It runs outside the stack, while Principle VI wants the server stack to start from
  images and environment values alone.
- `pg_dump` from the web image through Celery beat. The app image has no PostgreSQL 18 client.
  Adding one grows the image and ties backups to the app.
- A third-party backup image: another image to trust and keep current.
- A bind mount to a folder on the Pi. It needs a host path, which Docker creates owned by root, and
  Portainer's relative paths need a Business Edition option that the stack may not have enabled.
- Physical backups with WAL archiving. They need more storage and moving parts than a 24-hour
  recovery point needs.

## R23. Weekly copy, restore and rehearsal (PR 9, operator)

**Decision**:
- **Weekly copy** (FR-026):
  1. Copy the newest `.dump` and its `.sha256` out of the backup container with `docker cp`.
  2. Move them to another machine with `scp`.
  3. Check them there with `sha256sum -c` and `pg_restore --list`, using a PostgreSQL 18 client or
     the same image.
  4. Keep the last 4 weekly copies there, and delete the transfer copy on the Pi.
- **Restore into a separate database** (FR-029), without touching the live one:
  1. `createdb library_restore`.
  2. `pg_restore --no-owner --exit-on-error`, run from the backup container.
  3. Start a temporary web container from the same image on port 8001, with
     `DB_NAME=library_restore`, `WEB_CONCURRENCY=1` and a broker database of its own
     (`redis://redis:6379/15`), so its events never reach the live worker.
  4. Check the record counts with SQL, a librarian sign-in and a search.
  5. Stop the container, `dropdb`, and flush broker database 15.

  The temporary container adds about 0.7 GB while it runs. Rehearse at a quiet time and record the
  peak.
- **Restore after losing the database**: recreate the volume, restore into `library_db` and restart
  `web`. It migrates and re-encodes on startup as it does today. Restoring into an older release is
  not supported (spec edge case).
- **The rehearsal record** goes into [Measurements](#measurements) (SC-006):
  - the date and the operator;
  - the backup file and its size;
  - how long the restore took, against the 60-minute target;
  - whether the counts matched;
  - the sign-in and search results.

## R24. Persistence, cold start and hosting limits (PR 9, operator)

**Decision**:
- **Persistence** (FR-030, SC-005):
  - Record each table's count with one SQL query ([quickstart.md](quickstart.md)) before and after
    each of these: `docker restart` of each service, a Portainer redeploy and a Pi reboot.
  - For each, record the time from the action until `web` is healthy and `/api/v1/version/`
    answers.
- **Cold start**: after 24 hours without traffic, time the signed-in catalog with
  `smoke_stack_budget.py` (Story 4 scenario 2).
- **Hosting limits** (FR-031):
  - memory, measured with `smoke_stack_budget.py`;
  - disk used by `pgdata18`, `redisdata8`, `pgbackups` and the container logs, from `docker system
    df -v`;
  - free disk space;
  - confirmation that the old Render services are deleted and hold no copy of the data, following
    the operator guide's "Shut down Render" section.
- **No uploaded files** (FR-032): no model has a file field and `MEDIA_ROOT` is unset. The register
  records the rule that a future upload feature keeps its files in a volume the backups cover.

## R25. Accessibility (PR 10)

**Decision**:
- **Automated checks** (FR-042), in `scripts/a11y/`:
  - `package.json` and `package-lock.json` pin Playwright 1.64.0 and @axe-core/playwright 4.13.0,
    the newest releases at least two weeks old. Playwright 1.64.1 and @axe-core/playwright 4.14.0
    are newer.
  - `check_pages.mjs` signs in as the seeded reader and the seeded librarian and loads each main
    page (FR-041). It runs axe with the tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` and
    `wcag22aa`, and fails on any violation.
  - CI runs it on the `ubuntu-latest` leg once the stack has started. It installs Chromium through
    Playwright first.
  - It is CI-only: no runtime dependency and no build step for the site.
- **Likely fixes**, from reading the templates:
  - a skip link;
  - visible focus on links and buttons;
  - errors tied to their fields with `aria-describedby` and `aria-invalid`, in
    `includes/form_snippet.html`;
  - one message region (`role="status"`) in `base.html`, replacing the per-page loops;
  - more contrast for the light grey text;
  - plain-language labels and messages that say what happened and what to do next, confirmation
    steps for deletions and cancellations, and forms that keep what the person typed after an
    error (FR-043);
  - text equivalents for the dashboard's bars;
  - dates with their zone (R16).
- **Manual checks**: each main task in Story 6 with the keyboard alone, and with NVDA in Firefox or
  Chrome. The results are recorded.
- **Walkthrough** (FR-045):
  - at least 3 people who are new to the system, at least 1 of them with little digital experience;
  - each attempts every main task without help;
  - the anonymous results record the task, whether it finished without help, and the problems seen;
  - each problem is fixed or registered.
- **Third-party assets**: Tailwind's CDN and Google Fonts load when the page loads, so the CI check
  needs the network, which CI runners have. A register item covers loading third-party assets in
  readers' browsers.

## R26. Administrator role (PR 11)

**Decision**:
- **The role**: `ROLE_ADMINISTRATOR = 2` ("administrator") is added to `ROLE_CHOICES`, with a
  state-only migration (`authentication/0005`).
- **Predicates**:
  - `is_librarian` now means "has librarian rights": librarian or administrator. Staff and
    admin-site rights follow it.
  - `is_administrator` is new.
- **Who changes roles**:
  - `may_change_role` is true only for administrators, who also keep every librarian right
    (FR-063).
  - The web form, the API serializer and the admin site make `role` read-only for librarians.
  - The choices they offer are reader and librarian.
- **Granting the administrator role** happens only on the server:
  - `createsuperuser` creates an administrator.
  - `manage.py set_administrator <email> [--remove]` changes an existing account.
  - Both are audited, with channel `command`.
  - Removing the librarian or the administrator role keeps the account (FR-063).
- **Operator guide**: "Create the first administrator" replaces "Create the first librarian
  account".

**Alternatives considered**: letting administrators grant the administrator role on the web. The
spec only needs the operator to create the first one, and keeping it on the server keeps the most
powerful change off the internet.

## R27. Merge rules: repository settings applied by Arsen (KAN-72, KAN-73, KAN-74)

**Decision**: these change ruleset 23898585 for `main`:

| Sub-task | Setting |
|---|---|
| KAN-72 | Add `lint` to the required status checks, beside `smoke-test`. |
| KAN-73 | Add the "Require code scanning results" rule for CodeQL: security alerts high or higher, other alerts at error level. It blocks only alerts the PR introduces (spec edge case). |
| KAN-74 | Turn on "Require review from Code Owners". |

- **Evidence** (FR-052, SC-012):
  - the ruleset JSON after each change, from `gh api repos/Arezzon/Library-Django/rulesets/23898585`;
  - one demonstration per rule: a draft PR that fails lint, one that fails the smoke test, one that
    adds a CodeQL alert and one without a code owner's approval. Each is shown blocked, then closed.
- **Effect to plan for**: with code-owner review on, a PR that touches paths owned only by the `*`
  fallback needs Arsen's approval. Arsen's own PRs on those paths need another owner or the
  ruleset's bypass list; that choice is Arsen's.
- **New paths get owners**: `/library/audit/` in PR 8 and `/scripts/a11y/` in PR 10.

## R28. Debt register and closing evidence (PR 12)

**Decision**:
- **The register**: `docs/shared/debt-register.md`, one table. Its columns and rules are in
  [contracts/debt-register.md](contracts/debt-register.md). The items come from:
  - LR1's and LR2's priority debt;
  - the areas KAN-62 names;
  - FR-055's gaps;
  - the findings in R30.
- **Owners**: they start from the risk register's owner roles, each named as a person:
  - R2, the race condition: the senior engineer.
  - R3, test coverage: the QA lead.
  - R7, data loss: the product owner together with the tech lead.
- **Evidence**: PR 12 collects it from PRs 1 to 11 and from the settings:
  - PR links and CI runs;
  - tests;
  - [Measurements](#measurements) and the restore record;
  - the account review and the walkthrough.
- **Jira**, by the assignee:
  - KAN-18 and KAN-19 get corrected descriptions.
  - KAN-62 links the register.
  - KAN-62 moves to Done only when no P1 item is open or blocked (FR-056).

## R29. Constitution amendments

**Decision**: each amendment ships in the PR that changes the governed fact, so the constitution is
accurate after every merge.

| PR | Bump | Change |
|---|---|---|
| 7 | PATCH | Workflow item 4: the smoke-test job runs the reservation burst |
| 8 | MINOR | Principle I lists `audit`. Principle V adds "a critical change with its audit entry" to the writes that must succeed or fail together, and says that audit entries are part of the business record, unlike analytics. Workflow item 4: the test command includes `audit`, and smoke-test checks the logs for secrets. |
| 9 | PATCH | Principle VI's list of the stack's services adds `backup`. Workflow item 4: smoke-test runs the backup and restore check. |
| 10 | PATCH | Workflow item 4: smoke-test runs the accessibility check |
| 11 | MINOR | Principle II adds the administrator audience (`ROLE_ADMINISTRATOR`), the only role that grants or removes the librarian role |

- Versions are numbered in merge order.
- Each amendment:
  - goes through `/speckit-constitution`;
  - updates `AGENTS.md` and the README where they repeat the changed text;
  - adds a changelog entry.
- While the Superpowers handoff is `executing`, set it to `blocked` for the amendment (R1).
- PR 3's coverage report blocks nothing, so the CI gate list does not change. PR 3's description
  records the review that the constitution requires whenever the CI workflow changes.

## R30. Findings for the register

| Finding | Where | Handling |
|---|---|---|
| `/authentication/` returns a server error (its template does not exist) | `authentication/urls.py` | Fixed in PR 1 (R4) |
| Through the API and the admin site, deleting a book also deletes its loans | book API, admin site | Fixed in PR 4 (R10) |
| An account's creation time changes on every save | `authentication/models.py` | Fixed in PR 3; past values are lost (R9) |
| A book's total copies can be negative | `book/models.py` | Fixed in PR 3 (R9) |
| DRF's Basic authentication is on by default | settings | Removed in PR 1 (R2) |
| Signing out works through GET, so a link on another site can sign people out | `authentication/views.py` | Register, P3 |
| The admin site's user form shows the password hash as an editable text field | `authentication/admin.py` | Register, P3 |
| Pages load Tailwind and fonts from third-party servers in readers' browsers | `base.html` | Register, P3 (privacy and availability) |
| Audit entries have no retention period | `audit` | Register, P2, for the product owner and the business analyst |
| The gaps FR-055 lists: weekly-only off-device copies, analytics search text, English only, browser tests not in CI, P2 search and forecasting out of scope | — | Register |

## Measurements

PRs 1 to 11 fill this section. Each entry gives the date, the method and the result. PR 12 links
each entry from the register.

- Query counts per list, before and after PR 2 (FR-048).
- Coverage of added and changed lines, per PR (FR-051).
- Catalog page load p95 on the Pi (SC-010).
- Memory and search p95 on the Pi after PRs 5, 8 and 9 (FR-033, SC-014).
- The librarian account review after PR 1 (FR-007).
- The restore rehearsal (FR-029, SC-006).
- Persistence after a restart, a redeploy and a reboot, and the cold start (FR-030, SC-005).
- Disk use and the shutdown of the old hosting (FR-031).
- The reservation burst and load on the Pi (SC-002, SC-003).
- The accessibility results: automated, keyboard and screen reader (SC-009).
- The walkthrough (FR-045).
- The merge-rule demonstrations (SC-012).

### Query counts per list (PR 2, FR-048)

**Date**: 2026-10-28.

**Method**:
- Each list's test in `library/<app>/test_queries.py` loads the list through Django's test client
  with 1 row, then with 50. It counts the queries of each load with `CaptureQueriesContext`
  (`library/library/testing.py`).
- The tests sign in as the list's audience. They run on PostgreSQL 18 in `docker-compose-dev.yml`,
  with the encoder mocked.
- Every count includes the 2 queries that load the session and the signed-in account.
- "Before" is `main` at `f19f808`; "after" is PR 2.

**Result**: every list now uses the same number of queries with 1 row and with 50. Only the API's
author list changed. It read each author's books with a separate query, so it grew from 4 queries to
53; it now prefetches them and stays at 4.

| List | Signed in as | Before: 1 row / 50 rows | After: 1 row / 50 rows |
|---|---|---|---|
| Web book list, `/book/` | reader | 5 / 5 | 5 / 5 |
| Web book list of one author, `/book/?author_id=<id>` | reader | 5 / 5 | 5 / 5 |
| API book list, `/api/v1/book/` | reader | 4 / 4 | 4 / 4 |
| API search, `/api/v1/books/search/?q=…` (at most 20 results) | reader | 4 / 4 | 4 / 4 |
| Web author list, `/author/` (each author with 3 books) | librarian | 4 / 4 | 4 / 4 |
| **API author list, `/api/v1/author/`** (each author with 3 books) | librarian | **4 / 53** | **4 / 4** |
| Web user list, `/authentication/users/` | librarian | 3 / 3 | 3 / 3 |
| API user list, `/api/v1/user/` | librarian | 3 / 3 | 3 / 3 |
| All loans, `/order/all/` | librarian | 3 / 3 | 3 / 3 |
| My loans, `/order/my/` | reader | 3 / 3 | 3 / 3 |
| A reader's books, `/book/user/<id>/` | librarian | 4 / 4 | 4 / 4 |
| API loan list, `/api/v1/order/` | librarian | 3 / 3 | 3 / 3 |
| API list of one user's loans, `/api/v1/user/<id>/order/` | reader | 3 / 3 | 3 / 3 |
| Analytics dashboard, `/events/` (25 events per page) | librarian | 11 / 11 | 11 / 11 |

### Coverage of added and changed lines (FR-051)

**Method**: the full test command runs under `coverage run --rcfile=/app/pyproject.toml`
in the web container, with the real-model tests on. `diff-cover` then compares
`coverage.xml` with the pull request's base, from `library/`. The settings in
`pyproject.toml` measure the five apps and the project package, and leave out
migrations, test files and test helpers. From PR 3 on, CI posts the same report on every
pull request.

| Pull request | Date | Changed lines measured | Covered | Note |
|---|---|---|---|---|
| PR 1, access control | 2026-10-28 | 127 | 100% | Measured locally before the report existed |
| PR 2, query counts | 2026-10-28 | 1 | 100% | Measured locally; `scripts/smoke_stack_budget.py` runs outside the Django tests and was checked by running it |
| PR 3, tests and coverage | 2026-10-28 | 32 | 100% | Measured locally against `main`, after PR 2 merged |

The whole of the measured code stood at 87% after PR 3 (1,862 statements, 247 not run).

### Memory with the reservation expiry in the worker (PR 5, Principle VI)

Celery beat now runs inside the existing worker (`--beat`, R11), so the stack adds no container.
CI's memory check, run on the development machine on 2026-10-28 with beat running and after the
scheduled expiry had run:

| Containers | Peak memory | Search p95 | Catalog p95 | Book save p95 | Result |
|---|---|---|---|---|---|
| 5 | 2.882 GiB | 52.8 ms | 26.9 ms | 48.8 ms | PASS (limit 4 GiB) |

PR 8's run on the same machine, before beat, peaked at 2.955 GiB, so the embedded scheduler adds
no measurable memory. CI repeats the check on every run.

### Librarian account review after PR 1 (FR-007)

- **Date**: 28.10.2026, after PR 1 was deployed.
- **Method**: the operator reviewed every librarian account on the server (R7).
- **Result**: 1 account reviewed, none changed. No unauthorized changes or signs of
  exploitation were found.
- **Record**: [the comment on #36](https://github.com/Arezzon/Library-Django/pull/36#issuecomment-6468084803).
