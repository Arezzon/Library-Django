# Feature Specification: Technical Lead's Debt Fixes (KAN-90)

**Feature Branch**: `005-tech-debt-fixes` (spec directory; no git branch was created)

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: "Complete all my tasks from Jira Epic KAN-90 that have To Do Status (https://arsensworkspace-47040086.atlassian.net/browse/KAN-90), every task should go in separate PR (except releated like: KAN-79 + KAN-80 should be in one PR, KAN-96 + KAN-97 also can be in one PR, KAN-101 + KAN-102 also can be in single PR), flow is like that: Move task on which you currently working to In Progress -> implement and open PR -> place task In Review."

## Clarifications

### Session 2026-11-04

- Q: KAN-80 (TD-37) is a decision issue that @Arezzon decides. What does group A's pull request do for
  it? → A: Hide the pages. On 2026-11-04 the technical lead reported that @Arezzon has already
  approved option 1 of the KAN-80 comment: readers get "not found" on librarian and administrator
  pages, and the API keeps "forbidden".
- Q: KAN-94 (TD-20): run the two browser test files in CI, or delete them? → A: Run both in CI. They
  stay, run without a display against the stack CI starts, and are updated for group C's sign-out
  button.
- Q: Should the constitution's list of CI gates name group B's new browser sign-in step? → A: Yes, in
  group D's amendment. It becomes a MINOR amendment (2.4.1 to 2.5.0) instead of the PATCH that KAN-101
  describes, because it adds a gate to the list. Group D therefore merges after group B.

## User Scenarios & Testing *(mandatory)*

