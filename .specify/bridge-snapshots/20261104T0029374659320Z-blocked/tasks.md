---

description: "Tasks for the technical lead's KAN-90 debt fixes: four pull requests and their Jira flow"
---

# Tasks: Technical Lead's Debt Fixes (KAN-90)

**Input**: Design documents from `specs/005-tech-debt-fixes/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/) and [quickstart.md](quickstart.md)

**Tests**: required. Spec FR-009 and constitution Principle III require tests that fail without each
behavior change. Within each story, tests come first and must be seen failing before the change.

**Organization**: one phase per user story, in priority order. User Story 1 (the Jira flow) runs
through every group, so its move and comment tasks sit inside each group's phase, labelled `[US1]`.

| Story | Group | Issues | PR branch |
| ----- | ----- | ------ | --------- |
| US1 (P1) | all | the seven issues | none |
| US2 (P1) | C | KAN-96, KAN-97 | `fix/kan-96-97-sign-out-and-admin-password` |
| US3 (P2) | A | KAN-79, KAN-80 | `fix/kan-79-80-not-found-page` |
| US4 (P2) | B | KAN-94 | `test/kan-94-browser-sign-in-ci` |
| US5 (P3) | D | KAN-101, KAN-102 | `test/kan-101-102-route-list-and-test-command` |

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story the task serves
- Paths are relative to the repository root. Django code is under `library/`, and management commands
  run there, inside the `web` service.

## Standing rules for every task

- **Django tests**:
  `docker compose -f docker-compose-dev.yml exec -T web python manage.py test <labels>`.
  The full suite is `authentication author book order events audit ai`.
- **Lint**: `ruff check .` and `black --check .` from the repository root, at the versions pinned in
  `requirements-dev.txt`.
- **Never stage** `specs/005-tech-debt-fixes/`, `.specify/bridge-events.jsonl`,
  `.specify/superpowers-handoff.json` or `.specify/bridge-snapshots/`. Run `git status --short` before
  every commit.
- **People**: GitHub handles only, in every file, commit and PR. Jira texts are Ukrainian and follow
  [contracts/jira-reporting.md](contracts/jira-reporting.md).
- **Jira moves**: use transition `31` (In Progress) and `41` (In Review) only. Re-read the issue first.
  If it is not assigned to @fazelukario or is
  not in the source status, skip the move and record why in `specs/005-tech-debt-fixes/progress.md`.
  Never move to Done.
- **One group at a time**: start the next group only once the current group's issues are In Review.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: a running stack, the tools and a clean baseline.

- [x] T001 Make sure Docker is running. If `docker info` fails, start Docker Desktop with `powershell.exe -NoProfile -Command 'Start-Process -FilePath "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"'` and wait for `docker info`. Then run `docker compose -f docker-compose-dev.yml up -d --wait` from the repository root.
- [x] T002 [P] Install the pinned lint tools with `python -m pip install -r requirements-dev.txt`, and confirm `ruff check .` and `black --check .` pass on `main` at `origin/main`.
- [x] T003 [P] Check GitHub access for `.agents/skills/preview-pr/SKILL.md`: `gh auth status` shows `fazelukario`, and `gh repo view --json nameWithOwner` shows `Arezzon/Library-Django`.
- [x] T004 Run the full Django suite on `main` (see Standing rules) and record the result as the baseline in a new running record, `specs/005-tech-debt-fixes/progress.md`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the record and the issue snapshot that every group's Jira steps rely on.

**⚠️ CRITICAL**: no group may start before this phase is complete.

- [x] T005 Add these to `specs/005-tech-debt-fixes/progress.md`:
  - a table with one row per issue: key, TD ID, group, status, PR, CI result, comment ID and moves made. The keys are KAN-79/TD-36/A, KAN-80/TD-37/A, KAN-94/TD-20/B, KAN-96/TD-22/C, KAN-97/TD-23/C, KAN-101/TD-31/D and KAN-102/TD-35/D.
  - an empty "Deviations" section.
- [x] T006 Snapshot all 16 children of KAN-90 with `searchJiraIssuesUsingJql`. Use cloudId `arsensworkspace-47040086.atlassian.net`, JQL `parent = KAN-90 ORDER BY key ASC`, and fields `summary, status, assignee`. Record key, status and assignee in `specs/005-tech-debt-fixes/progress.md`. The end-state check (T087) compares against this, to prove that no teammate's issue changed.
- [x] T007 Confirm with `getJiraIssue` that each of the seven issues is still assigned to @fazelukario and has the status **To Do**. Record any that are not under "Deviations" in `specs/005-tech-debt-fixes/progress.md`; they are skipped in their group.

**Checkpoint**: baseline green, record created, issues confirmed. Groups can start.

---

## Phase 3: User Story 1 - Each issue shows where its work stands (Priority: P1)

**Goal**: the board always shows which of the lead's issues is in progress and which awaits review,
with the PR linked.

**Independent Test**: during the work, only the current group's issues are In Progress. Every issue
whose PR has passed CI is In Review, with one comment that links the PR (spec US1).

- [x] T008 [US1] Run `executeRead` with `listJiraIssueTransitions` for each of the seven issues, and confirm that transition `31` leads to "In Progress" and `41` to "In Review". If an ID differs, record the actual ID in `specs/005-tech-debt-fixes/progress.md` and use it in the tasks below.
- [x] T009 [US1] Copy the comment templates from `specs/005-tech-debt-fixes/contracts/jira-reporting.md` into `specs/005-tech-debt-fixes/progress.md`, one block per issue, leaving `<n>`, `<PR title>` and `<PR url>` to fill in. Check each line against the format rules: one line per paragraph, plain link labels, no gendered past-tense verbs.

The rest of US1 runs inside each group's phase: the In Progress move at its start, and the comment and
In Review move at its end.

---

## Phase 4: User Story 2 - Signing out on purpose, and a safe admin password (Priority: P1) 🎯 MVP

**Goal**: group C (KAN-96, KAN-97). Opening the sign-out link no longer signs anyone out, and the admin
user form cannot change a password.

**Independent Test**: signed in, a GET of `/authentication/logout/` gets 405 and keeps the session; the
"Log Out" button signs out. Saving an admin user form leaves the password unchanged; the password page
changes it (quickstart, Group C).

### Start

- [x] T010 [US1] Move KAN-96 and KAN-97 to **In Progress** (transition `31`), after re-reading each one's assignee and status. Record the moves in `specs/005-tech-debt-fixes/progress.md`.
- [x] T011 [US2] Follow `.agents/skills/fresh-feature-branch/SKILL.md`: `git fetch origin --prune`, then `git switch -c fix/kan-96-97-sign-out-and-admin-password origin/main`. Record the base commit in `specs/005-tech-debt-fixes/progress.md`.
  - Check whether group B's PR has merged: `git log origin/main --oneline --grep "KAN-94"`. If it has, the browser tests must keep passing (T024).

### Tests for User Story 2 (write first; they must fail)

- [x] T012 [P] [US2] In `library/authentication/test_routes.py`, replace `test_signing_out_ends_the_session_and_returns_to_sign_in` (lines 214–230) with three tests:
  - (a) a POST to `/authentication/logout/` by an anonymous caller, a reader and a librarian redirects to `LOGIN`. For the two signed-in callers, a following GET of `/` redirects to `LOGIN`.
  - (b) a GET of `/authentication/logout/` by a signed-in reader gets 405, and a following GET of `/` gets 200, so the session survives.
  - (c) with `Client(enforce_csrf_checks=True)` and `force_login(reader)`, a POST without a token gets 403, and a following GET of `/` gets 200.
- [x] T013 [P] [US2] In `library/authentication/test_templates.py`, add a test that renders `/` for a signed-in reader and checks:
  - exactly two `<form` elements with `method="post"` and `action="/authentication/logout/"`, each holding `csrfmiddlewaretoken` and a `<button type="submit"` whose text is "Log Out";
  - no `href="/authentication/logout/"`.
- [x] T014 [P] [US2] In `library/events/tests.py` (around line 105, in `test_login_and_logout_track_actor_without_credentials`), sign out with `client.post("/authentication/logout/")` instead of `client.get(...)`. Keep the assertion that the payload's `event_type` is `EventType.LOGOUT`.
- [x] T015 [P] [US2] Add admin password tests to `AdministratorRoleTests` in `library/authentication/test_access.py`, using `admin_url(user, page)`:
  - (a) as an administrator, the change page of `self.reader` has no `<input` named `password` and has a link to `../password/`.
  - (b) posting the change form (the existing `change(client, "admin", user, ...)` helper) with `password="edited-hash-value"` gets 302 and leaves `check_password("routes-password")` true. Use the reader's actual seeded password if it differs.
  - (c) a POST to `admin_url(self.reader, "password")` with `password1` and `password2` set to `"admin-set-password-1"` gets 302, and the new password checks. Also send `usable_password: "true"` if Django 5.2's `AdminPasswordChangeForm` renders that field; check with `form.fields`.
  - (d) a librarian's GET of `admin_url(self.administrator, "password")` gets 403.
- [x] T016 [US2] In `library/authentication/test_access.py`, rewrite `test_the_admin_site_sets_passwords_and_a_librarian_adds_readers` (from about line 595) so that it does not rely on the behaviour KAN-97 removes:
  - set the reader's password through `admin_url(self.reader, "password")`, as in T015 (c);
  - post the add page with `email`, `first_name`, `middle_name`, `last_name`, `password1` and `password2` (plus `usable_password: "true"` if the add form has it), and the extra `role: ROLE_LIBRARIAN`;
  - keep the assertions that the added account's role is `ROLE_VISITOR` and that `check_password("admin-added-password-1")` holds.
- [x] T017 [US2] Run `python manage.py test authentication events` in the `web` service. Confirm that T012 (b, c), T013 and T015 (a, b, c) fail on the unchanged code, and record the failing test names in `specs/005-tech-debt-fixes/progress.md`.

### Implementation for User Story 2

- [x] T018 [P] [US2] In `library/authentication/views.py`, decorate `logout` with `@require_POST` from `django.views.decorators.http`. Keep `auth_logout(request)` and `redirect("login")`, and add a one-line docstring saying that signing out takes a POST with a CSRF token (TD-22).
- [x] T019 [P] [US2] In `library/library/templates/base.html`, replace both sign-out links with POST forms, keeping their look and keyboard behaviour:
  - line 172: `<form method="post" action="{% url 'logout' %}" class="inline-flex ml-2">{% csrf_token %}<button type="submit" class="btn-logout">Log Out</button></form>`
  - line 263: `<form method="post" action="{% url 'logout' %}">{% csrf_token %}<button type="submit" class="btn-danger w-full justify-center">Log Out</button></form>`
  - If the button renders differently from the link in a browser, add `cursor-pointer` and `bg-transparent` to `.btn-logout` at line 63.
- [x] T020 [P] [US2] In `library/events/management/commands/smoke_test_tracking.py:164`, sign out with `request("/authentication/logout/", {"csrfmiddlewaretoken": token})`, so that it POSTs with the token it already holds.
- [x] T021 [US2] Rebuild `CustomUserAdmin` in `library/authentication/admin.py` on `django.contrib.auth.admin.UserAdmin` (research R4):
  - Add `CustomUserChangeForm(UserChangeForm)` with `Meta.model = CustomUser` and `fields = ("email", "password", "first_name", "middle_name", "last_name", "role", "is_active")`.
  - Add `CustomUserCreationForm(AdminUserCreationForm)` with `Meta.model = CustomUser` and `fields = ("email", "first_name", "middle_name", "last_name")`.
  - Set `form`, `add_form` and `add_fieldsets`: one wide section with `email`, the three names, `usable_password` if the form has it, `password1` and `password2`.
  - Set `ordering = ("email",)` and `filter_horizontal = ()`.
  - Keep `list_display`, `list_filter`, `search_fields`, `readonly_fields`, `fieldsets`, `get_readonly_fields`, `formfield_for_choice_field`, `has_change_permission` and `has_delete_permission` as they are.
  - In `save_model`, keep the `update_account` path when `change` is true; otherwise call `super().save_model(...)`, because the add form has already hashed the password.
  - Update the class docstring to mention TD-23.
- [x] T022 [US2] Run `python manage.py test authentication events` in the `web` service until it passes, then run the full suite. Fix any other test that signed out by GET; `grep -rn "logout/" library --include=*.py` lists them.
- [x] T023 [US2] Run `python manage.py smoke_test_tracking` in the `web` service with the stack up, and confirm it ends with `PASS`.
- [x] T024 [US2] Only if T011 found group B merged: run the browser tests as in quickstart Group B, and confirm 4 passed. Otherwise write "not applicable" in `specs/005-tech-debt-fixes/progress.md`.
- [x] T025 [US2] Check in a browser, as quickstart Group C describes: header and mobile "Log Out" by mouse and keyboard; a direct GET gets 405; the admin change page is read-only; the password page works. Record the result in `specs/005-tech-debt-fixes/progress.md`.

### Documentation and delivery

- [x] T026 [P] [US2] In `specs/003-priority-tech-debt/contracts/access-control.md`, change the `/authentication/logout/` row of "Web routes" to: "GET: 405 for everyone. POST with a CSRF token: redirect to sign-in (anonymous) / signs out (reader, librarian)". Cite KAN-96.
- [x] T027 [P] [US2] Add the group C entry at the top of `docs/shared/changelog.md`: the date, then `Sign out by form, and a read-only password in the admin site (KAN-96, KAN-97)`, then a description under 200 words.
- [x] T028 [US2] Commit with `.agents/skills/preview-commit/SKILL.md`. Stage only the files T012–T027 changed, after lint and the full suite pass. Message: `fix(authentication): sign out only by form and show the admin password read-only (KAN-96, KAN-97)`.
- [x] T029 [US2] Push and open the PR with `.agents/skills/preview-pr/SKILL.md`:
  - title as in T028, base `main`, assignee @fazelukario;
  - description per `specs/005-tech-debt-fixes/contracts/pull-requests.md` (Group C): link KAN-96/TD-22 and KAN-97/TD-23, give the quickstart commands, and tick only true DoD items.
  - Record the PR number and URL in `specs/005-tech-debt-fixes/progress.md`.
- [x] T030 [US2] Run `gh pr checks <n> --watch`. If a check fails, fix it on the branch, push, and watch again; KAN-96 and KAN-97 stay In Progress. Record the green run in `specs/005-tech-debt-fixes/progress.md`.
- [x] T031 [US1] Post the KAN-96 and KAN-97 comments from `specs/005-tech-debt-fixes/progress.md` with `addOrEditJiraIssueComment` (Markdown), each with the PR filled in and the pair sentence naming the other issue. Then move both to **In Review** (transition `41`). Record the comment IDs and moves.

**Checkpoint**: group C is in review. KAN-96 and KAN-97 show In Review with the PR linked.

---

## Phase 5: User Story 3 - Unknown and staff-only addresses answer with the site's own "not found" page (Priority: P2)

**Goal**: group A (KAN-79, KAN-80). A styled 404 page, which readers also get on librarian-only pages.

**Independent Test**: with `DEBUG=False`, `/no-such-page/` gets 404 with the site's page. A reader on
`/order/reservations/desk/` gets the same page. A librarian gets the desk (quickstart, Group A).

### Start

- [x] T032 [US1] Move KAN-79 and KAN-80 to **In Progress** (transition `31`) after re-reading them, and record the moves.
- [x] T033 [US3] `git fetch origin --prune`, then `git switch -c fix/kan-79-80-not-found-page origin/main`. Record the base commit, and whether group C has merged (`git log origin/main --oneline --grep "KAN-96"`).

### Tests for User Story 3 (write first; they must fail)

- [x] T034 [P] [US3] Create `library/authentication/test_not_found.py`. With a reader, a librarian and an anonymous client, test that:
  - `/no-such-page/` answers 404 using template `404.html`, with the title `Page Not Found | LibrarySys` and a link `href="/"` with the text "Go to the home page";
  - the page does not contain the string `no-such-page`;
  - the anonymous page shows the "Log In" link, the reader's page their email, and the librarian's page the librarian navigation;
  - a reader on `/order/reservations/desk/` gets 404 with `404.html` and the same heading as the unknown address;
  - an anonymous GET of `/order/reservations/desk/` still redirects to `/authentication/login/?next=/order/reservations/desk/`;
  - a librarian gets 200 there.
- [x] T035 [P] [US3] In `library/authentication/test_routes.py`, change the reader column from `FORBIDDEN` to `NOT_FOUND` on every librarian-only row of `ROUTES`:
  - `/book/create/`, `/book/update/{book}/`, `/book/user/{reader}/`
  - both GET and POST rows of `/book/delete/...`
  - all five `/author/...` rows
  - `/order/lend/`, `/order/reservations/desk/`, and the GET and POST rows of `/order/reservations/{reservation}/issue/`
  - `/order/all/`, `/order/update/{loan}/`, and the GET and POST rows of `/order/close/{loan}/`
  - `/authentication/users/`
  - `/events/`, `/events/activity/`, `/events/forecast/`

  Keep `FORBIDDEN` on `/authentication/users/{other}/` and `/authentication/users/{other}/update/`, which are owner-scoped.
- [x] T036 [P] [US3] In `library/authentication/tests.py` (`test_role_required_refuses_other_roles`, around line 430), expect `Http404` instead of `PermissionDenied` for the reader. In `library/authentication/test_access.py:528`, expect 404 for the former librarian on `/order/reservations/desk/`.
- [x] T037 [P] [US3] In `library/author/tests.py:132`, a reader's POSTs to the librarian-only author pages expect 404. Leave line 245, which is API, at 403.
- [x] T038 [P] [US3] Update the book tests:
  - `library/book/tests.py:1198`: a reader's POSTs to `book_update` and `book_delete` expect 404. Leave line 1211 (API) at 403.
  - `library/book/test_delete.py:95`: a reader's POST expects 404. Leave line 126 (CSRF) at 403.
- [x] T039 [P] [US3] Update the events tests to expect 404, renaming tests and updating any assertion on the 403 page's text or template to the 404 page's:
  - `library/events/tests.py:440`: a reader on `/events/activity/`.
  - `library/events/test_forecast_page.py:49`: rename `test_a_reader_gets_the_forbidden_page` to `test_a_reader_gets_the_not_found_page`.
  - `library/events/test_overview_page.py:52`: rename `test_a_reader_gets_the_forbidden_page_without_figures` to `test_a_reader_gets_the_not_found_page_without_figures`.

  Leave `events/tests.py:365-370` and `:567`, and `events/test_overview.py:346` (API and owner) at 403.
- [x] T040 [P] [US3] In `library/order/tests.py`, the borrower's web POSTs at lines 376 (`order_lend`), 472 (`order_close`) and 540 (`order_update`) expect 404. Leave the API assertions at 521, 549, 571 and 595, and `order/test_reservations.py:370` (admin site), at 403.
- [x] T041 [US3] Run the full suite. Confirm that T034–T040 fail on the unchanged code, and that no other test fails. Record the failing names.

### Implementation for User Story 3

- [x] T042 [P] [US3] Create `library/library/templates/404.html` from `library/library/templates/403.html`'s structure:
  - `{% extends 'base.html' %}`, with the title block `Page Not Found | LibrarySys`;
  - the same card, with `<h1>` "We can't find this page." and `<p>` "The address may be mistyped, or the page may have moved. Go back to the home page.";
  - `<a href="{% url 'home' %}" class="btn-primary mt-6">Go to the home page</a>`;
  - no `request_path` or other echo of the address.
- [x] T043 [P] [US3] In `library/authentication/decorators.py`, make `librarian_required` and `role_required` `raise Http404` (from `django.http`) instead of `PermissionDenied` when a signed-in caller lacks the role.
  - Update their docstrings: "answers 404, the same as an unknown address, so readers do not learn that the page exists (KAN-80)".
  - Leave `librarian_or_owner_required` and the anonymous redirect unchanged.
- [x] T044 [US3] In `scripts/a11y/check_pages.mjs`, give `open(page, target, expected = 200)` an optional expected status, and pass it through `visit(page, name, target, expected)`. Then:
  - after the visitor's registration visits (around line 176), add `await visit(visitor, "not found (visitor)", "/no-such-page/", 404)`;
  - after the reader's "assistant" visit (line 221), add `await visit(page, "not found (reader)", "/no-such-page/", 404)` and `await visit(page, "staff page as reader", "/order/reservations/desk/", 404)`.
- [x] T045 [US3] Run the full suite until it passes, then lint.
- [x] T046 [US3] If Node 22 is available, restart the web service with `DEBUG=False docker compose -f docker-compose-dev.yml up -d --wait web` and run the a11y check as in quickstart Group A. Expect 0 violations, including the three new visits. Otherwise record that CI runs it. Restore the usual `DEBUG` afterwards.

### Documentation and delivery

- [x] T047 [P] [US3] In `specs/003-priority-tech-debt/spec.md` (FR-004, line 548), append the exception text from `specs/005-tech-debt-fixes/contracts/web-access.md` (section "Amendment to spec 003, FR-004") word for word.
- [x] T048 [P] [US3] In `specs/003-priority-tech-debt/contracts/access-control.md`:
  - in "Web routes", change the Reader cell `403` to `404 (KAN-80)` on every librarian-only row;
  - in "Refusal responses", change the Web cell of "Signed in, not allowed" to "404 page for librarian-only pages (KAN-80); 403 page for owner-scoped pages".
- [x] T049 [P] [US3] Update the BA documents:
  - `docs/ba/analytics-dashboard.md`: in the table at line 14, the Reader page cell becomes "404, same page as an unknown address (KAN-80)", and API stays 403. At lines 270–275 ("Reader opens `/events/`"), describe the 404 page.
  - `docs/ba/demand-forecast.md`: at line 17 the Reader cell becomes 404. At line 191, change "Readers get 403" to "Readers get the 404 page".
- [x] T050 [P] [US3] In `README.md`, after the API refusal paragraph (around line 452), add one sentence: on the web, a signed-in reader who opens a librarian or administrator page gets the same 404 page as an unknown address, while anonymous visitors are sent to sign in.
- [x] T051 [P] [US3] Add the group A changelog entry at the top of `docs/shared/changelog.md`: `A 404 page in the site's style, and staff pages hidden from readers (KAN-79, KAN-80)`. Say that @Arezzon decided option 1 of KAN-80.
- [x] T052 [US3] Commit with `.agents/skills/preview-commit/SKILL.md`, staging only the files T034–T051 changed. Message: `fix(authentication): answer unknown and staff-only pages with the site's 404 page (KAN-79, KAN-80)`.
- [x] T053 [US3] Push and open the PR with `.agents/skills/preview-pr/SKILL.md`, as `specs/005-tech-debt-fixes/contracts/pull-requests.md` (Group A) describes:
  - link KAN-79/TD-36 and KAN-80/TD-37;
  - state @Arezzon's decision, as the technical lead reported on 2026-11-04;
  - note the code owners of `docs/ba/`;
  - assignee @fazelukario.

  Record the PR in `specs/005-tech-debt-fixes/progress.md`.
