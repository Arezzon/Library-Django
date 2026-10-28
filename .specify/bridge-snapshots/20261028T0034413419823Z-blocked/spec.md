# Feature Specification: Close the Priority Technical Debt of v1.0

**Feature Branch**: One branch per pull request (FR-062); no branch is shared by the whole feature

**Created**: 2026-10-27

**Status**: Draft

**Input**: User description: "Complete KAN-62 from Jira (https://arsensworkspace-47040086.atlassian.net/browse/KAN-62), each sub-KAN should go into seperate PR if it need to change or implement something"

**Source task**: KAN-62, "Close the remaining priority technical debt of v1.0 and confirm the
result", a task in epic KAN-2 "Modernize the base system", planned for the sprint "Lab 4 ·
Development" (2026-10-24 to 2026-11-03). It asks the team to bring the priority technical debt
recorded in the LR1 and LR2 analyses to a verified state, and says that a plan alone does not close
it. It names six areas and the issues behind them:

1. the framework and dependency upgrade and the migration check (KAN-17);
2. correct availability without N+1 queries, and atomic issuing and reservation (KAN-18, KAN-19,
   KAN-55 to KAN-58), with the code and the issue descriptions brought in line now that the stored
   available count is gone;
3. meaningful unit, integration and concurrency tests for books, loans and reservations, lint,
   format and static analysis checks, and CI that pull requests must pass (KAN-21, KAN-22, KAN-15);
4. no default production secrets and a secure configuration (KAN-24);
5. reliable media storage and database backups with a trial restore, with the hosting limits, cold
   start and data persistence checked;
6. a register of the remaining debt in which every open item has an owner, a priority and a plan.

It adds two P1 gaps from LR1 that must also be confirmed: centralized technical logs with an audit
of critical changes that never holds passwords, keys or the full text of private queries, and main
pages that people with any level of digital experience can use and understand. Its acceptance
criteria are: (1) every item links to a change or a check, or records the blocker that keeps the
task open; (2) CI, migrations, concurrency tests, the secrets check and the trial restore give
reproducible results; (3) catalog and availability queries are measured, the N+1 fix is documented,
and the demo deployment keeps its data after a restart; (4) the debt register, the README and the
ADRs are updated and no critical P1 item is open. P2 search and demand forecasting are out of
scope. KAN-62 had no Jira sub-tasks when this spec was written, so in this spec a "sub-KAN" is each
issue that KAN-62 names, plus the five sub-tasks KAN-67 to KAN-71 that this feature created for
KAN-62's own work (FR-059).

**Background sources**: the team's LR1 analysis of v1.0 (its technical debt table, the state of the
non-functional requirements and the risks), the LR2 design of v2.0 (targets of 95% of catalog
requests within 2 s, 95% of reservation and issue operations within 3 s with no double hold or
issue, WCAG 2.2 AA for both interfaces, regular backups with a verified restore, and 85% test
coverage of new and changed code), and the LR3 status, which lists backups and the trial restore,
media after a restart, technical logs, regression tests and catalog queries as the KAN-62 items
still to confirm. The business analyst's LR2 draft in the team folder adds the roles requirement
(an administrator grants or removes the librarian role) and the clarity criteria of US-09, and the
team's Confluence roadmap holds the risk register with an owner role for each risk. The Markdown
sources that KAN-62 cites by name are in neither the team folder nor Confluence.

### Starting point (2026-10-27)

| Item named in KAN-62 | Issue | Jira status | What the repository and the server show | Remaining work |
|---|---|---|---|---|
| Framework and dependency upgrade, migration check | KAN-17 | Done | Django 5.2 LTS and current dependencies since pull requests #30 to #32 and #34; a test fails whenever a model change has no migration | Evidence only |
| Availability without N+1 queries | KAN-18 | Done | Availability is derived from total copies minus unreturned loans in one aggregate, and the book list in the API has a constant-query test. The author list in the API still reads each author's books with a separate query. The Jira description names an order status field that does not exist | Measure every list, fix the author list, lock the counts with tests, correct the description |
| Atomic issuing | KAN-19 | Done | Issuing locks the book and rechecks availability, and tests cover two parallel issues of the last copy. The Jira description still says that issuing decreases a stored counter | Correct the description, record the evidence |
| 48-hour reservation, stages 1 to 4 | KAN-55 to KAN-58 | Idea | No reservations exist. Readers issue books to themselves on the web and through the API | All of it |
| Business-logic tests | KAN-21 | Idea | Book, loan (including concurrency), account and analytics tests exist. The author app has none, and coverage is not measured | Fill the gaps, measure coverage |
| Lint and format in CI | KAN-22 | Done | The lint check runs on every pull request, but `main` requires only the smoke test before a merge | Make it a merge requirement (repository setting) |
| Code scanning | KAN-15 | Done | Code scanning runs on pull requests and weekly, but is not a merge requirement | Make it a merge requirement (repository setting) |
| Code-owner review (related) | KAN-13 | Done | The ruleset for `main` still merges with one approval from anyone, because code-owner review is switched off | Switch it on (repository setting) |
| No default secrets, secure configuration | KAN-24 | Done | The site refuses to start without a secret key, debug is off unless enabled, and CI checks that the image holds no key. However, the sign-up form offers the librarian role, a reader can change their own role and account status on the profile page, and the user, author, book, loan and search operations of the API declare no audience, so they accept anonymous callers, and all but search accept changes. A librarian has full administrative rights | Close the access-control gap |
| Reliable media storage | — | — | The product stores no uploaded files and never has. All data lives in the database and broker volumes | Verify persistence and record it |
| Database backup with a trial restore | — | — | The operator guide gives manual backup and restore commands. Nothing is scheduled, kept, copied off the device or rehearsed | All of it |
| Hosting limits, cold start, data persistence | — | — | The free hosting used by v1.0 slept when idle (the first request took over a minute) and erased its data after 30 days. The Raspberry Pi removed both, and its memory and search budget is measured (2.669 GiB peak, search p95 243 ms). Restart times and data survival are not recorded | Measure and record |
| Centralized technical logs, audit of critical changes | — | — | Request errors go to the console and little else is logged. There is no request identifier, no log rotation in either stack and no audit trail. Analytics events are best effort and may be lost | All of it |
| Accessible, understandable main pages | — | — | Never audited. Times are shown in UTC | All of it |
| Debt register, README and ADRs | — | — | No register and no ADRs exist | All of it |

## Clarifications

### Session 2026-10-27

- Q: Beyond refusing a second active reservation of the same book and a reservation of a book the
  reader has on loan, which limits apply to reserving and issuing? KAN-57 requires these refusal
  rules to be agreed before implementation. → A: A reader may hold at most 3 active reservations at
  once, and a reader with an overdue loan can neither reserve a book nor be issued one until they
  return it.
- Q: Must a copy of each backup leave the Raspberry Pi, so that losing the Pi or its disk does not
  lose both the data and the backups? → A: Yes, through a documented manual step. Daily backups stay
  on the Pi, separate from the database, and once a week the operator copies the newest backup to
  another machine.
- Q: How should the KAN-62 work that has no Jira issue of its own become pull requests? → A: Create a
  Jira sub-task under KAN-62 for each of the four parts (technical logs and audit, backups and
  restore, accessibility and clarity, and the debt register), with the assignee's confirmation, and
  deliver one pull request per sub-task. Access control stays its own KAN-24 pull request.
