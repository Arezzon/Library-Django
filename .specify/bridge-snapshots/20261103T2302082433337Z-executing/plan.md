# Implementation Plan: Technical Lead's Debt Fixes (KAN-90)

**Branch**: `005-tech-debt-fixes` (spec directory; no git branch; each group gets its own branch) | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-tech-debt-fixes/spec.md`

## Summary

Close the technical lead's seven KAN-90 issues with four pull requests, worked one at a time in the
order C, A, B, D. Each issue moves to In Progress when its group starts. When the PR is open and its CI
has passed, the issue gets a Ukrainian comment with the PR link and moves to In Review.

| Group | Issues | Approach (research) |
| ----- | ------ | ------------------- |
| C | KAN-96, KAN-97 | `@require_POST` on sign-out, with form buttons in `base.html`; the admin is based on Django's `UserAdmin`, with a read-only hash and the change-password view ([R3](research.md#r3-signing-out-kan-96-td-22), [R4](research.md#r4-the-admin-password-field-kan-97-td-23)) |
| A | KAN-79, KAN-80 | `404.html` styled like `403.html`; `librarian_required` and `role_required` raise `Http404` for readers; FR-004 of spec 003, its contract, the README and the BA documents updated ([R5](research.md#r5-the-sites-404-page-kan-79-td-36), [R6](research.md#r6-hiding-staff-pages-kan-80-td-37)) |
| B | KAN-94 | Both Selenium files made headless-capable and configurable, `selenium`/`pytest` pinned, a CI step on the `ubuntu-latest` leg ([R7](research.md#r7-browser-sign-in-tests-in-ci-kan-94-td-20)) |
| D | KAN-101, KAN-102 | Constitution MINOR 2.5.0 through `/speckit-constitution`: `ai` in the command, and B's browser sign-in step in the CI gates. `AGENTS.md` gets the same command. A URL-walking test requires a `ROUTES` row for every web pattern, and seven new rows are added. D merges after B ([R8](research.md#r8-the-test-command-in-the-constitution-and-agentsmd-kan-101-td-31), [R9](research.md#r9-every-web-route-in-the-access-tests-kan-102-td-35)) |

## Technical Context

**Language/Version**: Python 3.12, Django 5.2 LTS, Django REST Framework. Server-rendered templates
with Tailwind via CDN. Node 22 for the a11y script. Ukrainian Markdown for the Jira comments.

**Primary Dependencies**:
- Django's `contrib.auth`: `UserAdmin`, `UserChangeForm`, `AdminUserCreationForm`,
  `ReadOnlyPasswordHashField`.
- `require_POST` and `Http404`.
- CI tooling only: `selenium==4.51.0` and `pytest==9.1.1`.
- Operations: the Atlassian connector (`transitionJiraIssue`, `addOrEditJiraIssueComment`) and the
  GitHub CLI (`gh`).

**Storage**: PostgreSQL 18 with pgvector. No model change and no migration.

**Testing**:
- Django tests in the `web` service of `docker-compose-dev.yml`.
- `ruff` and `black` at the pinned versions.
- The axe check through Playwright.
- The Selenium tests against the dev stack.
- `smoke_test_tracking`.

**Target Platform**: Linux containers (`linux/amd64`, `linux/arm64`). GitHub Actions runs the browser
steps on the `ubuntu-latest` leg only.

**Project Type**: web application, a Django monolith under `library/`.

**Performance Goals**: N/A. No query path changes, and the existing query-count tests stay as they
are.

**Constraints**:
- One PR per group, each from a fresh `origin/main` and green on its own.
- No merge.
- In Review only after CI has passed.
- New tests fail without the change.
- The constitution changes only through `/speckit-constitution`, with the bridge handoff set to
  `blocked` while it runs.
- Handles only, never real names.
- Local Spec Kit state stays out of every PR.

**Scale/Scope**: 7 issues, 4 PRs, 7 Jira comments, 14 moves.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle or rule | How this plan meets it | Result |
| ----------------- | ---------------------- | ------ |
| I. Domain-owned apps | Sign-out, the admin and the decorators stay in `authentication`. `404.html` sits with `403.html` in `library/library/templates/`, which is project-wide wiring. Each app's tests stay in that app. No new app | Pass |
| II. Explicit role-based access | Sign-out becomes non-GET and CSRF-protected, which brings it into compliance. Staff pages keep their declared audience; only the refusal's status changes, in the one decorator. Every changed route keeps a permitted and a refused caller. Group D makes a missing route fail a test. Sign-out is open to all, like sign-in, so the check skips it, as research R9 explains | Pass |
| III. Test-backed changes | Groups C, A and D add tests that fail without their change, against PostgreSQL in the `web` service. B's change is to the tests themselves; they run in CI and are run three times locally. D's documentation change is exempt (spec FR-009). `smoke_test_tracking` keeps passing, now with POST | Pass |
| IV. Secrets and safe defaults | No new secret. The Selenium files keep the demo reader's password, which the workflow already calls public. The tests log the email only, and the logs-secrets step still runs | Pass |
| V. Consistent data, best-effort side effects | No data path changes. Sign-out still fires `user_logged_out`, which the tracking records | Pass |
| VI. Lean, portable, reproducible deployment | Nothing is added to the image. The two pins are CI tooling in `requirements-dev.txt`. No change to Technology & Platform Constraints | Pass |
| Workflow 1, branching | Each group's branch starts from a freshly fetched `origin/main` | Pass |
| Workflow 3–4, checks and CI gates | Local lint and tests before each PR, and every CI gate green before In Review. Group B adds a smoke-test step, and group D's amendment adds it to item 4 (research R7, R8). Until D merges, item 4 lists less than CI enforces, which is the safe direction | Pass |
| Workflow 5–6, PRs and scope | Titles, template, changelog and code owners per [contracts/pull-requests.md](contracts/pull-requests.md). Each PR holds only its group | Pass |
| Workflow 7, documentation | Group A updates the README, `docs/ba/analytics-dashboard.md`, `docs/ba/demand-forecast.md`, FR-004 of spec 003 and its contract. Group D updates the contract's routes. Group B adds the README's run instructions | Pass |
| Governance, amendments | Group D amends through `/speckit-constitution` as a MINOR (2.4.1 to 2.5.0), because it adds a gate to item 4, with the handoff `blocked` during it. @Arezzon is requested as code owner | Pass |

**Post-design re-check** (after Phase 1): unchanged, and all gates pass. Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/005-tech-debt-fixes/
├── spec.md
├── plan.md                    # This file
├── research.md                # Phase 0: R1–R10
├── data-model.md              # Phase 1: issues, groups, PRs, access answers, admin forms
├── quickstart.md              # Phase 1: how to validate each group and the end state
├── contracts/
│   ├── jira-reporting.md      # Moves and the Ukrainian comment texts
│   ├── pull-requests.md       # Branch, title, contents and notes per group
│   └── web-access.md          # Changed web answers, the FR-004 amendment, the route-list rule
├── checklists/requirements.md
└── tasks.md                   # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
library/
├── authentication/
│   ├── views.py               # C: @require_POST on logout
│   ├── admin.py               # C: UserAdmin-based CustomUserAdmin, change and add forms
│   ├── decorators.py          # A: Http404 for a signed-in caller without the role
│   ├── test_routes.py         # C, A, D: sign-out tests, reader 404s, web_routes() guard, new rows
│   ├── test_access.py         # C: admin tests (add form fields, read-only password, password view)
│   └── tests.py               # A: role_required raises Http404
├── library/templates/
│   ├── base.html              # C: two sign-out forms
│   └── 404.html               # A: new
├── events/
│   ├── tests.py               # C: sign out by POST
│   └── management/commands/smoke_test_tracking.py   # C: POST with csrfmiddlewaretoken
├── author/ book/ order/ events/ ai/ audit/          # A: reader-on-staff-page assertions 403 → 404
├── test_selenium_auth_pytest.py                     # B: BASE_URL, headless, link-or-button Log Out
└── test_selenium_auth_unittest.py                   # B: same
scripts/a11y/check_pages.mjs   # A: visit an unknown address as visitor and reader, expect 404
.github/workflows/docker-build.yml                   # B: browser sign-in step
requirements-dev.txt           # B: selenium, pytest pins
.specify/memory/constitution.md                      # D: MINOR 2.5.0 (ai; browser sign-in gate)
AGENTS.md                      # D: test command with ai
specs/003-priority-tech-debt/spec.md                 # A: FR-004 exception
specs/003-priority-tech-debt/contracts/access-control.md   # C, A, D: route table and refusals
docs/ba/analytics-dashboard.md, docs/ba/demand-forecast.md # A: readers get 404
README.md                      # A: web refusal; B: running the browser tests
docs/shared/changelog.md       # every group: one entry
```

**Structure Decision**: the existing Django monolith. Each change goes in the app that owns it, and
project-wide templates go in `library/library/templates/`. No new app, module or dependency in the
image.

## Delivery sequence

For each group, in the order C, A, B, D:

1. Re-read its issues. If they are @fazelukario's and in To Do, move them to In Progress (transition
   `31`).
2. Create the branch from a freshly fetched `origin/main`. Merged earlier groups are therefore
   included; unmerged ones are not.
3. Write the failing tests, then the change. Run the quickstart checks for the group.
4. Commit with `preview-commit`, then push and open the PR with `preview-pr`: template, changelog
   entry, assignee.
5. Wait for CI. If it fails, fix on the same branch; the issues stay In Progress.
6. When CI is green, post each issue's comment
   ([contracts/jira-reporting.md](contracts/jira-reporting.md)), then move it to In Review (transition
   `41`).

Group D only:

- Set `.specify/superpowers-handoff.json` to `blocked` before `/speckit-constitution`, and back to
  `executing` after it.
- Its PR asks to merge after group B's, because the amendment names B's CI step.

## Complexity Tracking

No violations.