- [x] T054 [US3] Run `gh pr checks <n> --watch`, fix any failure on the branch, and record the green run.
- [x] T055 [US1] Post the KAN-79 change comment and the KAN-80 decision comment from `specs/005-tech-debt-fixes/progress.md`, with the PR filled in. Then move both to **In Review** (transition `41`), and record the comment IDs and moves.

**Checkpoint**: group A is in review.

---

## Phase 6: User Story 4 - The browser sign-in tests protect something (Priority: P2)

**Goal**: group B (KAN-94). Both Selenium files run on every PR and pass.

**Independent Test**: the PR's CI run shows the new step passing with 4 tests. Locally, three headless
runs pass (quickstart, Group B).

### Start

- [x] T056 [US1] Move KAN-94 to **In Progress** (transition `31`) after re-reading it, and record the move.
- [x] T057 [US4] `git fetch origin --prune`, then `git switch -c test/kan-94-browser-sign-in-ci origin/main`. Record the base commit, and whether group C has merged.

### Implementation for User Story 4

The change is to the tests themselves. The check is that they run and pass, in CI and three times
locally.

- [x] T058 [P] [US4] Add `pytest==9.1.1` and `selenium==4.51.0` to `requirements-dev.txt`, keeping its alphabetical order. These are the newest releases at least two weeks old on 2026-11-04 (research R7).
- [x] T059 [P] [US4] Update `library/test_selenium_auth_pytest.py`:
  - `BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")`.
  - In the `driver` fixture, build `webdriver.ChromeOptions()`. When `os.environ.get("SELENIUM_HEADLESS") == "1"`, add `--headless=new` and `--window-size=1366,900`, and skip `maximize_window()`; otherwise maximise as today.
  - Add `LOG_OUT = (By.XPATH, "//*[self::a or self::button][normalize-space()='Log Out']")` and use it for the presence wait and the click, so that it works with a link or with group C's button.
  - Keep both scenarios' assertions.
