# Contract: pull requests

One PR per group, made with `.agents/skills/preview-commit/SKILL.md` and then
`.agents/skills/preview-pr/SKILL.md`. Every PR has these:

- **Base**: `main`. The branch starts from a freshly fetched `origin/main`.
- **Assignee**: @fazelukario, checked after creation.
- **Description**: the sections of `.github/PULL_REQUEST_TEMPLATE.md`.
  - "What changed" names the Jira keys and TD IDs and links the issues.
  - "How to verify" gives the commands from [quickstart.md](../quickstart.md).
  - The Definition of Done ticks only what is true, and says why for anything left unticked.
- **Changelog**: one entry at the top of `docs/shared/changelog.md`: the date, a topic, then fewer than
  200 words.
- **Scope**: only the group's files. Never `specs/005-tech-debt-fixes/`, `.specify/bridge-events.jsonl`,
  `.specify/superpowers-handoff.json` or `.specify/bridge-snapshots/`.
- **People**: named by GitHub handle only. Code owners review per `.github/CODEOWNERS`.
- **Merging**: not merged by this work.

## Group C: KAN-96 + KAN-97

- **Branch**: `fix/kan-96-97-sign-out-and-admin-password`
- **Title**: `fix(authentication): sign out only by form and show the admin password read-only (KAN-96, KAN-97)`
- **What changed**: TD-22 and TD-23.
  - Signing out takes a POST with a CSRF token. A GET gets 405 and keeps the session. Both "Log Out"
    controls are form buttons that look as before.
  - The tracking smoke test signs out by POST.
  - The admin user form shows the hash read-only, with a link to the change-password form.
  - Adding a user still sets a password.
- **Changelog topic**: `Sign out by form, and a read-only password in the admin site (KAN-96, KAN-97)`
- **Notes**:
  - If group B has merged first, this PR leaves the browser tests passing; they find "Log Out" as a
    link or a button.
  - If group D has merged first, the sign-out rows of `ROUTES` change to POST and 405.

## Group A: KAN-79 + KAN-80

- **Branch**: `fix/kan-79-80-not-found-page`
- **Title**: `fix(authentication): answer unknown and staff-only pages with the site's 404 page (KAN-79, KAN-80)`
- **What changed**: TD-36 and TD-37.
  - `404.html` is styled like the 403 page.
  - Librarian-only pages and actions answer a signed-in reader 404, decided in
    `authentication/decorators.py`. Anonymous callers still go to sign-in, and the API keeps 403.
  - FR-004 of spec 003 and its access contract carry the exception.
  - The BA documents and the README say what readers get.
  - The a11y check covers the 404 page.
  - @Arezzon decided option 1 of KAN-80, as the technical lead reported on 2026-11-04.
- **Changelog topic**: `A 404 page in the site's style, and staff pages hidden from readers (KAN-79, KAN-80)`
- **Note**: code owners include @anastasiiaMirovska for `docs/ba/`.

## Group B: KAN-94

- **Branch**: `test/kan-94-browser-sign-in-ci`
- **Title**: `test(ci): run the browser sign-in tests on every pull request (KAN-94)`
- **What changed**: TD-20, path 1.
  - Both files stay. They read `BASE_URL` and `SELENIUM_HEADLESS`, and find "Log Out" as a link or a
    button.
  - `selenium==4.51.0` and `pytest==9.1.1` are pinned in `requirements-dev.txt`.
  - A step on the `ubuntu-latest` leg runs both files against the CI stack.
  - The README says how to run them locally.
- **Changelog topic**: `Browser sign-in tests run in CI (KAN-94)`
- **Notes**:
  - Constitution item 4 does not list this step yet. Group D's amendment adds it.
  - Code owners for the test files: @Dima22820, @Arezzon.

## Group D: KAN-101 + KAN-102

- **Branch**: `test/kan-101-102-route-list-and-test-command`
- **Title**: `test(authentication): require every page in the access tests and give CI's test command (KAN-101, KAN-102)`
- **What changed**: TD-31 and TD-35.
  - Constitution 2.5.0 (MINOR, through `/speckit-constitution`): item 4 gives
    `manage.py test authentication author book order events audit ai`, and lists the browser sign-in
    tests among the smoke-test checks. MINOR because a gate is added (the technical lead's decision,
    2026-11-04); `ai` alone would be PATCH.
  - `AGENTS.md` gives the same command.
  - The description asks to merge after group B's PR.
  - A new test walks every web route and fails on one missing from `ROUTES`. A second test checks that
    the guard reports a removed entry.
  - Seven patterns get rows, also in the spec 003 contract.
  - The PR records the manual check: with one row removed, the test failed and named the route.
- **Changelog topic**: `Every page in the access tests, and CI's test command in the docs (KAN-101, KAN-102)`
- **Note**: @Arezzon must approve the constitution change as its code owner.
