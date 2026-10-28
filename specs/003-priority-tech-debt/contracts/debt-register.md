# Contract: The debt register (PR 12)

**Requirements**: FR-054 to FR-058, SC-013, Story 9 | **Research**: R28, R30

## Location and audience

The register is `docs/shared/debt-register.md`. Its readers are the product owner, the business
analyst, reviewers and the team. KAN-62 links to it (FR-058).

## Table

| Column | Content | Rule |
|---|---|---|
| ID | `TD-NN` | Never reused |
| Item | What the debt is, in one sentence | Plain language |
| Source | `LR1`, `LR2`, `KAN-NN`, `Risk R#` or `Finding` (research.md R30) | At least one |
| Priority | `P1`, `P2` or `P3` | P1 blocks KAN-62 (FR-056) |
| Owner | A named person, with their role | Starts from the risk register's owner roles (R28) |
| Status | `closed`, `open`, `blocked` or `accepted` | See below |
| Evidence, plan or blocker | Links or text | As the status requires |
| Target sprint | For example, "Lab 5" | Required when the item is `open` |

| Status | Requires |
|---|---|
| `closed` | A link to evidence: a merged PR, a CI run, a test (`path::name`), a measurement or restore record in research.md, or a setting (the ruleset JSON) |
| `open` | An owner, a plan in one or two sentences, and a target sprint |
| `blocked` | The blocker and who can remove it |
| `accepted` | The product owner's decision to live with it, the reason, and a date to review it. Not allowed for P1. |

## Closing rule

KAN-62 moves to Done only when:
- every item that KAN-62 names is `closed` or links to the blocker that keeps KAN-62 open;
- no P1 item is `open` or `blocked`;
- every `open` item has an owner, a priority and a plan with a target sprint (SC-013).

## Initial items

PR 12 writes these rows. Owners are named in the register itself.

| ID | Item | Source | Priority | Expected status at close | Evidence or plan |
|---|---|---|---|---|---|
| TD-01 | Framework and dependency upgrade, migration check | LR1, KAN-17 | P1 | closed | PRs #30 to #32 and #34; `authentication/tests.py::MigrationStateTests` |
| TD-02 | Availability without N+1 queries, with the counts measured | LR1, KAN-18 | P1 | closed | PR 2; the `test_queries.py` tests; Measurements |
| TD-03 | Atomic issuing | KAN-19 | P1 | closed | `order/tests.py::ConcurrentIssuanceTests`; KAN-19's description corrected |
| TD-04 | 48-hour reservations with atomic stock | LR2, KAN-55 to KAN-58 | P1 | closed | PRs 4 to 7; race tests; Measurements (burst and load) |
| TD-05 | Business-rule tests and coverage | LR1, KAN-21, Risk R3 | P1 | closed | PR 3; coverage reports per PR |
| TD-06 | Lint and format required before merge | KAN-22 (KAN-72) | P1 | closed | Ruleset JSON; demonstration PR |
| TD-07 | Code scanning required before merge | KAN-15 (KAN-73) | P1 | closed | Ruleset JSON; demonstration PR |
| TD-08 | Code owners' approval required before merge | KAN-13 (KAN-74) | P1 | closed | Ruleset JSON; demonstration PR |
| TD-09 | No default secrets; access control by role | LR1, KAN-24 | P1 | closed | PR 1; access tests; the librarian account review |
| TD-10 | Administrator role grants the librarian role | LR2 | P1 | closed | PR 11 |
| TD-11 | Reliable media storage | KAN-62 | P1 | closed | The record that no files are uploaded, and the rule for the future (FR-032) |
| TD-12 | Daily backups with a rehearsed restore | LR2, Risk R7 | P1 | closed | PR 9; the CI restore check; the rehearsal record |
| TD-13 | Hosting limits, cold start and persistence | LR1 | P1 | closed | Measurements (FR-030, FR-031) |
| TD-14 | Central technical logs and an audit of critical changes | LR1 | P1 | closed | PR 8; the log check in CI |
| TD-15 | Accessible, understandable main pages | LR1, LR2 | P1 | closed | PR 10; the automated report; the walkthrough |
| TD-16 | Debt register, README and ADRs | KAN-62 | P1 | closed | PR 12; `docs/adr/` |
| TD-17 | Automatic off-device backup copy | FR-055, Risk R7 | P2 | open | Add it before the site holds real readers' data |
| TD-18 | Analytics search events keep the search text | FR-055 | P2 | open | The business analyst decides whether to keep the text |
| TD-19 | Interface in English only | FR-055 | P2 | open | Ukrainian translation |
| TD-20 | Browser tests under `library/` do not run in CI | FR-055 | P2 | open | Run them in CI, or remove them |
| TD-21 | P2 search and demand forecasting | KAN-62 | P2 | accepted | Out of scope for v1.0 debt |
| TD-22 | Sign-out works through GET | Finding | P3 | open | Sign out with POST |
| TD-23 | The admin site's user form shows the password hash as text | Finding | P3 | open | Use Django's password widget |
| TD-24 | Pages load assets from third-party servers | Finding | P3 | open | Serve them locally |
| TD-25 | No retention period for audit entries | Finding | P2 | open | The product owner and the business analyst set one |
| TD-26 | Account creation times before PR 3 are unreliable | Finding | P3 | accepted | They cannot be recovered |
| TD-27 | Code-scanning alerts that existed before this feature | Edge case | per alert | open or closed | Triaged list, linked |

The walkthrough's problems that are not fixed (FR-045), and any defect that PR 3 or a later PR files
under FR-053, get rows of their own.