- [x] T060 [P] [US4] Make the same changes in `library/test_selenium_auth_unittest.py`: `BASE_URL` from the environment as the class attribute, the headless options in `setUp`, and the `LOG_OUT` locator.
- [x] T061 [US4] In `.github/workflows/docker-build.yml`, add a step right after "Verify the main pages meet WCAG 2.2 AA" (about line 266), named `Verify the browser sign-in tests`, with `if: matrix.runner == 'ubuntu-latest'`:
  - `env`: `SELENIUM_HEADLESS: "1"` and `BASE_URL: http://localhost:8000`.
  - `run`: `python -m pip install --quiet "$(grep '^pytest==' requirements-dev.txt)" "$(grep '^selenium==' requirements-dev.txt)"`, then `python -m pytest library/test_selenium_auth_pytest.py library/test_selenium_auth_unittest.py -v -p no:cacheprovider`.
  - Do not write to `$RUNNER_TEMP/test-output.txt`.
- [x] T062 [US4] Install the new pins locally (`python -m pip install -r requirements-dev.txt`) and run the browser tests three times against the stack, as quickstart Group B describes. Each run must report 4 passed. Record the runs in `specs/005-tech-debt-fixes/progress.md`. If Chrome cannot run locally, record that and rely on T066.
- [x] T063 [US4] Lint the two test files: `ruff check .` and `black --check .`.