[Epic KAN-90](https://arsensworkspace-47040086.atlassian.net/browse/KAN-90) holds one Jira issue for
each of the 16 open items of the [technical debt register](../../docs/shared/debt-register.md). On
2026-11-04, seven of them are assigned to the technical lead, @fazelukario, and have the status
**To Do**:

| Issue | Register item | Kind | What is wrong |
| ----- | ------------- | ---- | ------------- |
| KAN-79 | TD-36 | change | An unknown address shows a plain "Not Found" page with no site navigation |
| KAN-80 | TD-37 | decision | Librarian and administrator pages answer a reader "forbidden", which confirms that they exist |
| KAN-94 | TD-20 | change | The two browser sign-in test files under `library/` never run in CI |
| KAN-96 | TD-22 | change | Merely visiting the sign-out address signs the user out |
| KAN-97 | TD-23 | change | The admin site's user form shows the password hash as an editable field, and a changed value becomes the new password |
| KAN-101 | TD-31 | change | The constitution and `AGENTS.md` give the test command without `ai`, which CI runs |
| KAN-102 | TD-35 | change | A page missing from the hand-kept access-test list fails no test |

This feature delivers them as four pull requests, one per group:

| Group | Issues | Why together |
| ----- | ------ | ------------ |
| A | KAN-79 + KAN-80 | Hiding staff pages from readers answers them with KAN-79's "not found" page |
| B | KAN-94 | Stands alone |
| C | KAN-96 + KAN-97 | Both close account-safety findings from KAN-62 |
| D | KAN-101 + KAN-102 | Both close gaps in what the tests check |

KAN-94 was assigned to @Dima22820 when the Epic was published on 2026-11-03 and is now assigned to the
technical lead. The request names three pairs and does not name KAN-94, so it gets a pull request of
its own.

### User Story 1 - Each issue shows where its work stands (Priority: P1)

The team follows sprint 5 on the Jira board. While the technical lead's work on a group is under way,
that group's issues show **In Progress**. When its pull request is ready for review, they show
**In Review**, with a comment that links the pull request, as each issue's "Як звітувати" section asks.

**Why this priority**: the request sets this flow, and the Epic's review step starts from issues in
In Review that link their pull request. An issue that sits in To Do while its fix exists gets no
review.

**Independent Test**: during the work, read the statuses and comments of the seven issues. Only the
issues of the group being worked on are In Progress, and every issue whose pull request is ready is in
In Review with a comment that links it.

**Acceptance Scenarios**:

1. **Given** a group whose issues are in To Do, **When** work on that group starts, **Then** each of
   its issues moves to In Progress before any change is made for it.
2. **Given** a group in progress, **When** its pull request is open and its CI checks have passed,
   **Then** each of its issues gets a comment in Ukrainian with the pull request's link and moves to
   In Review.
3. **Given** any of the seven issues, **Then** none is moved to Done and none has its description
   changed.
4. **Given** the other nine issues of KAN-90, which belong to teammates, **Then** none of them is
   moved or edited.

---

### User Story 2 - Signing out happens only on purpose, and the admin form cannot change a password by accident (Priority: P1)

Group C. A signed-in user stays signed in when another page, an image or a link, including one on
another site, points at the sign-out address. An administrator who saves a user's details in the admin
site does not change that user's password.

**Why this priority**: both findings let an action the user did not mean change their account: another
site can sign them out, and a stray edit can replace a password.

**Independent Test**: as a signed-in user, open the sign-out address directly: the session survives.
Press "Log Out": the session ends. In the admin site, edit a user and save without using the
change-password form: the user's old password still works.

**Acceptance Scenarios**:

1. **Given** a signed-in user, **When** they open the sign-out address directly or follow a link to it,
   **Then** they stay signed in and get a "method not allowed" answer.
2. **Given** a signed-in user, **When** they press "Log Out" in the header or in the mobile menu, by
   mouse or keyboard, **Then** they are signed out and taken to the sign-in page, as today.
3. **Given** a sign-out request without the site's forgery-protection token, **When** it arrives,
   **Then** it is refused and the session survives.
4. **Given** an administrator editing a user in the admin site, **When** the form opens, **Then** the
   password is shown read-only, with a link to the change-password form.
5. **Given** that form, **When** the administrator saves it, **Then** the user's password does not
   change.
6. **Given** the change-password form, **When** an administrator sets a new password, **Then** the user
   signs in with the new password.

---

### User Story 3 - Unknown and staff-only addresses answer with the site's own "not found" page (Priority: P2)

Group A. A visitor who opens an address that does not exist sees a page in the site's style, with its
header and navigation, a short explanation and a way back home, instead of a bare server page. A
reader who opens a librarian or administrator page gets the same page, so the site no longer confirms
that the page exists.

**Why this priority**: a page with no navigation strands the visitor, and hiding staff pages, which
@Arezzon approved for KAN-80, answers readers with this page.

**Independent Test**: with debugging off, open an address that does not exist: the answer is "not
found" with the site's own page. Then open a librarian page as a reader: the answer is the same.

**Acceptance Scenarios**:

1. **Given** debugging is off, **When** anyone opens an address that does not exist, **Then** the answer
   is "not found", and the page has the site's header, navigation, a short explanation and a link to
   the home page.
2. **Given** the "not found" page, **When** it is used by keyboard only, **Then** every control can be
   reached and used, and the accessibility check finds no WCAG 2.2 level A or AA violation on it.
3. **Given** a signed-in reader, **When** they open a librarian or administrator page, **Then** they get
   "not found" with the same page as an address that does not exist.
4. **Given** a librarian or an administrator, **When** they open the same page, **Then** it works as
   today.
5. **Given** a visitor who is not signed in, **When** they open a librarian or administrator page,
   **Then** they are sent to sign in, as today.

---

### User Story 4 - The browser sign-in tests protect something, or are gone (Priority: P2)

Group B. Two files under `library/` test signing in and out in a real browser, but CI never runs them,
so they suggest coverage the project does not have. After this feature both run, and pass, on every
pull request.

**Why this priority**: the register rates TD-20 P2, the highest of the seven. A test nobody runs gives
false confidence about the sign-in flow.

**Independent Test**: open the CI run of any pull request after this one merges, and find both browser
sign-in test files among its passed steps.

**Acceptance Scenarios**:

1. **Given** a pull request, **When** CI runs, **Then** both browser sign-in test files run against the
   stack CI starts, and pass.
2. **Given** a change that breaks signing in or out in the browser, **When** CI runs, **Then** the
   browser sign-in tests fail.

---

### User Story 5 - Contributors run the tests CI runs, and a page without an access check fails a test (Priority: P3)

Group D. A contributor who follows the constitution or `AGENTS.md` runs the same Django test command
that CI runs, `ai` included. A developer who adds a page and forgets to list it in the web access tests
gets a failing test.

**Why this priority**: both are gaps in the safety net rather than defects users see. Today the six
unlisted pages do check access, and their own apps test it.

**Independent Test**: compare the command in both documents with CI's. Remove one route from the web
access test list and run the tests: one fails.

**Acceptance Scenarios**:

1. **Given** the constitution and `AGENTS.md`, **When** a contributor reads the test command, **Then**
   it names the same apps as CI, `ai` included.
2. **Given** the constitution change, **Then** its version is raised as a MINOR amendment (2.5.0),
   with the amendment date and a changelog entry, and its list of CI gates names the browser sign-in
   tests.
3. **Given** the web access test list, **When** any web page route is missing from it, **Then** a test
   fails and names the missing route.
4. **Given** the six routes missing on 2026-11-02 (the assistant, For You, Saved Books, a book's rating,
   a book's settings and signing out), **Then** each is in the list, with at least one permitted caller
   and one refused caller.

---

### Edge Cases

- **Browser tests and the sign-out button**: the browser tests find "Log Out" as a link. Group C makes
  it a button. Whichever of groups B and C merges second updates them, so that CI stays green on both.
- **The access list and sign-out**: group D lists the sign-out route. If group C has merged by then,
  the entry checks sign-out the way group C leaves it: only a form submission signs out.
- **Shared test file**: groups A and D both change the web access tests. The pull request that merges
  second is brought up to date with `main`, and its tests pass on the result.
- **Not signed in, sign out**: a visitor who is not signed in and submits the sign-out form lands on the
  sign-in page without an error.
- **New user in the admin site**: creating a user in the admin site still sets their password. The
  read-only rule applies to editing an existing user.
- **Not-found page and visitors**: the page renders for visitors who are not signed in, for readers,
  for librarians and for administrators. Each sees their usual navigation.
- **Debugging on**: in development, with debugging on, the framework's debug page may still appear for
  an unknown address. The requirement and its test apply with debugging off, as in production.
- **Pages a reader may open only for their own records**, for example another reader's order: the
  KAN-80 decision covers librarian and administrator pages only, so these answers do not change.
- **CI fails on an open pull request**: the fix goes into the same pull request, and the group's issues
  stay In Progress until CI passes.
- **An issue changes status or assignee during the work**: if one of the seven issues is no longer
  assigned to the technical lead or no longer in To Do when its group starts, it is not moved. The
  final report names it.

## Requirements *(mandatory)*

### Functional Requirements

**Workflow and delivery**

- **FR-001**: The work MUST cover exactly the seven issues listed above: the KAN-90 issues assigned to
  @fazelukario with the status To Do on 2026-11-04.
- **FR-002**: Each group (A, B, C, D) MUST be delivered as one pull request. No pull request may carry
  issues from two groups.
- **FR-003**: Groups MUST be worked one at a time. When work on a group starts, its issues MUST move from
  To Do to In Progress, and only that group's issues may be In Progress for this work.
- **FR-004**: When a group's pull request is open and its CI checks have passed, each of the group's
  issues MUST get one comment in Ukrainian that links the pull request, and then MUST move to In Review.
- **FR-005**: No issue may be moved to Done, no issue description may be changed, and no issue assigned
  to someone other than @fazelukario may be moved or edited.
- **FR-006**: Each pull request MUST follow the repository's rules: a `<action>(<service>): <description>`
  title, the pull request template with its Definition of Done, an entry in `docs/shared/changelog.md`,
  its issue keys and register IDs in the title or description, and @fazelukario as assignee.
- **FR-007**: Each pull request MUST start from the current `origin/main` and pass every CI check on its
  own. It MUST NOT depend on another group's unmerged pull request. One exception: group D's
  constitution text names group B's CI step, so D's description MUST ask for it to merge after B. D's
  checks do not depend on B.
- **FR-008**: Pull requests MUST NOT be merged as part of this work. The technical lead reviews them,
  updates the register and moves issues to Done, as the Epic describes.
- **FR-009**: Every behavior change MUST come with tests that fail without it and pass with it
  (constitution, principle III). Only group D's documentation change (KAN-101) is exempt.

**Group C: signing out (KAN-96, TD-22) and the admin password (KAN-97, TD-23)**

- **FR-010**: Signing out MUST happen only through a form submission that carries the site's
  forgery-protection token. Opening the sign-out address directly MUST NOT end the session, and MUST
  answer "method not allowed".
- **FR-011**: Both "Log Out" controls, in the header and in the mobile menu, MUST keep their look, MUST
  work by mouse and keyboard, and MUST keep the accessibility check at zero WCAG 2.2 A or AA violations.
- **FR-012**: The admin site's form for an existing user MUST show the password read-only, with a link to
  the change-password form. Saving that form MUST NOT change the password. Changing a password through
  the change-password form, and setting one when creating a user, MUST keep working.

**Group A: the "not found" page (KAN-79, TD-36) and staff pages (KAN-80, TD-37)**

- **FR-013**: Every web page and web action limited to librarians or administrators MUST answer a
  signed-in reader "not found", with the same page as an address that does not exist. The rule MUST be
  decided in one place for all such pages, not in each page. Librarians and administrators keep their
  access, and API endpoints keep answering "forbidden".
- **FR-013a**: FR-004 of spec 003 MUST be amended in the same pull request to state this exception for
  staff pages. Tests that expect "forbidden" for a reader on these pages MUST change to expect "not
  found".
- **FR-013b**: KAN-80's comment MUST state the decision: option 1 (hide), decided by @Arezzon, with the
  API keeping "forbidden", and link the pull request.
- **FR-014**: With debugging off, an address that does not exist MUST answer "not found" with a page in
  the site's style: header, navigation, a short explanation and a link to the home page, like the
  existing "forbidden" page.
- **FR-015**: The "not found" page MUST be usable by keyboard alone and MUST meet WCAG 2.2 AA. The CI
  accessibility check MUST cover it.
- **FR-016**: A visitor who is not signed in and opens a librarian or administrator page MUST still be
  sent to sign in.

**Group B: browser sign-in tests (KAN-94, TD-20)**

- **FR-017**: After group B, no browser test file in the repository may be left that CI does not run.
- **FR-018**: Browser tests that CI runs MUST run on every pull request and push to `main`, against the
  stack CI already starts and its seeded demo accounts, without a display. They MUST pass in every run
  of the pull request's own CI.
- **FR-019**: Both browser test files MUST stay and run in CI. They MUST take the site's address from
  the environment, defaulting to the one they use today, and MUST find the sign-out control however
  group C leaves it, as a link or as a button. Their two scenarios MUST keep checking what they check
  today: signing in and out with valid details, and the error shown for invalid ones.

**Group D: test command (KAN-101, TD-31) and the access test list (KAN-102, TD-35)**

- **FR-020**: The constitution's quality-gates item 4 and `AGENTS.md` MUST give the same Django test
  command that CI runs, `ai` included.
- **FR-021**: The constitution MUST change only through the project's constitution procedure, as a MINOR
  amendment (2.4.1 to 2.5.0), with the amendment date and a sync report. Besides adding `ai` (FR-020),
  its quality-gates item 4 MUST name the browser sign-in tests on the `ubuntu-latest` leg that group B
  adds.
- **FR-022**: A test MUST enumerate every web page route of the project and fail, naming the route, when
  one is missing from the web access test list. API routes, which have their own guard, the admin site
  and static files are outside it.
- **FR-023**: The six routes missing on 2026-11-02 MUST be added to the list, each with at least one
  permitted caller and one refused caller (constitution, principle II).
- **FR-024**: The pull request MUST record that the new test failed when a route was removed from the
  list, and passed with the full list.

### Key Entities

- **Issue**: one of the seven KAN issues. Attributes: key, register ID, kind (change or decision),
  status, assignee, group.
- **Group**: a set of issues delivered by one pull request (A to D). Attributes: issues, pull request,
  state (waiting, in progress, in review).
- **Pull request**: the GitHub change that closes a group. Attributes: link, title, base, CI result,
  changelog entry, assignee.
- **Register item**: the row in `docs/shared/debt-register.md` that an issue tracks. This feature does
  not change it; the technical lead updates it after review.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All seven issues end in In Review, each with exactly one comment that links its group's pull
  request. None is in Done, and none of the nine teammates' issues changed.
- **SC-002**: Exactly four pull requests are open, one per group, each assigned to @fazelukario, each
  with a changelog entry, and each with every CI check passed.
- **SC-003**: In 100% of tested cases, opening the sign-out address directly leaves a signed-in user
  signed in, and pressing "Log Out" signs them out on the first attempt.
- **SC-004**: Saving an existing user's form in the admin site changes no password, in every tested case.
- **SC-005**: Every tested unknown address answers "not found" with the site's own page, and the
  accessibility check finds 0 violations on it.
- **SC-006**: A signed-in reader who opens a librarian or administrator page gets the same status and
  page as for an unknown address, in every tested case, and a librarian still opens it.
- **SC-007**: Both browser sign-in test files run and pass in every CI run of their pull request, and no
  browser test file is left that CI does not run.
- **SC-008**: Removing any one route from the web access test list makes the test run fail, and on the
  final branch 0 web page routes are missing from it.
- **SC-009**: The test command in the constitution and in `AGENTS.md` matches CI's word for word, and
  the constitution's list of CI gates names every check of the smoke-test job that this feature adds.

## Assumptions

- **Moves are approved by the request**: the request sets the flow To Do, In Progress, In Review for
  the technical lead's own issues. That counts as approval of exactly those moves for these seven issues.
  Any other move, such as to Done or of a teammate's issue, still needs the technical lead's approval.
- **Jira comments**: the comment that links a pull request is short Ukrainian text with the link, as
  each issue's "Як звітувати" asks. It is posted without a separate draft review, because it is neither
  a description nor a new issue. Any longer text is shown to the technical lead first.
- **In Review waits for CI**: an issue moves to In Review only once its pull request's CI has passed,
  because the Epic's review checks that it has.
- **Order**: groups run in the priority order of their user stories: C, A, B, then D.
- **Language**: the site's interface is in English, like the existing "forbidden" page, so the "not
  found" page is in English. TD-19 (KAN-93) decides translation separately.
- **Error page for server faults**: KAN-79 adds a styled page for server errors only "if needed". It is
  out of scope: the "not found" page closes the reported problem.
- **@Arezzon's KAN-80 decision**: the technical lead reported it on 2026-11-04 (see Clarifications).
  The pull request and the KAN-80 comment record it as given; no further approval is asked for.
- **Pages scoped to a record's owner** are outside KAN-80 and keep their answers.
- **Other documents**: `README.md` already gives the command with `ai`. Only the constitution and
  `AGENTS.md` change for KAN-101.
- **Spec location**: like spec 004, this spec, its plan and its tasks stay as files in `specs/`, with no
  git branch of their own. Each group's pull request has its own branch from `origin/main`.
- **Local checks**: Django tests run in the `web` service of `docker-compose-dev.yml`, as CI does. Lint
  runs `ruff check .` and `black --check .` with the versions pinned in `requirements-dev.txt`.
