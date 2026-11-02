# Technical debt register

This register lists the priority technical debt of v1.0 and the gaps found while closing it (KAN-62).
Each item shows its priority, owner and status, with evidence, a plan or a blocker. The rules are in
the [register contract](../../specs/003-priority-tech-debt/contracts/debt-register.md).

**Updated**: 2026-11-02, by PR 12 (KAN-71).

**KAN-62**: stays open. 2 P1 items are open, and FR-056 keeps KAN-62 from moving to Done while any
P1 item is open or blocked.

## What keeps KAN-62 open

| Who acts | Items | What remains |
|---|---|---|
| @fazelukario, with people new to the system | TD-15 | The keyboard and screen-reader checks, and the walkthrough |
| @fazelukario and @myrrhfawn | TD-28 | Correcting the descriptions of KAN-18 and KAN-19 in Jira |

## How to read it

- **Priority**: a P1 item blocks KAN-62 (FR-056). P2 and P3 items do not.
- **Status**:

  | Status | What it needs |
  |---|---|
  | closed | Linked evidence |
  | open | An owner, a plan and a target sprint |
  | blocked | The blocker, and who can remove it |
  | accepted | The product owner's decision, its reason and a review date. A P1 item cannot be accepted. |
- **Source**:
  - `LR1` and `LR2`: the team's analyses of v1.0 and the design of v2.0;
  - `KAN-NN`: a Jira issue;
  - `Risk R#`: the risk register on the team's Confluence roadmap;
  - `Finding`: a defect or gap found while closing KAN-62 ([research R30](../../specs/003-priority-tech-debt/research.md#r30-findings-for-the-register)).
- **Owner**: a person, by their GitHub handle, and their role. Owners start from the owners in the
  risk register.
- **Target sprint**: Lab 4 · Development (until 2026-11-03), Lab 5 · Testing, or Final · Product
  v2.0.
- IDs are never reused.

## Register

| ID | Item | Source | Priority | Owner | Status | Evidence, plan or blocker | Target sprint |
|---|---|---|---|---|---|---|---|
| TD-01 | Upgrade the framework and dependencies, with a migration check | LR1, KAN-17 | P1 | @fazelukario, technical lead | closed | [#30](https://github.com/Arezzon/Library-Django/pull/30), [#31](https://github.com/Arezzon/Library-Django/pull/31), [#32](https://github.com/Arezzon/Library-Django/pull/32) and [#34](https://github.com/Arezzon/Library-Django/pull/34): Django 5.2 LTS. `library/authentication/tests.py::MigrationStateTests` fails if a model change has no migration. | — |
| TD-02 | Show availability without N+1 queries, with the query counts and the catalog speed measured | LR1, KAN-18 | P1 | @fazelukario, technical lead | closed | The query counts: [#38](https://github.com/Arezzon/Library-Django/pull/38) (PR 2), the `test_queries.py` tests of five apps, and the [query count measurements](../../specs/003-priority-tech-debt/research.md#query-counts-per-list-pr-2-fr-048). On the Pi, 95% of 60 catalog page loads finished within 54.2 ms, where the target is 2 s ([Pi measurements](../../specs/003-priority-tech-debt/research.md#on-the-raspberry-pi-t039-t067-t137-t149-t172), T039, SC-010). | — |
| TD-03 | Issue books atomically | KAN-19, Risk R2 | P1 | @fazelukario, technical lead | closed | `library/order/tests.py::ConcurrentIssuanceTests`: two loans of the last copy race, directly and through the API, and exactly one succeeds. The second waits for the book's lock, then checks the stock again. The Jira description is corrected under TD-28. | — |
| TD-04 | 48-hour reservations with atomic stock | LR2, KAN-55 to KAN-58, Risk R2 | P1 | @fazelukario, technical lead | closed | [#41](https://github.com/Arezzon/Library-Django/pull/41), [#42](https://github.com/Arezzon/Library-Django/pull/42), [#43](https://github.com/Arezzon/Library-Django/pull/43) and [#44](https://github.com/Arezzon/Library-Django/pull/44) (PRs 4 to 7); `library/order/test_reservations.py::ReservationRaceTests`; and CI's burst check ("Verify a burst of reservations holds exactly one copy", [run on `main`](https://github.com/Arezzon/Library-Django/actions/runs/41332873249)). On the Pi, a burst of 100 held exactly 1 copy, and with 30 readers each operation's p95 stayed under 755 ms, where the limit is 3 s ([Pi measurements](../../specs/003-priority-tech-debt/research.md#on-the-raspberry-pi-t039-t067-t137-t149-t172), T137, SC-003). | — |
| TD-05 | Test the business rules, and measure coverage | LR1, KAN-21, Risk R3 | P1 | @Dima22820, QA lead | closed | [#39](https://github.com/Arezzon/Library-Django/pull/39) (PR 3). CI reports the coverage of changed lines on every pull request: 99.6% across PRs 1 to 11 ([coverage measurements](../../specs/003-priority-tech-debt/research.md#coverage-of-added-and-changed-lines-fr-051), SC-011). | — |
| TD-06 | Require lint and format before merge | KAN-22 (KAN-72), Risk R11 | P1 | @Arezzon, product owner | closed | Ruleset 23898585 requires `lint` ([merge rules](../../specs/003-priority-tech-debt/research.md#merge-rules-on-main-sc-012)). @fazelukario, technical lead, checked the rule on 2026-11-01 (T056, SC-012); no demonstration pull request was opened. | — |
| TD-07 | Require code scanning before merge | KAN-15 (KAN-73), Risk R11 | P1 | @Arezzon, product owner | closed | The ruleset requires CodeQL results, with every alert level counted ([merge rules](../../specs/003-priority-tech-debt/research.md#merge-rules-on-main-sc-012)). @fazelukario, technical lead, checked the rule on 2026-11-01 (T056); no demonstration pull request was opened. | — |
| TD-08 | Require code owners' approval before merge | KAN-13 (KAN-74), Risk R11 | P1 | @Arezzon, product owner | closed | The ruleset requires code owners' review ([merge rules](../../specs/003-priority-tech-debt/research.md#merge-rules-on-main-sc-012)). @fazelukario, technical lead, checked the rule on 2026-11-01 (T056); no demonstration pull request was opened. | — |
| TD-09 | No default secrets, and access control by role | LR1, KAN-24 | P1 | @fazelukario, technical lead | closed | [#19](https://github.com/Arezzon/Library-Django/pull/19) and CI's "Verify the image ships no default SECRET_KEY". [#36](https://github.com/Arezzon/Library-Django/pull/36) (PR 1): every operation declares who may use it. Tests: `library/authentication/test_access.py::OperationAccessTests` and `library/authentication/test_routes.py::WebRouteAccessTests`. Also the [librarian account review](../../specs/003-priority-tech-debt/research.md#librarian-account-review-after-pr-1-fr-007). | — |
| TD-10 | Only an administrator grants the librarian role | LR2 | P1 | @fazelukario, technical lead and operator | closed | [#54](https://github.com/Arezzon/Library-Django/pull/54) (PR 11); `library/authentication/test_access.py::AdministratorRoleTests` and `library/authentication/tests.py::AdministratorCommandTests`. On 2026-11-02 the operator created the designated administrator on the Pi, account #5, with `createsuperuser`, and the audit trail records it ([Pi measurements](../../specs/003-priority-tech-debt/research.md#on-the-raspberry-pi-t039-t067-t137-t149-t172), T149). | — |
| TD-11 | Reliable media storage | KAN-62 | P1 | @fazelukario, technical lead | closed | The site stores no uploaded files: no model has a file field, and `MEDIA_ROOT` is unset ([research R24](../../specs/003-priority-tech-debt/research.md#r24-persistence-cold-start-and-hosting-limits-pr-9-operator)). The [operator guide](../deployment/raspberry-pi-portainer.md#check-data-persistence-and-limits) sets the rule for the future: an upload feature keeps its files in a volume that the backups cover (FR-032). | — |
| TD-12 | Daily backups, with a rehearsed restore | LR2, Risk R7 | P1 | @fazelukario, technical lead | closed | [#37](https://github.com/Arezzon/Library-Django/pull/37) (PR 9), [ADR 0003](../adr/0003-database-backups.md), and CI's "Verify a backup restores". On the Pi, the nightly backup passed its check, a copy passed its checksum and listing on another machine, and a restore rehearsal took 61 s from `createdb` to a passing search, with matching counts ([Pi measurements](../../specs/003-priority-tech-debt/research.md#on-the-raspberry-pi-t039-t067-t137-t149-t172), T067, SC-006). | — |
| TD-13 | Know the hosting limits, the cold start and data persistence | LR1, Risk R8 | P1 | @fazelukario, technical lead | closed | On the Pi ([Pi measurements](../../specs/003-priority-tech-debt/research.md#on-the-raspberry-pi-t039-t067-t137-t149-t172), T067, T172, SC-005, SC-014, FR-031): pages came back within 11 s of restarting each service and 15 s of a redeploy, with the counts unchanged, and within 17 s of a reboot, whose counts were not taken. The stack peaks at 2.6 GiB, with search p95 at 326 ms; its volumes and logs take under 70 MB; no uploaded files exist; and Render is gone. The first catalog load after a quiet period took 74 ms. | — |
| TD-14 | Central technical logs, and an audit of critical changes | LR1 | P1 | @fazelukario, technical lead | closed | [#40](https://github.com/Arezzon/Library-Django/pull/40) (PR 8). Tests: `library/audit/tests.py::AuditGuaranteeTests` and `library/authentication/test_logging.py::RedactionTests`. CI's "Verify the logs hold no secrets or search text" ([run on `main`](https://github.com/Arezzon/Library-Django/actions/runs/41332873249)). | — |
| TD-15 | Main pages that people with any level of digital experience can use and understand | LR1, LR2 | P1 | @fazelukario, technical lead | open | **Done**: [#56](https://github.com/Arezzon/Library-Django/pull/56) (PR 10), with its follow-ups in PR 12. CI's "Verify the main pages meet WCAG 2.2 AA" finds 0 violations on 39 pages ([accessibility measurements](../../specs/003-priority-tech-debt/research.md#accessibility-pr-10-sc-009)). **Plan**: complete each main task with the keyboard alone and with NVDA (T162). Then run the walkthrough with at least 3 people new to the system, of whom at least 80% of attempts must finish without help (T163, SC-009). Unfixed problems get rows here. | Lab 4 · Development |
| TD-16 | Debt register, README and ADRs | KAN-62 | P1 | @fazelukario, technical lead | closed | This register, the README and the [ADR index](../adr/README.md), reviewed in PR 12 (KAN-71) | — |
| TD-17 | Copy backups off the Pi automatically | FR-055, Risk R7 | P2 | @Arezzon, product owner | open | Backups leave the Pi only through the operator's weekly copy, so losing the Pi can cost up to a week of data ([ADR 0003](../adr/0003-database-backups.md)). **Plan**: add an automatic off-device copy before the site holds real readers' data. | Final · Product v2.0 |
| TD-18 | Analytics search events keep the search text | FR-055 | P2 | @anastasiiaMirovska, business analyst | open | **Plan**: decide whether analytics keeps the text of each search. If not, it records only that a search happened. | Lab 5 · Testing |
| TD-19 | The interface is in English only | FR-055 | P2 | @anastasiiaMirovska, business analyst | open | **Plan**: specify which pages and messages get Ukrainian first, then translate them. | Final · Product v2.0 |
| TD-20 | Browser tests under `library/` do not run in CI | FR-055, Risk R3 | P2 | @Dima22820, QA lead | open | `library/test_selenium_auth_pytest.py` and `library/test_selenium_auth_unittest.py`. **Plan**: run them in CI, or remove them. | Lab 5 · Testing |
| TD-21 | P2 search and demand forecasting | KAN-62 | P2 | @Arezzon, product owner | open | KAN-62 puts them out of scope for the v1.0 debt, and KAN-35 holds the forecasting. **Plan**: the product owner decides whether to accept this, with the reason and a review date. | Lab 5 · Testing |
| TD-22 | Signing out works through a GET request instead of a POST form | Finding | P3 | @fazelukario, technical lead | open | `library/authentication/views.py`. **Plan**: sign out with a POST form. | Final · Product v2.0 |
| TD-23 | The admin site's user form shows the password hash as an editable text field | Finding | P3 | @fazelukario, technical lead | open | `library/authentication/admin.py`. Since [#54](https://github.com/Arezzon/Library-Django/pull/54) (PR 11), a changed value is saved as a new password. **Plan**: show the hash read-only, with Django's password field and its link to the change form. | Final · Product v2.0 |
| TD-24 | Pages load Tailwind and fonts from third-party servers in readers' browsers | Finding | P3 | @OLEkSandrKoniaiev, technical architect | open | `library/library/templates/base.html`. **Plan**: build the CSS and serve the fonts from the site itself. | Final · Product v2.0 |
| TD-25 | Audit entries have no retention period | Finding | P2 | @Arezzon, product owner, with @anastasiiaMirovska, business analyst | open | **Plan**: set a retention period, then delete older entries on a schedule. | Lab 5 · Testing |
| TD-26 | Account creation times before PR 3 are unreliable | Finding | P3 | @Arezzon, product owner | open | Every save used to overwrite them, and the past values cannot be recovered ([#39](https://github.com/Arezzon/Library-Django/pull/39)). **Plan**: the product owner decides whether to accept this, with a review date. | Lab 5 · Testing |
| TD-27 | Code-scanning alerts that existed before this feature | Edge case | P2 | @fazelukario, technical lead | closed | None was open when the feature started on 2026-10-27. CodeQL's 7 earlier alerts were fixed on 2026-10-19: 6 stack-trace exposures and 1 missing workflow permission ([closed alerts](https://github.com/Arezzon/Library-Django/security/code-scanning?query=is%3Aclosed)). | — |
| TD-28 | The Jira descriptions of KAN-18 and KAN-19 still describe a stored available count | KAN-62, FR-058 | P1 | @fazelukario (KAN-18), and @myrrhfawn, senior engineer (KAN-19) | open | **Plan**: each assignee corrects their description (T039, T171). Availability is the total copies minus active loans and active reservations. Issuing locks the book and checks availability again, and no stored counter decreases. | Lab 4 · Development |
| TD-29 | Saving a book with an empty title creates a book without a name, on the web and through the API | Finding | P2 | @OLEkSandrKoniaiev, technical architect | open | `library/book/models.py`: `Book.name` allows blank. PR 10's accessibility check found it. **Plan**: require a title in the model, the form and the API, with a test. | Lab 5 · Testing |
| TD-30 | The assistant page showed when its answer was checked as a UTC timestamp, not in Kyiv time with the zone | Finding | P3 | @myrrhfawn, senior engineer | closed | [#55](https://github.com/Arezzon/Library-Django/pull/55) removed the timestamp from the page (`library/ai/templates/ai/assistant.html`), so no page shows it (FR-044). A test in `library/ai/test_interface.py::AssistantInterfaceTests` fails if the page shows it again. The API still gives `checked_at` in ISO 8601 with its offset, for programs. | — |
| TD-31 | The constitution's workflow item 4 and `AGENTS.md` give the test command without `ai`, which CI runs | Finding | P3 | @fazelukario, technical lead | open | **Plan**: add `ai` with the next constitution PATCH amendment, and in `AGENTS.md`. | Final · Product v2.0 |
| TD-32 | CodeQL alert 15 reports a URL redirection on the reservation notice's Dismiss | Finding | P3 | @fazelukario, technical lead | closed | [Alert 15](https://github.com/Arezzon/Library-Django/security/code-scanning/15), `library/order/views.py` (PR 6), was a false positive: the target already passed `url_has_allowed_host_and_scheme` with the request's own host. CodeQL's model of that check covers only a redirect inside its true branch, and the view redirected after it. PR 12 (KAN-71) moves the redirect inside the check. `library/order/test_reservations.py::CancellationNoticeTests` sends a missing `next`, another host, a protocol-relative address and a backslash to the reader's reservations. CodeQL's analysis of the pull request no longer reports the alert. | — |
| TD-33 | `Book.create(authors=[…])` uses the authors before the book is saved | KAN-77 | P3 | @OLEkSandrKoniaiev, technical architect | closed | [#58](https://github.com/Arezzon/Library-Django/pull/58) saves the book before linking its authors, in one transaction. `library/book/test_book_create.py::BookCreateTests`. | — |
| TD-34 | `remove_authors` removes every author, whatever list it is given | KAN-78 | P3 | @OLEkSandrKoniaiev, technical architect | open | Reproduced. **Plan**: fix it with a regression test. | Lab 5 · Testing |
| TD-35 | Team members' real names remain in the Git history: commit authors and co-author lines, `LICENSE`, and earlier versions of the documentation | Finding | P2 | @fazelukario, technical lead | blocked | The files name people by their GitHub handles since PR 12. Removing the names from the history means rewriting every commit on `main`. **Blocker**: the ruleset forbids force-pushing `main`, and only @Arezzon, its administrator, can lift that for the rewrite and change the copyright notice in `LICENSE`. Afterwards, everyone clones the repository again, and GitHub Support removes its cached copies of the old commits. | Lab 5 · Testing |

The walkthrough (T163) has not run yet. Each problem it finds that is not fixed gets a row of its own
(FR-045).

## Keeping it current

- When an open item is done, set it to `closed`, link the evidence, and change the date at the top.
- A new item gets the next free ID, an owner, a priority and a status.
- KAN-62 moves to Done only when no P1 item is open or blocked (FR-056, T171). The KAN-62 line at the
  top says how many remain.