### Documentation and delivery

- [x] T064 [P] [US4] In `README.md`, next to the test commands (around line 506), add a short paragraph on running the browser sign-in tests: start the stack, `python -m pip install -r requirements-dev.txt`, then the pytest command from quickstart Group B, and say that `SELENIUM_HEADLESS=1` hides the browser.
- [x] T065 [P] [US4] Add the group B changelog entry at the top of `docs/shared/changelog.md`: `Browser sign-in tests run in CI (KAN-94)`.
- [x] T066 [US4] Commit with `preview-commit` (message `test(ci): run the browser sign-in tests on every pull request (KAN-94)`), then push and open the PR with `preview-pr`, as `specs/005-tech-debt-fixes/contracts/pull-requests.md` (Group B) describes:
  - path 1 of KAN-94, both files kept;
  - group D's amendment will list the step;
  - code owners @Dima22820 and @Arezzon for the test files;
  - assignee @fazelukario.

  Record the PR.
- [x] T067 [US4] Run `gh pr checks <n> --watch`. Open the `ubuntu-latest` smoke-test log and confirm that "Verify the browser sign-in tests" ran and reported 4 passed. Record it, and fix any failure on the branch.
- [x] T068 [US1] Post the KAN-94 comment, with the PR filled in, then move KAN-94 to **In Review** (transition `41`). Record both.