- Q: How are the merge requirements for code scanning (KAN-15) and the lint check (KAN-22) applied?
  → A: As repository settings, by Arsen, through a Jira sub-task under each issue that is assigned
  to him (KAN-73 under KAN-15, KAN-72 under KAN-22). Neither needs a pull request.
- Q: Should the KAN-62 sub-tasks be drafted for the assignee's confirmation before they are created?
  → A: No. They were created directly, as KAN-67 to KAN-71.
- Q: Who may grant or remove the librarian role? → A: Librarians for now, so that the access-control
  pull request stays small and closes the live gap fast. A later pull request adds the administrator
  role that LR2 requires, after which only administrators grant or remove the librarian role.
- Q: Should a reservation hold one unit of a book's stock, or one specific physical copy that the
  library tracks individually? → A: One unit of stock, counted the same way loans are. No copy records
  are added, and the ADR delivered with KAN-55 records the choice and the rejected alternative.
- Q: Should Arsen also get a sub-task under KAN-13 to switch on required code-owner review for
  `main`? → A: Yes. KAN-13 is marked Done, but the ruleset still merges without a code owner's
  approval. Like the sub-tasks of KAN-15 and KAN-22, it is a repository setting that Arsen applies
  (KAN-74).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Only librarians can grant access or change library data (Priority: P1)

A visitor who signs up always becomes a reader. Only a librarian can make someone a librarian, take
the role away, or activate and deactivate an account; a later stage of this feature hands the
granting and removing of the librarian role to a separate administrator role, as LR2 requires. A
reader can still edit their own name, but not their role or their account status. Every operation of the API states who may use it: anonymous
callers reach only the sign-in and registration pages, the version check and the API
documentation; readers read the catalog and their own records; only librarians change the catalog,
other people's accounts and loans. People who use the site as intended notice no difference.

**Why this priority**: Anyone on the internet can make themselves a librarian today, and a librarian
has full administrative rights, so the deployed site can be taken over and personal data read
without signing in. Every other control in this feature, from reservations to issuing by librarians
and the audit trail, depends on roles that can be trusted, so this story ships first.

**Independent Test**: Without signing in, try to register as a librarian and call every operation of
the API. As a reader, try to change your own role, open another user's record, and change a book, an
author and someone else's loan through the web, the API and the admin site. As a librarian, perform
every librarian task. Only the librarian's attempts and the reader's own reads succeed.

**Acceptance Scenarios**:

1. **Given** the sign-up page, **When** a visitor registers, **Then** the new account is a reader
   account and the page offers no way to choose a role or an account status.
2. **Given** a signed-in reader on their own profile page, **When** they submit a change to their role
   or account status, including through a hand-crafted request, **Then** the change is refused and
   nothing is changed.
3. **Given** a signed-in librarian, **When** they activate or deactivate an account, or, until the
   administrator role ships (FR-063), grant or remove the librarian role, **Then** the change takes
   effect and leaves an audit entry (Story 5).
4. **Given** an anonymous caller, **When** they call any operation of the API other than the version
   check, the documentation, the schema and the index, **Then** the call is refused and no data is
   returned or changed.
5. **Given** a signed-in reader, **When** they use the API, **Then** they can read books, authors and
   search results, read and rename their own account, and read their own loans, and every other
   operation is refused, except the reader actions this feature adds (Stories 2 and 3).
6. **Given** a refused call, **When** the caller is anonymous, **Then** the response says that signing
   in is required; **when** the caller is signed in but not allowed, **then** it says that the action
   is not permitted. Neither response reveals whether the record exists.
7. **Given** the published API schema, **When** a maintainer reads it, **Then** every operation states
   who may call it and the refusal responses it can return.
8. **Given** the administrator role has shipped (FR-063), **When** a librarian tries to grant or
   remove the librarian role through the web, the API or the admin site, **Then** the change is
   refused; **when** an administrator does the same, **then** it takes effect, the account is kept and
   the change leaves an audit entry.

---

### User Story 2 - A reader reserves an available book for 48 hours (Priority: P2)

A signed-in reader finds a book with a copy available and reserves it in one step. The reservation is
active at once, without waiting for a librarian, and holds one copy for exactly 48 hours. The reader
sees the deadline in local time and what to do next: collect the book from a librarian before the
deadline. While the hold lasts, nobody else can reserve or borrow that copy. When the deadline
passes, the copy counts as available again immediately, even if no background cleanup has run.

**Why this priority**: The 48-hour reservation is a P1 goal of v2.0 (epic KAN-48) and the reason the
stock accounting had to become atomic. KAN-62 counts the debt as closed only when reservations, like
loans, can never hold or lend more copies than exist.

**Independent Test**: Give a book exactly one available copy. Have two readers reserve it at the same
moment, check that a librarian cannot lend the held copy to someone else, then let the deadline pass
and check the availability again.

**Acceptance Scenarios**:

1. **Given** a signed-in reader and a book with an available copy, **When** they reserve it, **Then**
   the reservation is active immediately, its deadline is exactly 48 hours after its creation, and
   the book's available count drops by one wherever it is shown: catalog, book page, search results
   and API.
2. **Given** a book with no available copy, **When** a reader tries to reserve it, **Then** no
   reservation is created and the reader is told plainly that no copy is available.
3. **Given** one available copy, **When** two readers reserve it at the same moment, **Then** exactly
   one succeeds and the other is told that no copy is available.
4. **Given** an active reservation on the last copy, **When** a librarian tries to lend that book to
   another reader without a reservation, **Then** the loan is refused because no copy is available.
5. **Given** a reservation whose deadline has passed, **When** anyone views or uses the book's
   availability, **Then** the expired reservation no longer reduces it, whether or not any cleanup has
   run, and the reservation is shown as expired.
6. **Given** a reader who already has an active reservation or an active loan of a book, **When** they
   try to reserve the same book, **Then** the request is refused with a message that says why.
7. **Given** a reader's reservations, **When** the reader opens them, **Then** each shows its state, its
   deadline in the library's local time and the next step.
8. **Given** a reader who already holds 3 active reservations, **When** they try to reserve another
   book, **Then** the request is refused, and the message says that the limit is 3 and that collecting
   or cancelling a reservation frees a place.
9. **Given** a reader with an overdue loan, **When** they try to reserve a book, **Then** the request is
   refused, and the message names the overdue book and its due date and says to return it first.

---

### User Story 3 - A librarian issues a reserved book or cancels a reservation with a reason (Priority: P3)

When the reader comes to the desk, the librarian finds the active reservation and issues the book. In
one step the reservation becomes "issued" and the loan starts, so the copy is never counted twice or
released in between. When a reservation has to end early, for example because the copy is damaged,
the librarian cancels it and gives a reason. The copy becomes available again at once, the
cancellation records who made it, when and why, and the reader sees it the next time they open the
site. Readers no longer lend books to themselves: every loan starts with a librarian.

**Why this priority**: LR2 moved issuing from the reader to the librarian, and KAN-57 requires the move
to be atomic and checked by role. Without it a reservation is a promise that nobody can keep.

**Independent Test**: As a librarian, issue an active reservation and confirm that exactly one loan
exists, then repeat the request and confirm that no second loan appears. Try to issue an expired
reservation. Cancel another reservation with a reason and confirm that the copy is free, the audit
entry exists and the reader sees the notice. As a reader, try through the web and the API to start a
loan, to issue a reservation and to cancel another reader's reservation.

