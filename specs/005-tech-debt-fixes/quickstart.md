# Quickstart: validating the four groups

Run from the repository root unless a step says otherwise. Expected answers are in
[contracts/web-access.md](contracts/web-access.md). The Jira steps are in
[contracts/jira-reporting.md](contracts/jira-reporting.md).

## Prerequisites

- Docker Desktop is running. If `docker info` fails, start it as the Docker Desktop memory note says.
- The dev stack is up: `docker compose -f docker-compose-dev.yml up -d --wait`.
- Lint tools at the pinned versions: `python -m pip install -r requirements-dev.txt`. From group B,
  this also installs selenium and pytest.
- For the browser checks, Node 22 and Google Chrome. The a11y script installs its own Chromium.

## Every group

```bash
ruff check . && black --check .
docker compose -f docker-compose-dev.yml exec -T web \
  python manage.py test authentication author book order events audit ai --verbosity 1
```

Expected: no lint findings, and every test passes. For a behaviour change, also run the new tests
against `origin/main`'s code, or with the change reverted, and see them fail (Principle III).

## Group C: sign out and the admin password

```bash
docker compose -f docker-compose-dev.yml exec -T web python manage.py test authentication events
docker compose -f docker-compose-dev.yml exec -T web python manage.py smoke_test_tracking   # as CI runs it; ends with PASS
```

- In a browser, signed in: open `http://localhost:8000/authentication/logout/` directly. You get 405
  and are still signed in. Press "Log Out" in the header, then in the mobile menu at 400 px width, by
  mouse and by keyboard (Tab, Enter). Each signs you out and goes to the sign-in page.
- As an administrator in `/admin/`: open a user. The password is read-only and links to the
  change-password form. Save the user without changes, and the old password still signs in. Change the
  password through the link, and the new one signs in.

## Group A: the 404 page and staff pages

```bash
docker compose -f docker-compose-dev.yml exec -T web python manage.py test authentication author book order events
```

- A local `.env` usually sets `DEBUG=True`, which shows Django's debug page. To see the real page,
  restart the web service with `DEBUG=False`:
  `DEBUG=False docker compose -f docker-compose-dev.yml up -d --wait web`.
  - Open `/no-such-page/`: 404 in the site's style, with the navigation and "Go to the home page".
  - As the demo reader, open `/order/reservations/desk/`: the same page, and 404.
  - As the demo librarian, open the same address: the desk page.
- Accessibility, with the stack on `DEBUG=False`:
  `npm ci --prefix scripts/a11y && npx --prefix scripts/a11y playwright install chromium && node scripts/a11y/check_pages.mjs --base-url http://localhost:8000`.
  Expected: 0 violations, including the 404 page.

## Group B: browser sign-in tests

```bash
SELENIUM_HEADLESS=1 BASE_URL=http://localhost:8000 \
  python -m pytest library/test_selenium_auth_pytest.py library/test_selenium_auth_unittest.py -v -p no:cacheprovider
```

Run it three times. Expected: 4 passed each time. The stack must hold the seeded demo reader. Without
`SELENIUM_HEADLESS`, a visible Chrome window opens, as before.

## Group D: test command and route list

```bash
grep -n "manage.py test authentication author book order events audit ai" AGENTS.md .specify/memory/constitution.md
grep -n "^\*\*Version\*\*" .specify/memory/constitution.md   # 2.5.0, Last Amended = PR date
grep -n -i "browser sign-in" .specify/memory/constitution.md  # item 4 names the step
docker compose -f docker-compose-dev.yml exec -T web python manage.py test authentication.test_routes
```

- Remove one row from `ROUTES`, for example `/book/preferences/`, and run `authentication.test_routes`
  again. One test fails and names `book/preferences/`. Put the row back, and the run passes. Record
  this in the PR.

## After each PR

```bash
gh pr view <n> --json title,assignees,baseRefName,url
gh pr checks <n> --watch
```

- Expected: the title format holds, @fazelukario is the assignee, the base is `main`, and every check
  passes.
- Then post the comment and move the group's issues to In Review. Read them back: status In Review,
  one comment with the PR link.

## At the end

- JQL `parent = KAN-90 AND assignee = currentUser()` lists the seven issues, all in In Review.
  None is in Done.
- No other KAN-90 issue changed status.
- Four open PRs, one per group, each with green checks.