**Checkpoint**: group B is in review.

---

## Phase 7: User Story 5 - Contributors run CI's tests, and a page without an access row fails a test (Priority: P3)

**Goal**: group D (KAN-101, KAN-102):
- the constitution (2.5.0, MINOR) and `AGENTS.md` give CI's test command;
- the constitution lists the browser sign-in step;
- every web route must be in the access table.

**Independent Test**: the command in both documents matches CI's. Removing one `ROUTES` row fails a
test that names the route (quickstart, Group D).

### Start

- [x] T069 [US1] Move KAN-101 and KAN-102 to **In Progress** (transition `31`) after re-reading them, and record the moves.
- [ ] T070 [US5] `git fetch origin --prune`, then `git switch -c test/kan-101-102-route-list-and-test-command origin/main`. Record the base commit, and which of groups C, A and B have merged (`git log origin/main --oneline --grep "KAN-96\|KAN-79\|KAN-94"`). T074 depends on it.

### Tests for User Story 5 (KAN-102; write first)

- [ ] T071 [US5] In `library/authentication/test_routes.py`, add a module function `web_routes()`, modelled on `api_routes()` in `library/authentication/test_access.py:186`:
  - walk `get_resolver().url_patterns` with `str(pattern.pattern)` prefixes;
  - skip any route that starts with `api/`;
  - collapse every pattern under `admin/` into the single route `admin/`;
  - return a sorted list of route strings, for example `book/<int:book_id>/rating/`.