**Acceptance Scenarios**:

1. **Given** an active, unexpired reservation, **When** a librarian issues it, **Then** in one step the
   reservation becomes issued and a loan starts for that reader and book, with the loan period the
   librarian chose (14 days by default, 1 to 30), and the available count does not change at that
   moment, because the held copy becomes the lent copy.
2. **Given** the same issue request sent twice, by a double click, a retry or two librarians, **When**
   both arrive, **Then** exactly one loan exists and the second request is told that the reservation
   was already issued.
3. **Given** a reservation whose deadline has passed, **When** a librarian tries to issue it, **Then**
   no loan is created from it, and the librarian is told that it expired and that a normal loan is
   possible only while a copy is available.
4. **Given** an active reservation, **When** a librarian cancels it with a reason, **Then** the
   reservation becomes cancelled, the copy is available again at once, and the audit trail records the
   librarian, the time and the reason.
5. **Given** a cancellation without a reason, **When** a librarian submits it, **Then** it is refused
   and nothing changes.
6. **Given** a reader whose reservation the library cancelled, **When** the reader next opens the site,
   **Then** they see that it was cancelled, when it was cancelled and the reason.
7. **Given** a signed-in reader, **When** they try through the web or the API to start a loan, to issue
   any reservation or to cancel another reader's reservation, **Then** the attempt is refused and
   nothing changes.
8. **Given** a reader's own active reservation, **When** the reader cancels it, **Then** it becomes
   cancelled and the copy is available again; no reason is needed.
9. **Given** a reservation created at a known time, **When** a librarian issues it one second before
   the 48 hours are up, **Then** it succeeds; **when** they issue it at or after that moment, **then**
   it is refused.
10. **Given** a loan started by a librarian, **When** the activity analytics record it, **Then** it
    counts as that reader's borrow, and the librarian is recorded as the person who issued it.
11. **Given** a reader with an overdue loan, **When** a librarian tries to issue them a reserved book or
    lend them a book directly, **Then** no loan is created, and the librarian is told which overdue
    book must be returned first.

---

### User Story 4 - The deployed library keeps its data and can be restored from a backup (Priority: P4)

The Raspberry Pi deployment keeps every account, book, loan, reservation and audit entry when a
service restarts, when the stack is redeployed and when the Pi reboots, and it answers the first
request after a quiet period as fast as any other. The database is backed up automatically every day,
each backup is checked and kept on the Pi for at least a week, and once a week the operator copies the
newest backup to another machine. An operator who follows the operator guide can restore the latest
backup, and that restore has been rehearsed on the Pi and its result recorded.

**Why this priority**: LR1 rates losing data on a restart as high-priority debt, and LR2 requires
regular backups with a verified restore (risk R7, data loss). The move to the Pi removed the old
hosting's sleep and 30-day data limit, but nobody has yet shown that a restore works. With
reservations and the audit trail, the database becomes the library's only record of who holds what.

**Independent Test**: Record how many records of each kind exist, restart every service, redeploy
the stack and reboot the Pi, and confirm after each step that the counts match and the site answers
within the target time. Then restore the latest backup into a separate database by following the
guide, start the application on the restored copy, and check the counts, a librarian sign-in and a
search.

**Acceptance Scenarios**:

1. **Given** the running deployment, **When** a single service restarts, the stack is redeployed or the
   Pi reboots, **Then** every stored record is still there and unchanged, and the site serves pages
   again within 3 minutes.
2. **Given** a deployment that has been idle for 24 hours, **When** the first visitor opens the
   catalog, **Then** it loads as fast as any other request, with no wake-up delay.
3. **Given** a normal day, **When** the daily backup runs, **Then** a new, complete backup exists, it
   is checked to be readable, and the operator can see that the latest backup succeeded.
4. **Given** a backup that fails, **When** the operator checks, **Then** the failure and its cause are
   visible in the logs, and the earlier backups are kept.
5. **Given** the latest backup, **When** the operator follows the guide's restore steps, **Then** the
   restored database holds the same records as at backup time, the application starts on it, a
   librarian can sign in and search returns results, all without touching the live database.
6. **Given** backups older than the retention period, **When** the next backup runs, **Then** they are
   removed automatically, and at least the 7 most recent daily backups always remain.
7. **Given** the weekly routine in the operator guide, **When** the operator follows it, **Then** the
   newest backup is copied to another machine and checked to be readable there.

---

### User Story 5 - Maintainers trace failures and critical changes without exposing secrets (Priority: P5)

When something fails, an operator finds the cause in one place. The web and worker services write
their technical log lines in one consistent format, with a request identifier that follows a request
into the background work it starts. Every critical change leaves an audit entry with who made it,
what changed, when, and, where a reason is required, why. Critical changes are granting or removing
a role, activating or deactivating an account, starting, returning, reopening or reassigning a loan,
creating, issuing, cancelling or expiring a reservation, and changing or deleting a book's stock. No
log line and no audit entry ever contains a password, a secret, a token, a session identifier or the
full text of what someone searched for.

**Why this priority**: LR1 names the missing logs as a stability risk, and KAN-62 lists logs and the
audit trail among the P1 gaps that must be confirmed before it closes. Stories 1 to 4 come first only
because they close risks that reach users directly.

**Independent Test**: Cause a failing request and find all of its log lines, from web and worker, by
its request identifier. Perform each critical change and find its audit entry. Search every log line
and audit entry produced by the full test suite and the smoke test for passwords, secrets, tokens and
search text.

**Acceptance Scenarios**:

1. **Given** a request that fails in the web service or in the background work it started, **When**
   the operator searches the logs for its request identifier, **Then** every related line from both
   services is found, with the error and its traceback.
2. **Given** each critical change, **When** it is completed through the web, the API, the admin site
   or a management command, **Then** exactly one audit entry records the actor, the action, the
   record, the time, the values before and after, the reason where one is required, and the channel.
3. **Given** a critical change that fails or is rolled back, **When** the audit trail is read, **Then**
   it holds no entry for that change.
4. **Given** an audit entry, **When** anyone tries to edit or delete it through the application,
   **Then** they cannot, and only librarians can read it.
5. **Given** a failed sign-in, a refused request or a search, **When** it is logged, **Then** the log
   line holds no password, secret, token, session identifier or search text.
6. **Given** a long-running server, **When** the logs grow, **Then** they are rotated and never use
   more than the disk limit set in FR-036.

---

### User Story 6 - People with any level of digital experience can use the main pages (Priority: P6)

Readers and librarians can complete the main tasks with a keyboard alone or with a screen reader, and
people who are new to the system complete them without help. For readers the main tasks are signing
in, registering, searching and browsing the catalog, opening a book, reserving it, and checking their
loans and reservations. For librarians they are finding a reservation, issuing a book, recording a
return, cancelling a reservation, and managing books, authors and accounts. Labels, messages and
confirmations use plain words, say what happened and what to do next, and show times in the
library's local time.

**Why this priority**: LR1 warns that librarians with little digital experience will make mistakes in
issuing and returns that distort the stock. LR2 sets WCAG 2.2 AA for both interfaces, KAN-58 requires
a keyboard-accessible reservation journey, and KAN-62 requires accessibility and clarity to be checked
before it closes.

