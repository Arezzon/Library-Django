# Research: Technical Lead's Debt Fixes (KAN-90)

Facts read on 2026-11-04 from `origin/main` at `76f4f0d` (#64) and from Jira. People are named by
GitHub handle.

## R1. Jira workflow and the seven issues

- **Decision**: move issues with `transitionJiraIssue`, by transition ID: `31` leads to **In
  Progress** and `41` to **In Review** (read from `listJiraIssueTransitions` on KAN-96). Read each
  issue's status and assignee just before moving it. If it is no longer @fazelukario's or no longer in
  the expected status, skip it and report it (spec, Edge Cases).
- **Rationale**: KAN is team-managed, and every status can reach every other: Idea, To Do, In
  Progress, In Review and Done. The request approves exactly these two moves for these seven issues
  (spec, Assumptions).
- **Facts**: on 2026-11-04 the seven issues are KAN-79, KAN-80, KAN-94, KAN-96, KAN-97, KAN-101 and
  KAN-102. All are assigned to @fazelukario and have the status
  **To Do**. KAN-94 was @Dima22820's when KAN-90 was published.
- **Comments**: post them with `addOrEditJiraIssueComment` in Markdown. As recorded in the Jira
  Markdown notes, a link label must be plain text (not inline code) and each paragraph must be one
  line. Texts are in [contracts/jira-reporting.md](contracts/jira-reporting.md).
- **Alternatives considered**: `targetStatus` instead of IDs. It works, but the IDs were read and are
  unambiguous.

## R2. Order, branches and pull requests

- **Decision**: work the groups in the order C, A, B, D, one at a time. Each group has its own
  branch from a freshly fetched `origin/main` (`.agents/skills/fresh-feature-branch/SKILL.md`):

  | Group | Branch | Title |
  | ----- | ------ | ----- |
  | C | `fix/kan-96-97-sign-out-and-admin-password` | `fix(authentication): sign out only by form and show the admin password read-only (KAN-96, KAN-97)` |
  | A | `fix/kan-79-80-not-found-page` | `fix(authentication): answer unknown and staff-only pages with the site's 404 page (KAN-79, KAN-80)` |
  | B | `test/kan-94-browser-sign-in-ci` | `test(ci): run the browser sign-in tests on every pull request (KAN-94)` |
  | D | `test/kan-101-102-route-list-and-test-command` | `test(authentication): require every page in the access tests and give CI's test command (KAN-101, KAN-102)` |

- **Rationale**: the user stories rank C first because both of its findings let an unintended action
  change an account. A gives KAN-80 its page. B is independent. D last: its route list then reflects
  what C and A changed, if they have merged by then. The title actions follow the repository's history
  (`fix(...)`, `test(order)`, `docs(shared)`).
- **Waiting for CI**: after `gh pr create`, wait with `gh pr checks <n> --watch`. An issue moves to In
  Review only when every check has passed (spec FR-004).
- **Local Spec Kit state stays out of the PRs**: `specs/005-tech-debt-fixes/` is untracked, and
  `.specify/bridge-events.jsonl`, `.specify/superpowers-handoff.json` and `.specify/bridge-snapshots/`
  change whenever a bridge command runs. None of them is staged in any group's PR. Only group D touches
  `.specify/`, and only `.specify/memory/constitution.md`.
- **Alternatives considered**: stacking B and D on C so that they see the sign-out form at once. This
  is rejected by spec FR-007. Instead, the PR that merges second adapts (R5, R9).

## R3. Signing out (KAN-96, TD-22)

- **Facts**: `library/authentication/views.py:113` signs out on any method, with no decorator.
  `base.html:172` (header) and `:263` (mobile menu) link to it. A GET to `/authentication/logout/` is
  also made by `authentication/test_routes.py:214-230`, `events/tests.py:105` and
  `events/management/commands/smoke_test_tracking.py:164`, which CI runs over real HTTP. The smoke
  test's `request(path, data)` POSTs when it is given data, and it already holds a CSRF `token`.
- **Decision**: put `@require_POST` on the view. A GET then gets 405 and the session stays. The view
  keeps redirecting to the sign-in page, and the `user_logged_out` signal, which the tracking test
  records, still fires. The two links become `<form method="post">` with `{% csrf_token %}` and a
  `<button type="submit">` that keeps the classes `btn-logout ml-2` and `btn-danger w-full
  justify-center`. The form is inline, and the button inherits the link's font, so the look does not
  change. The smoke test POSTs with `csrfmiddlewaretoken`, and the tests switch to POST.
- **Tests that fail without the change**: a signed-in GET keeps the session and gets 405. A POST signs
  out and redirects to sign-in. With `Client(enforce_csrf_checks=True)`, a POST without a token gets
  403 and the session survives. The page renders a form with a CSRF token, not a link.
- **Rationale**: it is the smallest change that meets Principle II's rule for state-changing actions:
  not GET, and CSRF-protected.
- **Alternatives considered**: Django's `LogoutView`, which has been POST-only since Django 5.0. It
  would need `next_page` and would drop the view's explicit redirect, for no gain. Keeping GET and
  adding a confirmation page adds a page and still lets a link sign the user out with one click.

## R4. The admin password field (KAN-97, TD-23)

- **Facts**: `CustomUserAdmin` is a plain `admin.ModelAdmin` that lists `password` in `fieldsets`, so
  the hash shows as a text input. Its `save_model` passes every changed field to
  `services.update_account`, which calls `set_password` for `password`. An edited hash therefore
  becomes the password (#54). `CustomUser` is an `AbstractBaseUser` with no `username`, `groups` or
  `user_permissions`. `is_staff` and `is_superuser` are properties derived from the role. Admin tests
  live in `authentication/test_access.py` (`AdministratorRoleTests`, lines 417–660), including a POST
  to the add page at line 606.
- **Decision**: base `CustomUserAdmin` on `django.contrib.auth.admin.UserAdmin`, with forms for
  `CustomUser`:
  - a change form, a `UserChangeForm` subclass with `Meta.model = CustomUser`, whose
    `ReadOnlyPasswordHashField` is disabled, so it never appears in `changed_data`, and shows Django's
    link to the change-password form;
  - an add form, an `AdminUserCreationForm` subclass with `email` and the name fields, which sets the
    password from its two password fields.

  `UserAdmin` brings the change-password view (`<id>/password/`). That view checks
  `has_change_permission(request, user)`, which already includes `may_change_account`, so a librarian
  still cannot change an administrator's password. Override the attributes that assume Django's `User`
  model: `ordering`, `list_filter`, `filter_horizontal = ()`, `search_fields` and `add_fieldsets`. Keep
  this admin's own `list_display`, role rules, permissions and `save_model` for edits. On add
  (`change=False`), the add form's `save` sets the password.
- **Tests that fail without the change**: the change page shows the hash read-only, with the link. A
  POST of the change form with an edited `password` value leaves `check_password(old)` true. The
  change-password page sets a new password. A librarian gets 403 on an administrator's password page.
  The add page creates a user who can sign in. Update the add-page test at line 606 to send `password1`
  and `password2`.
- **Alternatives considered**:
  - keep `ModelAdmin` and add a custom form and password URL: this re-implements the view, templates
    and lookup guards that `UserAdmin` already has;
  - remove `password` from the form: then the admin site cannot change a password at all, and the issue
    asks for the link.

## R5. The site's 404 page (KAN-79, TD-36)

- **Facts**: `library/library/templates/403.html` extends `base.html` with a card, a heading, a line
  of text and a "Go to the home page" button. There is no `404.html`. Django's default `handler404`
  renders `404.html` through `RequestContext`, so `base.html` gets `request.user` and messages. The test
  runner always uses `DEBUG=False`. CI's stack also runs with `DEBUG=False` (`docker-compose-dev.yml`
  defaults to it, and CI does not set it), while a local `.env` copied from `.env.example` turns it on.
  `scripts/a11y/check_pages.mjs` throws on any non-OK answer (`open()` at line 45).
- **Decision**: add `library/library/templates/404.html` in the style of `403.html`, in English: title
  "Page Not Found | LibrarySys", heading "We can't find this page.", one line of text, and "Go to the
  home page". It does not echo the requested path, so a hidden staff page and an unknown address give
  the same page. In the a11y script, add a visit that accepts 404 and checks an unknown address as a
  visitor and as a reader.
- **Tests that fail without the change**: an unknown address answers 404 with template `404.html`, the
  site's navigation and the home link, for an anonymous caller, a reader and a librarian.
- **Alternatives considered**: a `500.html` as well. It is out of scope (spec, Assumptions): a server
  error page must not depend on the context that `base.html` needs, so it needs its own design.

## R6. Hiding staff pages (KAN-80, TD-37)

- **Facts**: every librarian-only page and action uses `@librarian_required`: 21 views in
  `authentication`, `author`, `book`, `events` and `order`. `role_required` guards no view; only
  `authentication/tests.py:430` tests it. Owner pages use `librarian_or_owner_required`, and
  `user_update` raises `PermissionDenied` in the view for administrator accounts. Both stay at 403
  (spec, Assumptions). The route table in `authentication/test_routes.py` copies
  `specs/003-priority-tech-debt/contracts/access-control.md` ("Web routes"). About 20 more web
  assertions in the app tests expect 403 for a reader. These documents say that readers get 403 on
  staff pages: `docs/ba/analytics-dashboard.md:14,274`, `docs/ba/demand-forecast.md:17,191`, and the
  contract's "Web routes" and "Refusal responses". FR-004 of spec 003 is at
  `specs/003-priority-tech-debt/spec.md:548`.
- **Decision**: in `authentication/decorators.py`, `librarian_required` and `role_required` raise
  `Http404` instead of `PermissionDenied` for a signed-in caller without the role, so the answer is
  decided in one place. Anonymous callers still go to sign-in. DRF permissions are untouched, so the
  API keeps 403. In the same PR:
  - add the exception to FR-004 of spec 003, citing KAN-80 and @Arezzon's decision;
  - update the contract's tables;
  - update the two BA documents;
  - add a sentence on the web answer to the README's access paragraph (`README.md:452`).
- **Tests that fail without the change**: for every staff route, the reader column changes from
  `FORBIDDEN` to `NOT_FOUND`. A reader's answer on `/order/reservations/desk/` has the same status and
  template as an unknown address. `role_required` raises `Http404` for a reader. The app tests that
  assert 403 for a reader on a staff page change to 404, and those for API calls stay 403.
- **Alternatives considered**: a middleware that rewrites 403 into 404. This would also hide owner
  pages and the API's refusals, which the decision excludes.

## R7. Browser sign-in tests in CI (KAN-94, TD-20)

- **Facts**: both files open `webdriver.Chrome()` with no options, maximise the window, and use
  `BASE_URL = "http://127.0.0.1:8000"`. They sign in as the seeded demo reader (`reader@library.com`).
  The CI workflow already uses that account and calls its password public (`docker-build.yml:289`).
  They find "Log In" and "Log Out" by link text, and the error by `.alert-error`, whose text still
  matches `views.py:55`. Neither `selenium` nor `pytest` is pinned anywhere. The browser checks run in
  the `smoke-test` job's `ubuntu-latest` leg (`docker-build.yml:242-266`), where the GitHub image ships
  Google Chrome and Selenium Manager matches the driver. Sign-in has no throttling, so the two failed
  sign-ins per run lock nothing.
- **Decision**:
  - pin `selenium==4.51.0` and `pytest==9.1.1` in `requirements-dev.txt` (CI tooling, not in the image).
    These are the newest releases at least two weeks old on 2026-11-04: selenium 4.52.0 is from
    2026-10-29, and pytest 9.2.0 from 2026-10-27.
  - in both files, read `BASE_URL` from the environment (default unchanged). When `SELENIUM_HEADLESS=1`,
    start Chrome with `--headless=new --window-size=1366,900` and skip maximising, so the desktop header,
    not the mobile menu, is shown.
  - find "Log Out" with an XPath that matches an `a` or a `button` whose text is "Log Out". It then works
    before and after group C (spec FR-019).
  - add a step after "Verify the main pages meet WCAG 2.2 AA" on the `ubuntu-latest` leg. It installs
    the two pins with `grep`, as the coverage step does, and runs
    `python -m pytest library/test_selenium_auth_pytest.py library/test_selenium_auth_unittest.py -v -p no:cacheprovider`
    with `SELENIUM_HEADLESS=1` and `BASE_URL=http://localhost:8000`. pytest also runs the unittest file.
- **Logs**: the tests log the reader's email, never the password, and the step does not write to
  `test-output.txt`, so the secrets check is unaffected.
- **Constitution**: quality-gates item 4 lists the smoke-test checks. Group D's amendment adds this step
  (the technical lead's decision on 2026-11-04; see R8). B's PR says so.
- **Alternatives considered**:
  - rewrite the tests in the existing Playwright scripts: they would no longer be these files, and the
    user chose to keep both;
  - a separate requirements file: `requirements-dev.txt` is already where CI tooling is pinned.

## R8. The test command in the constitution and `AGENTS.md` (KAN-101, TD-31)

- **Facts**: CI runs `manage.py test authentication author book order events audit ai`
  (`docker-build.yml:155,166`). `README.md:506,514,579` already include `ai`. Only
  `.specify/memory/constitution.md:173` and `AGENTS.md:4` lack it. The constitution is version 2.4.1,
  last amended 2026-11-01.
- **Decision**: run `/speckit-constitution` for a MINOR amendment to 2.5.0, with the PR's date as
  "Last Amended" and a sync report. It makes two changes to item 4:
  - add `ai` to the test command;
  - add the browser sign-in tests (both Selenium files, on the `ubuntu-latest` leg) to the smoke-test
    checks.

  `AGENTS.md` gets the same command.
- **Why MINOR**: the technical lead decided on 2026-11-04 to fold B's step in. Adding a gate expands
  guidance materially, which is MINOR under Governance; `ai` alone would be PATCH. KAN-101 asked for a
  PATCH, so its comment says why the bump differs.
- **Merge order**: D's PR asks to merge after B's. D's checks do not depend on B (spec FR-007). The bridge guard refuses
  `speckit.constitution` while the handoff is `executing`, so set the handoff to `blocked` first and
  back to `executing` afterwards (Governance, Amendments).
- **Review**: `.specify/memory/` falls under CODEOWNERS' fallback owner, @Arezzon, whose approval the
  issue requires. It is requested on the PR, not given by this work.
- **Alternatives considered**: editing the file by hand. The constitution forbids it.

## R9. Every web route in the access tests (KAN-102, TD-35)

- **Facts**: `WebRouteAccessTests` checks the `ROUTES` table (method, route, anonymous, reader,
  librarian). `test_access.py:186` walks `get_resolver()` for API views, and the same walk works for
  pages. These web patterns have no row:
  - `assistant/` and `assistant/result/`
  - `book/recommendations/` (For You)
  - `book/preferences/` (Saved Books)
  - `book/<int:book_id>/rating/` (POST)
  - `book/<int:book_id>/preferences/` (POST)
  - `authentication/logout/`

  That is seven patterns: the register counted the assistant's two as one.
- **Decision**:
  - add `web_routes()`, which walks every pattern except the `api/` prefix and counts everything under
    `admin/` as one route, `admin/`. The API has its own guard (`DeclaredAudienceTests`), and the public
    schema and docs pages sit under `api/`.
  - add a test that resolves each `ROUTES` entry with `resolve(...).route` and fails, naming the
    patterns, when a walked pattern has no entry. A second test removes one entry and checks that the
    missing pattern is reported, so the guard cannot silently stop working.
  - add rows for the seven patterns, with the answers measured on the branch.
  - sign-out is open to every caller by design, like sign-in and registration. Its rows record GET and
    POST, and the "permitted and refused caller" check skips it, as it already skips those two.
  - add the rows to the contract's "Web routes" too.
- **Interaction**: if C has merged when D starts, the sign-out rows are POST: redirect to sign-in, and
  GET: 405. Otherwise they record the GET behaviour, and C's PR, merging second, updates them. If A has
  merged, the reader column of staff rows is `NOT_FOUND`.
- **Alternatives considered**: deriving the expected answers automatically. That would check nothing:
  the table states what the contract allows.

## R10. Local checks

- **Decision**: run the Django tests in the `web` service:
  `docker compose -f docker-compose-dev.yml exec -T web python manage.py test authentication author book order events audit ai`.
  Run `ruff check .` and `black --check .` from the repository root with the pins in
  `requirements-dev.txt`. Group B also runs the browser tests three times against the local stack, and
  group A the a11y script, when Node and the stack are available.
- **Facts**: Docker Desktop may need starting first; see the Docker Desktop notes in memory.