- [ ] T072 [US5] In `WebRouteAccessTests` (same file):
  - add `missing_routes(self, table)`, which returns the `web_routes()` entries not covered by `{resolve(route.format(**self.ids()).split("?")[0]).route for _, route, *_ in table}`;
  - add `test_every_web_route_is_in_the_table`, which asserts `self.missing_routes(ROUTES) == []`, with a message listing them;
  - add `test_a_route_missing_from_the_table_is_reported`, which removes the `/book/{book}/` row from a copy of `ROUTES` and asserts that `book/<int:book_id>/` is reported.
- [ ] T073 [US5] Run `python manage.py test authentication.test_routes`. Confirm that `test_every_web_route_is_in_the_table` fails and lists exactly the missing patterns: `assistant/`, `assistant/result/`, `book/recommendations/`, `book/preferences/`, `book/<int:book_id>/rating/`, `book/<int:book_id>/preferences/` and `authentication/logout/`. Record the list. Any extra pattern also gets a row in T074.

### Implementation for User Story 5

- [ ] T074 [US5] In `ROUTES` in `library/authentication/test_routes.py`, add one row per missing pattern, with the answers measured on this branch for anonymous, reader and librarian:
  - `("get", "/assistant/", ...)`
  - `("get", "/assistant/result/", ...)`
  - `("get", "/book/recommendations/", ...)`
  - `("get", "/book/preferences/", ...)`
  - `("post", "/book/{book}/rating/", ...)`
  - `("post", "/book/{book}/preferences/", ...)`
  - for sign-out: if group C has merged, `("get", "/authentication/logout/", 405, 405, 405)` and `("post", "/authentication/logout/", LOGIN, LOGIN, LOGIN)`; otherwise `("get", "/authentication/logout/", LOGIN, LOGIN, LOGIN)`, which C's PR updates when it merges second.

  Other changes in the same file:
  - extend `assertOutcome` so that any integer outcome (for example 400 or 405) is compared as a status;
  - add `"/authentication/logout/"` to the routes skipped by `test_every_protected_route_has_a_permitted_and_a_refused_caller`, with a comment that sign-out, like sign-in and registration, is open to every caller.

  Every other new row must have at least one permitted and one refused caller (Principle II). If group A has merged, readers on librarian-only rows are `NOT_FOUND`.