**Independent Test**: Run the automated accessibility checks on every main page, complete each main
task with the keyboard alone and with a screen reader, and run a short task walkthrough with people
who have never used the system.

**Acceptance Scenarios**:

1. **Given** each main page, **When** the automated accessibility check runs, **Then** it reports no
   WCAG 2.2 level A or AA violation.
2. **Given** a keyboard only, **When** a person completes each main task, **Then** every control can be
   reached in a logical order, the focused control is always visible and focus is never trapped.
3. **Given** a screen reader, **When** a person completes the reservation and issuing journeys,
   **Then** every control, field, error and change of state, such as a new deadline or a refusal, is
   announced.
4. **Given** a form error, **When** it appears, **Then** it names the field, says what is wrong and how
   to fix it, and keeps what the person typed.
5. **Given** an action that cannot be undone, such as deleting a record or cancelling a reservation,
   **When** a person starts it, **Then** they confirm it in a step that says what will happen.
6. **Given** any date or time shown to people, such as a reservation deadline or a loan's due date,
   **When** it is displayed, **Then** it is in the library's local time zone and says which zone.
7. **Given** a walkthrough with at least three people who are new to the system, at least one of them
   with little digital experience, **When** they attempt each main task, **Then** at least 80% of the
   attempts finish without help, and every problem observed is fixed or entered in the debt register.

---

### User Story 7 - Catalog pages stay fast as the catalog grows (Priority: P7)

Every page and API list that shows books, authors, loans, reservations or accounts loads its data
with a fixed number of database queries, however many rows it shows, and the measurements that prove
it are recorded. The one case found so far, the author list of the API, which reads each author's
books separately, is fixed.

**Why this priority**: LR1 rated performance as "partial, risk of N+1 queries". KAN-18 replaced the
stored counter with an aggregate, and KAN-62 asks for the catalog and availability queries to be
measured and the N+1 fix documented. The risk grows with the catalog, but no list is slow today.

**Independent Test**: For each page and API list, count the database queries with 1 row and with 50
rows and compare them, then time catalog pages on the Pi.

**Acceptance Scenarios**:

1. **Given** each page and API list in scope, **When** it shows 1 row and when it shows 50 rows,
   **Then** it uses the same number of database queries.
2. **Given** the author list of the API, **When** it returns authors with their books, **Then** its
   query count no longer grows with the number of authors.
3. **Given** a later change that adds a query per row to any of these lists, **When** the tests run,
   **Then** they fail.
4. **Given** the measurements, **When** a reviewer reads the feature documentation, **Then** the query
   count of each list, the method, the date and the catalog response times on the Pi are recorded.

---

### User Story 8 - Tests and merge rules catch regressions before they reach the library (Priority: P8)

Maintainers change book, author, loan and reservation code knowing that unit, integration and
concurrency tests cover every business rule, and that nothing can merge into `main` unless the lint
and format check, the full smoke test and code scanning have passed and a code owner has approved.

**Why this priority**: LR1 rates the low test coverage of the business logic as high-priority debt,
KAN-21 is still open, two of the three checks that the constitution names as merge gates run on
every pull request but do not block a merge, and the code-owner review that KAN-13 was meant to
switch on is not enforced.

**Independent Test**: Read the coverage report for the business-rule code, then open a pull request
that breaks the lint check and confirm that it cannot be merged.

**Acceptance Scenarios**:

1. **Given** the rules for books, authors, loans and reservations, **When** the test suite runs,
   **Then** every rule has a test that fails if the rule breaks, including the role allowed for each
   action and at least one role that is refused.
2. **Given** two simultaneous loans of the last copy, two simultaneous reservations of it, or a
   reservation racing a loan, **When** the concurrency tests run on the database that CI uses,
   **Then** only one of the two succeeds every time.
3. **Given** the lines that this feature adds or changes, **When** CI measures coverage, **Then** at
   least 85% of them run under the tests, and the report appears on every pull request.
4. **Given** a pull request into `main` whose lint check, smoke test or code scanning fails, or that
   lacks an approval from a code owner of a path it touches, **When** anyone tries to merge it,
   **Then** the merge is blocked.
5. **Given** the author app, which has no tests today, **When** the test suite runs, **Then** it
   includes tests for creating, editing and deleting authors and their links to books.

---

### User Story 9 - The team sees what debt remains, who owns it and the proof for what was closed (Priority: P9)

The product owner, the business analyst and reviewers open one register that lists every priority
debt item from LR1, LR2 and this feature's own findings. Each item shows its priority, owner and
status, and either its evidence (a merged pull request, a CI run, a test, a measurement or a restore
record) or, if it is still open, a plan or a blocker. KAN-62 links to the register, and the README,
the ADRs and the Jira issues describe what the product actually does.

**Why this priority**: The register is how KAN-62 proves its first and fourth acceptance criteria, and
the task stays open while any P1 item in it remains open. It records the other stories, so it comes
last.

**Independent Test**: Pick any item named in KAN-62, follow its link to the evidence, and confirm that
no P1 item is open.

**Acceptance Scenarios**:

1. **Given** each item named in KAN-62, **When** a reviewer looks it up in the register, **Then** it
   links to the change or check that closed it, or names the blocker that keeps KAN-62 open.
2. **Given** an open item, **When** it is listed, **Then** it has an owner, a priority and a plan with
   a target sprint.
3. **Given** the register, **When** KAN-62 is moved to Done, **Then** no P1 item is open or blocked.
4. **Given** KAN-18 and KAN-19 in Jira, **When** someone compares them with the product, **Then** their
   descriptions match it: availability is the total number of copies minus active loans and active
   reservations, and nothing decreases a stored counter.
5. **Given** the items that were done before this feature (KAN-15, KAN-17, KAN-19, KAN-22 and
   KAN-24), **When** the register lists them, **Then** each links to its merged pull requests and to
   the tests or CI runs that verify it today.
6. **Given** the README and the ADRs, **When** a newcomer reads them, **Then** they describe
   reservations, issuing by librarians, roles, backups and logs as delivered.

---

### Edge Cases

- **Accounts that became librarians through the open sign-up**: after the access-control change is
  deployed, the operator reviews every librarian account on the server and removes the role from, or
  deactivates, any account that is not an authorized librarian. The review is recorded.
- **Public disclosure of the access-control gap**: the repository is public and the site is
  reachable, so the access-control pull request is merged and deployed first, and this spec, which
  describes the gap, is published only after that (FR-060).
- **Clients and checks that call the API anonymously today**: CI's endpoint checks and the Raspberry
  Pi measurement script call the search API without signing in. They are changed to keep working
  under the new rules, and no rule is weakened for them. No other anonymous client is known.
- **Loans that readers started before issuing moved to librarians**: they stay valid and can be
  returned as before. A reader who is part-way through the old borrowing form when the release goes
  live is sent to the reservation step instead.
- **The deadline at the boundary**: a reservation is active while less than 48 hours have passed since
  its creation. At exactly 48 hours it is expired. The 48 hours are elapsed time, so a daylight saving
  change neither lengthens nor shortens them.
- **A reservation that expires while a librarian is issuing it**: the issue step checks the deadline
  again at the moment it commits, so it either issues a valid reservation or refuses an expired one.