- [ ] T075 [US5] Run `python manage.py test authentication.test_routes` until it passes. Then temporarily delete the `/book/preferences/` row, run it again, and confirm that `test_every_web_route_is_in_the_table` fails naming `book/preferences/`. Restore the row. Record both runs in `specs/005-tech-debt-fixes/progress.md`; they are evidence for FR-024 and the PR.
- [ ] T076 [P] [US5] In `specs/003-priority-tech-debt/contracts/access-control.md` "Web routes", add rows matching T074 for the assistant pages, For You, Saved Books, a book's rating and a book's settings, and update the sign-out row if C has merged. Cite KAN-102.
- [ ] T077 [US5] Constitution amendment (KAN-101 and the browser gate), in this order:
  - (a) Set `.specify/superpowers-handoff.json` `status` to `blocked`, with `blocked_reason` "constitution amendment for KAN-101", through `/speckit-speckit-superpowers-bridge-handoff` or its script.
  - (b) Run `/speckit-constitution` with this input: MINOR amendment 2.4.1 → 2.5.0; in "Development Workflow & Quality Gates" item 4, make the test command `manage.py test authentication author book order events audit ai`; add to the smoke-test list "the browser sign-in tests (`library/test_selenium_auth_pytest.py` and `library/test_selenium_auth_unittest.py`, Selenium on headless Chrome) on the `ubuntu-latest` leg"; set Last Amended to today; give a sync report. The rationale is the technical lead's decision of 2026-11-04 to list the gate that KAN-94 added; `ai` alone would be PATCH.
  - (c) Set the handoff back to `executing`.
  - Stage only `.specify/memory/constitution.md`, plus any template the command changed for this amendment.
- [ ] T078 [P] [US5] In `AGENTS.md` line 4, change the command to `python manage.py test authentication author book order events audit ai`.
- [ ] T079 [US5] Check with `grep -n "manage.py test authentication author book order events audit ai" AGENTS.md .specify/memory/constitution.md` (one hit each) and `grep -n -i "browser sign-in" .specify/memory/constitution.md`. Confirm that the version line reads `2.5.0`. Run lint and the full suite.

### Documentation and delivery

- [ ] T080 [P] [US5] Add the group D changelog entry at the top of `docs/shared/changelog.md`: `Every page in the access tests, and CI's test command in the docs (KAN-101, KAN-102)`. Mention constitution 2.5.0 and why it is MINOR.
- [ ] T081 [US5] Commit with `preview-commit` (message `test(authentication): require every page in the access tests and give CI's test command (KAN-101, KAN-102)`), then push and open the PR with `preview-pr`, as `specs/005-tech-debt-fixes/contracts/pull-requests.md` (Group D) describes:
  - the manual removal check from T075;
  - "merge after #<group B PR>", because the amendment names B's step;
  - @Arezzon's approval is required for the constitution;
  - assignee @fazelukario.

  Record the PR.