- **A reader reserving the last copy while a librarian lends it to someone else**: exactly one of the
  two succeeds, and the other is told that no copy is available.
- **One reader sending several reservation requests at once**: the limit holds under simultaneous
  requests, so the reader never ends up with more than 3 active reservations.
- **A loan that becomes overdue while its reader holds a reservation**: the reservation stays active
  until its deadline, but it can be issued only after the overdue book is returned. If that does not
  happen within the 48 hours, the reservation expires. The reader and the librarian both see why.
- **Overdue at the boundary**: a loan is overdue from the moment its due date passes without a return.
- **Corrections to existing loans**: when a librarian reopens a return recorded by mistake or moves a
  loan to the right reader or book, that is a correction, not a new loan, so the overdue block does
  not apply. The availability rule still does.
- **A librarian lowering a book's total copies below its active loans and reservations**: the change
  is allowed, for example when copies are lost. Existing loans and reservations stay valid, the
  available count shows zero and never a negative number, new reservations and loans are refused until
  a copy is available again, and the librarian is warned.
- **Deleting a book or an account with reservation history**: a book with reservation or loan history
  cannot be deleted. When an account is deleted, its active reservations stop holding copies, and the
  audit entries about it stay readable.
- **The event broker is down**: reservations, issuing, cancellations and audit entries keep working.
  Only analytics events may be lost, and the loss is logged, as the constitution allows.
- **A backup that runs while people are using the site**: it is consistent at a single point in time.
- **The disk fills up**: the backup fails visibly, earlier backups are kept, the site keeps serving,
  and log rotation stops the logs from making things worse.
- **Restoring a backup into a newer release**: the restored database is migrated automatically when
  the application starts. Restoring into an older release than the one that made the backup is not
  supported, and the guide says so. Book vectors from another embedding model are re-encoded on
  startup, as they are today.
- **User input inside an error message**: the rules that keep secrets and search text out of the logs
  also apply to error messages and tracebacks.
- **An audit entry that cannot be written**: the business change rolls back with it, so a change
  without an audit entry never commits.
- **Charts on the analytics dashboard**: each chart has a text or table equivalent, so the dashboard
  meets the same accessibility level as the other main pages.
- **The old free hosting**: if any of its services still runs, the operator shuts it down as the
  operator guide describes, and the register records that no copy of the data remains there.
- **Code-scanning alerts that existed before this feature**: only alerts newly raised by a pull
  request block it. Existing alerts are triaged and listed in the register.
- **Code that the coverage target cannot reach** (glue such as startup commands): the pull request
  lists the uncovered lines and the reason.
- **Demo data**: seeding stays off by default on the server, its accounts stay documented as public
  demo accounts, and seeded loans stay valid after issuing moves to librarians.

## Requirements *(mandatory)*

### Functional Requirements

**Access control (KAN-24, secure configuration)**

- **FR-001**: Self-registration MUST always create a reader account. The sign-up page MUST NOT offer a
  role or an account status, and the server MUST ignore or refuse either one if a request sends it.
- **FR-002**: Only a librarian MUST be able to activate or deactivate an account, and, until the
  administrator role ships (FR-063), to grant or remove the librarian role, through the web, the API
  and the admin site. A reader MAY change only their own name fields. Any attempt by someone who is not
  allowed to change a role or an account status MUST be refused without changing anything.
- **FR-003**: Every operation of the API MUST declare its audience, and an operation that does not
  MUST be refused to every caller, so that the project fails closed. The audiences MUST be:
  - anonymous: the sign-in and registration pages of the web, the version check, and the API
    documentation, schema and index;
  - signed-in reader: reading books, authors and search results; reading their own account and
    changing its name fields; reading their own loans; from Stories 2 and 3, creating, reading and
    cancelling their own reservations; and sending their own activity events;
  - librarian: every operation, except granting or removing the librarian role once the
    administrator role ships;
  - administrator (from FR-063): every operation.

  Until the stage that moves issuing to librarians ships (KAN-57), a reader MAY also start a loan for
  themselves through the API, as the web allows today.
- **FR-004**: A refused request MUST say whether signing in is required or the action is not
  permitted. It MUST return no data from the protected record, and a caller who may not read a record
  MUST get the same response whether or not the record exists.
- **FR-005**: The published API schema MUST state the audience of every operation and describe its
  refusal responses.
- **FR-006**: CI's endpoint checks and the Raspberry Pi measurement procedure MUST keep working under
  the new rules, through an allowed identity or a route that needs no API access, without weakening
  any rule.
- **FR-007**: Once the change is deployed, the operator MUST review every librarian account on the
  server, remove the role from or deactivate every account that is not an authorized librarian, and
  record the date, the number of accounts reviewed and the changes made, for the debt register.
- **FR-063**: A later pull request of this feature MUST add the administrator role that LR2 requires.
  From then on only an administrator MUST be able to grant or remove the librarian role, through the
  web, the API and the admin site. Removing the role MUST keep the account. An administrator MUST
  also have every right of a librarian, the operator MUST be able to create the first administrator
  on the server, and every grant or removal MUST stay an audited critical change (FR-037).

**Reservations (KAN-55 to KAN-58)**

- **FR-008**: A reservation MUST hold one unit of a book's stock, not a particular physical copy. The
  ADR delivered with the reservation model MUST record this choice, the rejected alternative of
  tracking physical copies, how active loans and active reservations reduce availability, and the
  allowed changes of state.
- **FR-009**: Availability MUST be the total number of copies minus active loans minus active,
  unexpired reservations, and never less than zero. It MUST be computed by one implementation that
  the catalog, the book page, search results, the API, the admin site and every loan and reservation
  check all use.
- **FR-010**: A signed-in reader MUST be able to reserve a book with at least one available copy,
  through the web and the API. The reservation MUST be active immediately, without a librarian's
  approval, and MUST expire exactly 48 hours after its creation.
- **FR-011**: A reservation MUST be created in one atomic step that rechecks availability while no
  other loan or reservation of the same book can change it, so that simultaneous requests can never
  hold or lend more copies than exist. When no copy is available, no reservation MUST be created, and
  the reader MUST be told so.
- **FR-012**: A reader MUST NOT hold two active reservations of the same book, nor reserve a book they
  currently have on loan, nor hold more than 3 active reservations at once, even when several of
  their requests arrive at the same moment. A reader with an overdue loan, one not returned by its due
  date, MUST NOT be able to reserve a book or be issued one, from a reservation or directly, until the
  overdue book is returned. These are the refusal rules that KAN-57 requires to be agreed, and they
  MUST have one implementation that the web, the API and the admin site all use.
- **FR-013**: An expired reservation MUST stop reducing availability at its deadline, in every
  availability check, whether or not any background cleanup has run. It MUST be shown as expired and
  MUST NOT be issued.
- **FR-014**: A reservation MUST be in one of four states: active, issued, cancelled or expired. The
  only allowed changes MUST be active to issued (by a librarian, before the deadline), active to
  cancelled (by a librarian with a reason, or by the reader who owns it) and active to expired (at the
  deadline). Issued, cancelled and expired MUST be final.
- **FR-015**: Only a librarian MUST be able to start a loan, through the web, the API and the admin
  site. Issuing a reservation MUST happen in one atomic step that checks that the reservation is
  active, unexpired and the reader's, marks it issued and starts the loan. Repeating the request MUST
  NOT start a second loan.