- [ ] T082 [US5] Run `gh pr checks <n> --watch`, fix any failure on the branch, and record the green run.
- [ ] T083 [US1] Post the KAN-101 and KAN-102 comments from `specs/005-tech-debt-fixes/progress.md`, with the PR filled in. The KAN-101 summary explains MINOR 2.5.0. Then move both to **In Review** (transition `41`), and record the comment IDs and moves.

**Checkpoint**: all four groups are in review.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: prove the end state and hand over.

- [ ] T084 Fix any merge conflicts in PRs that have fallen behind `main`, by merging `origin/main` into the branch (no force-push). This applies mainly to the shared `library/authentication/test_routes.py` and `docs/shared/changelog.md`. Re-run CI, and record it.
- [ ] T085 [P] Run `gh pr list --author @me --state open --json number,title,assignees,url` and `gh pr checks` for each PR. Expect exactly four open PRs from this work, each assigned to @fazelukario, each green (SC-002).
- [ ] T086 [P] Run `searchJiraIssuesUsingJql` with `parent = KAN-90 AND assignee = currentUser()`. Expect all seven in **In Review**, none in Done, and each with exactly one comment from this work that links its PR (SC-001).
- [ ] T087 Compare the 16 children of KAN-90 with the T006 snapshot. Only the seven issues may have changed status, and no assignee may have changed. Record the result in `specs/005-tech-debt-fixes/progress.md`.
- [ ] T088 In `specs/005-tech-debt-fixes/progress.md`, record SC-001 to SC-009 as met or not met, with evidence links (PRs, CI runs, Jira comments). Set `**Status**` in `specs/005-tech-debt-fixes/spec.md` to "Implemented; in review", with the date.
- [ ] T089 Report to the technical lead:
  - the four PR links and their CI results;
  - the reviews needed: @Arezzon for the constitution and fallback paths, @Dima22820 for test files, @anastasiiaMirovska for `docs/ba/`;
  - that D merges after B;
  - that the register update and the moves to Done remain the technical lead's, as KAN-90 describes;
  - any deviation recorded.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)** → **Foundational (Phase 2)** → **US1 preparation (Phase 3)**. These block every
  group.
- **US2 (C) → US3 (A) → US4 (B) → US5 (D)**, in order. The request asks for one task in progress at a
  time. The code of each story does not depend on another's unmerged PR (spec FR-007).
- **Polish (Phase 8)** comes after all four groups are In Review.

### Cross-group interactions (handled in the tasks)

| Interaction | Handled by |
| ----------- | ---------- |
| C's sign-out button against B's browser tests | B's `LOG_OUT` locator accepts a link or a button (T059, T060). C checks the tests if B has merged first (T024) |
| C's sign-out against D's route rows | D records sign-out as it is on `main` (T074). Whichever merges second updates the rows (T084) |
| A's reader 404s against D's new rows | D measures answers on its own base (T074). Conflicts in `test_routes.py` are resolved at T084 |
| D's constitution text names B's step | D's PR asks to merge after B (T081) |

### Within each story

The issue moves to In Progress, then the branch is created, then tests are written and seen failing,
then the change is made, the suite turns green, docs and the changelog are updated, the work is
committed, the PR is opened, CI goes green, and finally the comment is posted and the issue moves to
In Review.

### Parallel opportunities

- Phase 1: T002 and T003.
- US2: tests T012–T015 (four files); implementation T018–T020 (three files); docs T026 and T027.
- US3: tests T034–T040 (seven test files); implementation T042 and T043; docs T047–T051 (five files).
- US4: T058–T060 (three files); docs T064 and T065.
- US5: T076 and T078 alongside T075–T077; T080.
- Polish: T085 and T086.

## Parallel Example: User Story 3

```text
Write the failing tests together:
  T034 library/authentication/test_not_found.py
  T035 library/authentication/test_routes.py
  T037 library/author/tests.py
  T038 library/book/tests.py, library/book/test_delete.py
  T039 library/events/tests.py, test_forecast_page.py, test_overview_page.py
  T040 library/order/tests.py

Then the two code changes together:
  T042 library/library/templates/404.html
  T043 library/authentication/decorators.py
```

## Implementation Strategy

### MVP first (User Story 2 with User Story 1's flow)

1. Phases 1–3.
2. Phase 4 (group C): the two account-safety fixes, and the first full pass of the Jira flow.
3. **Stop and validate**: KAN-96 and KAN-97 are In Review with a green PR. The flow is proven before it
   is repeated.

### Incremental delivery

Each next group (A, then B, then D) adds one PR and moves its issues the same way. Every group can be
reviewed and merged on its own; only D asks to wait for B.

## Notes

- `[P]` tasks touch different files and do not depend on unfinished tasks.
- A test task is done only when the test has been seen failing on the unchanged code (Principle III).
  The exceptions are group B's tests, which are themselves the change, and group D's documentation.
- Do not merge any PR, and do not move anything to Done.
- Do not change a Jira description. Comments follow `contracts/jira-reporting.md` exactly. Anything
  longer is shown to the technical lead first.