- **FR-016**: A librarian MUST also be able to lend a book to a reader who has no reservation, under
  the same availability rule (FR-009), so that a reservation on the last copy blocks such a loan.
- **FR-017**: A librarian who cancels a reservation early MUST give a reason of 1 to 500 characters.
  The cancellation MUST release the copy at once and record who cancelled, when and why. The reader
  MUST see the cancellation, its time and its reason the next time they open the site.
- **FR-018**: The reader who owns an active reservation MUST be able to cancel it without giving a
  reason. Nobody other than that reader or a librarian MUST be able to cancel it.
- **FR-019**: A reader MUST be able to see their reservations with the state, the creation time, the
  deadline and the next step of each. A librarian MUST be able to see every active reservation, ordered
  by deadline, with the reader, the book and the time left, and to issue or cancel it from there.
- **FR-020**: Every refusal MUST say what happened and what the person can do next. Refusals include:
  no copy is available, the book is already reserved or on loan by this reader, the reader already
  holds 3 active reservations, the reader has an overdue loan (naming the book and its due date), the
  deadline has passed, the reservation was already issued, and the action is not permitted.
- **FR-021**: Reservation operations MUST be offered through the versioned REST API and described in
  its published schema with their audiences and refusal responses. The README and the feature
  documentation MUST describe the reservation journey from both sides of the desk.
- **FR-022**: Adding reservations MUST NOT change any existing book or loan, and the schema change
  MUST apply to the existing data without losing any of it.
- **FR-023**: The activity analytics MUST keep working. A loan that a librarian starts MUST count as
  the reader's borrow, with the librarian recorded as the person who issued it, and the "borrow
  intent" signal MUST follow the reader's new reserve action. Reservations MUST keep working while
  the event broker is unavailable.
- **FR-024**: A book with reservation history MUST NOT be deletable, just as a book with loan history
  cannot be deleted today.

**Data safety and hosting (KAN-62)**

- **FR-025**: The server's database MUST be backed up automatically at least once a day. Each backup
  MUST be complete, holding every account, role, author, book, book vector, loan, reservation, audit
  entry and analytics event; consistent at a single point in time; and checked to be readable right
  after it is made.
- **FR-026**: Backups MUST be kept on the server for at least 7 days, in storage separate from the
  database's own, so that removing or recreating the database's storage leaves them intact. Backups
  older than the retention period MUST be removed automatically. The operator guide MUST add a weekly
  step that copies the newest backup to another machine and checks that the copy is readable there.
- **FR-027**: A failed backup MUST be visible to the operator in the logs, with its cause, and MUST NOT
  remove earlier backups.
- **FR-028**: Backups and the operator's copies of them MUST be readable only by the operator and MUST
  NOT be stored in the repository or the image. The operator guide MUST say that they contain password
  hashes and personal data.
- **FR-029**: The operator guide MUST give step-by-step instructions to restore a backup into a
  separate database without touching the live one, followed by checks that the restored copy matches:
  record counts, a librarian sign-in and a search. The restore MUST be rehearsed on the Raspberry Pi
  before KAN-62 closes, and the date, the backup's size, the restore's duration and the results MUST
  be recorded.
- **FR-030**: Data persistence MUST be verified on the Raspberry Pi: the record counts before and after
  a restart of each service, a redeploy of the stack and a reboot of the Pi MUST match, and the time
  until the site served pages again MUST be recorded for each.
- **FR-031**: The hosting limits that apply now MUST be measured and recorded: the memory budget, the
  disk space used by data, backups and logs, and the remaining headroom. It MUST also be confirmed and
  recorded that the old free hosting no longer serves the site or keeps a copy of its data.
- **FR-032**: It MUST be recorded that the product stores no uploaded files, together with the rule
  that any future upload feature keeps its files on persistent storage that the backups cover.
- **FR-033**: With the backup job and every other process this feature adds running, the whole stack
  MUST stay within the 4 GB memory budget on the Raspberry Pi, measured and recorded as Principle VI
  requires.

**Technical logs and audit (KAN-62)**

- **FR-034**: The web and worker services MUST write technical log lines in one consistent format
  that includes the time, the level, the service and a request identifier. The identifier MUST be
  carried into the background work that a request starts, so that an operator can find every line of
  one request in one place.
- **FR-035**: Technical logs MUST record at least: unhandled errors with their traceback, refused
  access attempts, failed sign-ins, failures and retries of background work, broker outages,
  embedding failures, the startup steps and the result of every backup.
- **FR-036**: Logs MUST be rotated so that they never use more than 500 MB of disk in total on the
  server. The log level MUST be configurable and MUST default to INFO.
- **FR-037**: Every critical change MUST create an audit entry that is written together with the
  change and only if the change commits. Critical changes are: a role granted or removed; an account
  activated, deactivated or deleted; a loan started, returned, reopened, reassigned or deleted; a
  reservation created, issued, cancelled or expired; a book's total copies changed; and a book
  deleted. Each entry MUST record the actor (or the system), the action, the affected record, the
  time, the values before and after, the reason where one is required, and the channel: web, API,
  admin site or command.
- **FR-038**: Audit entries MUST NOT be editable or deletable through the application, MUST stay
  readable after the related account or book is deleted, and MUST be readable only by librarians.
- **FR-039**: No technical log line or audit entry MUST contain a password or password hash, a secret
  or key, a token, a session or CSRF identifier, a database connection address with its password, or
  the text of a person's search.
- **FR-040**: If the audit entry for a change cannot be written, the change MUST roll back.

**Accessibility and clarity (KAN-62, KAN-58)**

- **FR-041**: The main pages MUST meet WCAG 2.2 level AA. For everyone they are the sign-in and
  registration pages, the catalog with search and the author filter, the book page, and the reader's
  loans, reservations and profile. For librarians they also include the reservation list, the loan
  list with editing and returns, the user list and editing, creating and editing books and authors,
  and the analytics dashboard.
- **FR-042**: Each main task (Story 6) MUST be possible with a keyboard alone and with a screen reader.
  Automated accessibility checks of the main pages MUST run in CI and report no level A or AA
  violation.
- **FR-043**: Labels, messages and confirmations MUST use plain language and say what happened and
  what to do next. Actions that cannot be undone MUST ask for confirmation, and a form with errors
  MUST keep the values the person entered.
- **FR-044**: Every date and time shown to people MUST be in the library's local time zone, and the
  page MUST say which zone it is.
- **FR-045**: Before KAN-62 closes, a task walkthrough MUST be run with at least three people who are
  new to the system, at least one of them with little digital experience. The results and every
  problem found MUST be recorded, and each problem MUST be fixed or recorded for the debt register
  with an owner and a plan.

**Catalog query counts (KAN-18)**

- **FR-046**: Every page and API list that shows books, authors, loans, reservations or accounts MUST
  use a number of database queries that does not depend on the number of rows it shows. The author
  list of the API MUST stop reading each author's books with a separate query.
- **FR-047**: Tests MUST fix these query counts, so that a change that adds a query per row fails CI.
- **FR-048**: The query count of each list and the catalog response times on the Raspberry Pi MUST be
  measured and recorded, with the method and the date.

**Tests and merge rules (KAN-21, KAN-22, KAN-15)**

- **FR-049**: Unit and integration tests MUST cover creating, editing and deleting books and authors
  through the web, the API and the admin site, their validation limits, availability, every change of
  state of a loan and of a reservation, and the audience of each action, with at least one permitted
  and one refused caller for every protected route (Principle II).
- **FR-050**: Concurrency tests on the database that CI uses MUST show that two loans of the last
  copy, two reservations of it, or a reservation and a loan of it never both succeed.
- **FR-051**: CI MUST measure the coverage of the book, author, loan and reservation code on every
  pull request and show it on the pull request. At least 85% of the lines that this feature adds or
  changes MUST be covered, and every exception MUST be listed with its reason in its pull request.
- **FR-052**: A merge into `main` MUST require the lint and format check, the full smoke test on every
  runner and code scanning to pass, and an approval from a code owner of every path the pull request
  touches. The three requirements missing today are repository settings, not file changes: Arsen, the
  repository administrator, MUST apply them through the Jira sub-tasks KAN-72 of KAN-22 (the lint
  check), KAN-73 of KAN-15 (code scanning) and KAN-74 of KAN-13 (code-owner review), and each applied
  setting MUST be recorded as evidence.
- **FR-053**: When a new test reveals a defect in existing behavior, the fix MUST ship in the same pull
  request if it is small. Otherwise a bug report MUST be filed with the repository's bug report
  template, and the defect MUST be recorded for the debt register.

**Debt register and documentation (KAN-62)**

- **FR-054**: The repository's documentation MUST hold a debt register that lists every priority item
  from LR1 and LR2 and every gap this feature finds. Each item MUST have an identifier, a description,
  a source, a priority (P1, P2 or P3), an owner and a status (closed, open, blocked or accepted). A
  closed item MUST link its evidence: a pull request, a CI run, a test, a measurement or a restore
  record. An open item MUST give a plan with a target sprint, and a blocked item its blocker.
- **FR-055**: The register MUST also list the gaps that this feature finds but does not fix, with an
  owner and a plan for each. Known so far: backups leave the Pi only through the operator's weekly
  copy, so losing the Pi can cost up to a week of data, and an automatic off-device copy is the
  follow-up for when the site holds real readers' data; analytics search events keep the text of each
  search; the interface is in English only; the browser tests under `library/` do not run in CI; and
  P2 search and demand forecasting are out of scope.
- **FR-056**: KAN-62 MUST NOT move to Done while any P1 item in the register is open or blocked.
- **FR-057**: Each pull request MUST update the README, the operator guide and `.env.example` wherever
  it changes behavior, setup or configuration. The reservation ADR MUST ship with the reservation
  model, and each pull request MUST add one changelog entry.
- **FR-058**: The descriptions of KAN-18 and KAN-19 in Jira MUST be corrected to match the delivered
  behavior, and KAN-62 MUST link the register and the evidence. The assignee MUST update the status
  of each issue as its pull request opens and merges.

**Delivery**

- **FR-059**: Every issue named in KAN-62 that needs a change to the repository's files MUST ship as
  its own pull request. A change that is only a repository setting MUST be applied through a Jira
  sub-task instead (FR-052), and an issue whose work is already complete MUST ship nothing and be
  closed with its evidence. KAN-62's own
  work is split into five Jira sub-tasks of KAN-62, KAN-67 to KAN-71: technical logs and audit,
  backups and restore, accessibility and clarity, the administrator role, and the debt register.
  Each sub-task ships as its own pull request:

  | Pull request | Issue | Contents | Comes after |
  |---|---|---|---|
  | 1 | KAN-24 (secure configuration) | Story 1, FR-001 to FR-007 | none; merged first |
  | 2 | KAN-18 | Story 7, FR-046 to FR-048 | none |
  | 3 | KAN-21 | Story 8 tests for the existing code, FR-049 to FR-051, FR-053 | 1 |
  | 4 | KAN-55 | Reservation model, states and ADR: FR-008, FR-014, FR-022, FR-024 | 1 |
  | 5 | KAN-56 | Story 2: FR-009 to FR-013 and the borrow-intent part of FR-023, with the reader's reserve action on the web and in the API | 4 |
  | 6 | KAN-57 | Story 3: FR-015 to FR-018 and the rest of FR-023 | 5 |
  | 7 | KAN-58 | The complete reservation pages and messages, FR-019 to FR-021, keyboard access, end-to-end tests and recorded acceptance results | 6 |
  | 8 | KAN-67 (KAN-62): technical logs and audit | Story 5, FR-034 to FR-040 | 1 |
  | 9 | KAN-68 (KAN-62): backups and restore | Story 4, FR-025 to FR-033 | none |
  | 10 | KAN-69 (KAN-62): accessibility and clarity | Story 6, FR-041 to FR-045 | 7 |
  | 11 | KAN-70 (KAN-62): administrator role | FR-063 | 1 |
  | 12 | KAN-71 (KAN-62): debt register | Story 9, FR-054 to FR-058, and the closing evidence | all others |
  | none | KAN-72 (KAN-22), KAN-73 (KAN-15), KAN-74 (KAN-13), assigned to Arsen | The lint, code-scanning and code-owner merge requirements, applied as repository settings (FR-052) | none |
  | none | KAN-17, KAN-19 | Evidence in the register | none |

  Each reservation stage MUST meet FR-020 and FR-021 for the actions it adds, so every operation
  appears in the API schema from the stage that adds it (Principle I); pull request 7 completes the
  pages, messages and documentation. The audit pull request (8) MUST cover every reservation change
  of state that exists when it merges, and a reservation stage that merges after it MUST add audit
  entries for its own changes of state; the administrator-role pull request (11) does the same for
  role changes. Measurements, restore records and other evidence produced by pull requests 1 to 11 and
  by the repository settings are collected into the debt register by pull request 12. The title of
  each pull request names its Jira key, and the access-control pull request names KAN-24 and KAN-62.
- **FR-060**: The access-control pull request MUST be the first of this feature to merge, as soon as
  review allows. Until it is deployed to the server, this spec and every other description of the gap
  MUST stay out of the public repository, apart from what that pull request itself has to show.
- **FR-061**: Each reservation stage MUST leave the site usable on its own: after every merge, readers
  can still get books through the web, by lending to themselves until KAN-57 ships and by reserving
  from then on, and librarians can still lend and take back books.
- **FR-062**: Each pull request MUST contain only its own part, pass every CI gate on its own, follow
  the pull request template and the `<action>(<service>): <description>` title convention, add one
  changelog entry, and be reviewed by the code owners of the paths it touches. Each pull request MUST
  get its own branch, created from a freshly fetched `origin/main`, or from the previous stage's
  branch when it depends on one that has not merged yet, as the fresh-feature-branch skill describes.

### Key Entities *(include if feature involves data)*

- **Reservation**: a reader's 48-hour hold on one unit of a book's stock. It records the reader, the
  book, the creation time, the deadline (creation time plus 48 hours), the state (active, issued,
  cancelled or expired), the loan it became when issued, and, when cancelled, who cancelled it, when
  and why.
- **Loan** (called an "order" in the product today): a book lent to a reader, with the start, the due
  date and the return date. From this feature on, only a librarian starts one, either from a
  reservation or directly. A loan is overdue once its due date has passed without a return.
- **Book stock**: the total number of copies of a book. The available number is derived (FR-009) and
  never stored.
- **Role**: each account has exactly one: reader, librarian, or, from FR-063, administrator, which
  has every librarian right and is the only role that can grant or remove the librarian role.
- **Audit entry**: an unchangeable record of one critical change, with the actor or the system, the
  action, the affected record, the time, the values before and after, the reason where required and
  the channel.
- **Backup**: a complete, point-in-time copy of the database with its creation time, its size and the
  result of its check, kept for the retention period.
- **Restore record**: the date, the backup used, the duration and the results of a rehearsed restore.
- **Debt item**: an entry in the debt register, with its identifier, description, source, priority,
  owner, status, and its evidence, plan or blocker.
- **Technical log line**: the time, level, service, request identifier and message of one event,
  never holding secrets or search text.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0 operations let an anonymous caller read personal data or change anything, and 0 paths
  let someone who is not a librarian obtain the librarian role, as shown by tests that cover every
  operation of the API and every form that can change a role.
- **SC-002**: With one available copy and 100 simultaneous attempts to reserve it, exactly 1 succeeds,
  in each of 20 repeated runs; the same holds for two simultaneous loans and for a loan racing a
  reservation, and a reader who sends simultaneous requests never ends up with more than 3 active
  reservations.
- **SC-003**: On the Raspberry Pi, 95% of reserve, issue and cancel operations complete within 3
  seconds while 30 readers reserve at the same time, and a burst of 100 simultaneous reservations
  never holds more copies than exist.
- **SC-004**: The first availability check at or after a reservation's deadline shows the copy as
  available, with no background job running.
- **SC-005**: After a restart of each service, a redeploy of the stack and a reboot of the Pi, the
  number of records of every kind matches exactly, and the site serves pages again within 3 minutes of
  each, when no change of embedding model is pending.
- **SC-006**: The newest backup on a healthy server is never older than 24 hours and the newest copy on
  another machine never older than 7 days, so at most one day of data is lost while the Pi's storage
  survives and at most a week if it does not. A rehearsed restore of the latest backup completes
  within 60 minutes and matches 100% of the record counts.
- **SC-007**: 100% of the critical change types listed in FR-037 create an audit entry, and a search of
  every log line and audit entry produced by the full test suite and the smoke test finds 0 passwords,
  secrets, tokens or search texts.
- **SC-008**: An operator finds every log line of a failing request, from both web and worker, with
  one search for its request identifier.
- **SC-009**: The automated checks report 0 WCAG 2.2 level A or AA violations on the main pages, every
  main task is completed with a keyboard alone and with a screen reader, and at least 80% of the
  walkthrough attempts by people new to the system finish without help.
- **SC-010**: Every page and API list in scope uses the same number of database queries with 1 row and
  with 50 rows, and 95% of catalog page loads on the Raspberry Pi complete within 2 seconds.
- **SC-011**: At least 85% of the lines this feature adds or changes are covered by tests, and the
  author app has tests.
- **SC-012**: A pull request into `main` whose lint check, smoke test or code scanning fails, or that
  lacks a code owner's approval, cannot be merged; each of the four rules is demonstrated once and
  recorded.
- **SC-013**: 100% of the items named in KAN-62 link to evidence or to a blocker in the register,
  100% of the open items have an owner, a priority and a plan, and 0 P1 items are open when KAN-62
  moves to Done.
- **SC-014**: With everything this feature adds running, the whole stack stays within 4 GB of memory on
  the Raspberry Pi and 95% of searches still answer within 500 ms.

## Assumptions

- KAN-62 had no Jira sub-tasks when this spec was written. Each "sub-KAN" in the request is an issue
  that KAN-62 names, and each one that still needs a change gets its own pull request. KAN-62's own
  work gets five new sub-tasks with one pull request each (FR-059).
- KAN-17 was completed by feature 002 (pull requests #30 to #32 and #34) and needs evidence only. The
  code for KAN-19 is complete, and only its Jira description is out of date. KAN-15, KAN-22 and KAN-24
  are complete as written. Their remaining parts here belong to them because KAN-62 groups the items
  that way: the merge requirements, which Arsen applies as repository settings through sub-tasks of
  KAN-15 and KAN-22 (and of KAN-13 for code-owner review), and the access-control gap.
- The access-control gap is attributed to KAN-24 because KAN-62 lists "a secure configuration" under
  it and LR1 includes access control in the security requirement. Its pull request names both KAN-24
  and KAN-62.
- The reservation rules are the ones agreed in LR2 and written into KAN-55 to KAN-57: a reservation
  is active immediately without a librarian's approval, lasts 48 hours, only librarians issue, and an
  early cancellation by the library needs a reason. They replace the earlier draft (US-06) in which a
  librarian had to approve each request.
- A reservation holds a unit of stock rather than a physical copy (FR-008), because the product tracks
  only a count per book and no copy records, as the LR2 feasibility review notes. This supersedes the
  BA draft's FR-06, which spoke of holding a specific copy.
- A reader may cancel their own reservation, as KAN-57 implies when it forbids cancelling "another
  reader's" reservation.
- The reason for a cancellation is shown to the reader, so librarians write reasons that the reader
  can read.
- Readers are informed inside the application. Email or text messages would need an external service,
  and they are out of scope.
- The library's local time zone is Europe/Kyiv. Times are stored as they are today and only shown in
  local time.
- The loan period that a librarian chooses keeps today's limits: 14 days by default, 1 to 30 days.
- The overdue block has no librarian override, as agreed: the reader returns the overdue book first.
  A librarian's correction of an existing loan is not a new loan, so the block does not apply to it.
- The "librarian or administrator" who may cancel a reservation early in KAN-57 is any librarian;
  once the administrator role exists (FR-063), administrators can too, because they have every
  librarian right.
- "Centralized" logs means that all services write one consistent stream that the operator can read and
  search in one place on the Raspberry Pi. No separate log collection service is added, which keeps
  the stack within its memory budget.
- An audit entry is part of the business record: it is saved together with the change it describes,
  so both are kept or neither is. It is not an analytics event, which may be lost.
- The analytics search events from KAN-30 keep the search text by design. They are analytics, not
  technical logs, so this feature leaves them unchanged and the register asks the business analyst to
  decide whether they should keep it.
- The interface stays in English. Ukrainian translation is recorded in the register for later.
- The accessibility level, WCAG 2.2 AA, comes from the LR2 requirements. The walkthrough participants
  may be volunteers from outside the team, and only anonymous results are kept.
- The accessibility checks and the coverage measurement are CI tools. They add no runtime dependency
  and no frontend build step. Any new runtime dependency, service or process that the plan proposes,
  for example for backups, is justified in its Complexity Tracking table (Principle VI).
- The server holds the seeded demo data and possibly a few accounts that people registered on the
  public site.
- P2 search work, recommendations, the AI assistant, ratings and demand forecasting are out of scope.
- At the assignee's request, the sub-tasks KAN-67 to KAN-71 of KAN-62 (assigned to the KAN-62
  assignee) and KAN-72, KAN-73 and KAN-74 of KAN-22, KAN-15 and KAN-13 (assigned to Arsen) were
  created on 2026-10-27. Every other Jira change is made by the assignee, or at their explicit request.
- Owners in the debt register start from the owner roles in the team's risk register: the senior
  engineer for the race condition (R2), the QA lead for test coverage (R3), and the product owner with
  the tech lead for data loss (R7). Each owner is named as a person.
