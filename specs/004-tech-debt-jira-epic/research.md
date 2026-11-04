# Research: Remaining Technical Debt Epic

All facts were read on 2026-11-03: Jira read-only, and the repository at `main` `ba90838` plus the
later merge of #64, which is noted where it matters. No unknowns remain from the Technical Context.

## R1. Who gets which issue

**Decision**: map register handles to Jira accounts using the evidence below, and look each account
up with `listJiraIssueAssignableUsers` when publishing. Repository files hold handles only, never
names or account IDs.

| Handle              | Role                | Evidence                                                                                                               |
| ------------------- | ------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| @fazelukario        | technical lead      | The connector's own account, `atlassianUserInfo`                                                                       |
| @Arezzon            | product owner       | Owns the Jira site and reports the team's issues. KAN-72 to KAN-74 (TD-06 to TD-08, owner @Arezzon) are this account's |
| @OLEkSandrKoniaiev  | technical architect | Assignee of KAN-77, KAN-78 and KAN-81. KAN-81's description names `OLEkSandrKoniaiev` as the assignee                  |
| @Dima22820          | QA lead             | Held KAN-21 (TD-05, owner @Dima22820). Assignee of the QA tasks KAN-85 and KAN-86                                      |
| @anastasiiaMirovska | business analyst    | Assignee of KAN-36, the release documentation; the display name matches the handle                                     |

KAN-79 (TD-36) is assigned to @myrrhfawn, senior engineer, who owns none of the items above. The draft
review asks the technical lead whether TD-36 stays with @myrrhfawn or moves to @fazelukario, the
register's owner (spec Edge Cases).

**Alternatives considered**: looking accounts up by name. That would put names in the repository, and
an account ID is unambiguous.

## R2. The sprint and the Epic

**Decision**: create the Epic with `assignToSprint: "5"`.

- If the result has `sprintAssignment.assigned: false`, the Epic gets start date 2026-11-03 and due
  date 2026-11-17 instead, as the spec's edge case says.
- Every child issue is created with `assignToSprint: "5"`.
- KAN-78, the one reused issue not in sprint 5, is moved there with `transitionJiraIssue` and
  `sprintId: 5`, with no transition.

**Facts**:

- Sprint 5 is "Лаб 5 · Тестування" on board 1. It is active from 2026-11-03T19:10Z to
  2026-11-17T15:00Z. Sprint 4 is closed.
- KAN is team-managed (`simplified: true`). Team-managed boards usually show Epics in a panel, not as
  sprint items, so the Epic may not take a sprint.
- KAN-79, KAN-80 and KAN-81 are already in sprint 5. KAN-78 is in no sprint.

**Alternatives considered**: a sprint field on the Epic alone, without its children. Rejected, because
the board plans the children.

## R3. Jira operations

**Decision**:

| Step                              | Operation                   | Fields                                                                                                                                                                         |
| --------------------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Create the Epic                   | `createJiraIssue`           | `issueType: "Epic"`, summary, description (Markdown), `assignee`, `labels: ["tech-debt"]`, `assignToSprint: "5"`                                                               |
| Create a change or decision issue | `createJiraIssue`           | `issueType: "Task"` or `"Bug"`, `parent: <Epic key>`, `assignee`, `priority` (`Medium` for P2, `Low` for P3), `labels: ["tech-debt", "td-NN"]`, `assignToSprint: "5"`          |
| Reuse an issue                    | `editJiraIssue`             | `fields.parent: {"key": <Epic key>}`, and `labels` as the full existing list plus `tech-debt` and `td-NN`. Labels are set, not appended, so the existing ones must be sent too |
| Put KAN-78 in the sprint          | `transitionJiraIssue`       | `sprintId: 5`, with no transition                                                                                                                                              |
| Comment on a reused issue         | `addOrEditJiraIssueComment` | Markdown body                                                                                                                                                                  |
| List the keys in the Epic         | `editJiraIssue` on the Epic | description, once the children have keys                                                                                                                                       |

`transitionJiraIssue` is never called with a transition (FR-012). Text is sent as Markdown, which the
connector converts. The team's issues use Markdown headings and lists, which convert cleanly.

**Existing labels of the reused issues**:

| Issue  | Labels                                                                |
| ------ | --------------------------------------------------------------------- |
| KAN-81 | `book-validation`, `github-issue-62`, `librarysys-v2`, `td-29`        |
| KAN-78 | `book-model`, `code-review-2026-10-30`, `librarysys-v2`, `reproduced` |
| KAN-79 | `librarysys-v2`, `manual-test-2026-11-01`, `ui`                       |
| KAN-80 | `access-control`, `librarysys-v2`, `manual-test-2026-11-01`, `ui`     |

KAN-81 already has `td-29`, which is the convention the new labels follow.

## R4. Language, format and approval

**Decision**:

- The texts are in Ukrainian, following KAN-36, KAN-78 to KAN-82 and the sprint names.
- Code identifiers, paths, status names (In Review, Done, In Progress), register IDs and handles stay in
  their original form.
- Each Jira text is one file in `drafts/`, named `epic.md`, `TD-NN.md` (new issues) or `TD-NN-comment.md`
  (reused issues). Each file starts with a field block: type, summary, assignee, priority, labels, parent
  and sprint.
- The technical lead reviews the files and approves them all at once or one by one. Requested changes
  are made in the files before anything is published (FR-011), and the published text is the approved
  file verbatim.

**Alternatives considered**: drafts only in chat. Rejected: 18 texts are too long for one message, and
the files keep a record of what was approved.

## R5. Decision items: questions and options

Each decision issue states the question, who decides and who is consulted, and the options. The
options come from the register, ADRs and code. Each is listed with what it leads to.

| ID    | Question                                                                             | Decides (consulted)                 | Options and what each leads to                                                                                                                                                                                                                                                                                                                                                                                                                                                    | Sources                                                                                                                                                                                                                                                                                                                                                                                             |
| ----- | ------------------------------------------------------------------------------------ | ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TD-17 | Where, and how often, should backups be copied off the Pi automatically, and when?   | @Arezzon (@fazelukario as operator) | (a) To cloud object storage. Needs an account, credentials in the stack's environment and encryption, because backups hold password hashes and personal data. (b) To another machine the team controls. Needs a machine that is always reachable, and a key. (c) Keep the weekly manual copy until the site holds real readers' data: `accepted`, with that as the review trigger and a date. (a) and (b) lead to a change in the backup service, ADR 0003 and the operator guide | [ADR 0003](../../docs/adr/0003-database-backups.md), "Consequences" and "Alternatives considered"                                                                                                                                                                                                                                                                                                   |
| TD-18 | Should analytics keep the text of each catalog search?                               | @anastasiiaMirovska (@Arezzon)      | (a) Keep it, for analysis of search quality: `accepted`, with the reason and a review date, and the text falls under the retention set by TD-25 or a period of its own. (b) Drop it, and record only that a search happened, with its author filter. That is a change to `library/events/searches.py` and the analytics activity table, and recommendations lose the search signal they read today                                                                                | `library/events/searches.py:23` stores `query.strip()[:200]`. `library/book/recommendation_data.py:86` reads it for recommendations, and `library/events/templates/events/_analytics_content.html:47` shows it to librarians. [Research R19 of 003](../003-priority-tech-debt/research.md#r19-keeping-secrets-and-search-text-out-of-logs-and-audit-entries-pr-8): logs already hold no search text |
| TD-19 | Which pages and messages get Ukrainian first, and which language is the default?     | @anastasiiaMirovska (@Arezzon)      | (a) The reader's path first: catalog, book page, sign-in, sign-up, reservations, errors. Staff pages follow. (b) The whole interface at once. (c) Only the messages readers see from the system: errors, confirmations, emails if any. Any option leads to a translation change. `LANGUAGE_CODE` is `en-us` today, and `USE_I18N` is on                                                                                                                                           | `library/library/settings.py:217-222`                                                                                                                                                                                                                                                                                                                                                               |
| TD-21 | What is left of "P2 search and demand forecasting" now that forecasting has shipped? | @Arezzon                            | Demand forecasting was merged in #64 (KAN-35, Done) after the register's last update, so that half can close with #64 as evidence. For "P2 search": (a) accept it as out of scope for v1.0 debt, with the reason and a review date; or (b) name the search work meant and plan it, with an owner and a target sprint. The register does not define "P2 search"; the answer should say what it covers                                                                              | Register TD-21; KAN-35; `library/events/forecast.py` (#64); 003 spec, FR-055                                                                                                                                                                                                                                                                                                                        |
| TD-25 | How long are audit entries kept?                                                     | @Arezzon (@anastasiiaMirovska)      | (a) A fixed period, for example 1 year, after which entries are deleted on a schedule: a change to the `audit` app and ADR 0002. (b) Kept while the account exists, plus a period after its deletion: the same change, keyed to deletion. (c) Kept indefinitely: `accepted`, with the reason and a review date. Audit entries hold names in `actor_label` and `target_label`, which KAN-82 also notes. The constitution treats them as part of the business record                | `library/audit/models.py`; [research of 003](../003-priority-tech-debt/research.md), "Retention"; KAN-82                                                                                                                                                                                                                                                                                            |
| TD-26 | Is it accepted that account creation times before PR 3 cannot be trusted?            | @Arezzon                            | (a) Accept: `accepted`, with the reason (the values are lost and cannot be recovered) and a review date. (b) Mark them: show "unknown" for accounts created before PR 3's deployment, which is a change. `created_at` has used `auto_now_add` since #39                                                                                                                                                                                                                           | `library/authentication/models.py:118`; [#39](https://github.com/Arezzon/Library-Django/pull/39)                                                                                                                                                                                                                                                                                                    |
| TD-37 | Should staff pages be hidden from readers?                                           | @Arezzon (@fazelukario)             | (a) Hide them: change FR-004 first. Then `library/authentication/decorators.py` answers readers 404 in one place, using TD-36's 404 page, and the tests that expect 403 change. Also decide whether the API keeps 403. (b) Keep 403, as FR-004 says, which tells the reader the action is not permitted: KAN-80 closes as won't-do, and TD-37 becomes `accepted` with the reason                                                                                                  | KAN-80; [003 spec FR-004](../003-priority-tech-debt/spec.md); register TD-37                                                                                                                                                                                                                                                                                                                        |

**Register correction**: TD-37's row says "Depends on TD-37". Read TD-36 (KAN-79): the 003 tasks gave
KAN-79 and KAN-80 the numbers TD-37 and TD-38 before the register renumbered them
([tasks.md:1794](../003-priority-tech-debt/tasks.md)). KAN-80's comment names TD-36 (KAN-79).

## R6. Change items: facts for the descriptions

| ID    | Where                                                                                                                                                                                                     | What done means beyond tests and a PR                                                                                                                                                                                                                                                                    | Issue        |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| TD-20 | `library/test_selenium_auth_pytest.py`, `library/test_selenium_auth_unittest.py`. CI runs `manage.py test authentication author book order events audit ai`, so these files at the project root never run | Either CI runs them (CI already runs Playwright for the accessibility check), or they are deleted with the reason in the PR. The QA lead chooses                                                                                                                                                         | New Task     |
| TD-22 | `library/authentication/views.py:113`, `logout`. It is linked with GET from `library/library/templates/base.html:172` and `:263`                                                                          | Signing out uses a POST form with CSRF. GET no longer signs out. Both links become forms that still meet WCAG 2.2 AA                                                                                                                                                                                     | New Bug      |
| TD-23 | `library/authentication/admin.py:38`, where the `password` field is in `fieldsets`                                                                                                                        | The hash is shown read-only, with Django's password widget and its link to the change form. Saving the form leaves the password unchanged                                                                                                                                                                | New Bug      |
| TD-24 | `library/library/templates/base.html:13-16`: the Tailwind play CDN and Google Fonts                                                                                                                       | No page loads assets from third-party servers. Self-hosted fonts are a static file served by WhiteNoise. Building the CSS adds a frontend build step, which the constitution allows only through its own feature spec, so raise it before writing code. The accessibility check still finds 0 violations | New Task     |
| TD-29 | Done in KAN-81's description                                                                                                                                                                              | As KAN-81 says                                                                                                                                                                                                                                                                                           | Reuse KAN-81 |
| TD-31 | `AGENTS.md:4` and the constitution's workflow item 4 omit `ai`. `.github/workflows/docker-build.yml:155,166` include it                                                                                   | `AGENTS.md` changes in the same PR as a PATCH amendment through `/speckit-constitution`                                                                                                                                                                                                                  | New Task     |
| TD-34 | Done in KAN-78's description                                                                                                                                                                              | As KAN-78 says                                                                                                                                                                                                                                                                                           | Reuse KAN-78 |
| TD-35 | `library/authentication/test_routes.py:122`, `WebRouteAccessTests`, which lists routes by hand                                                                                                            | A test walks every web route and fails when one is missing from the list. The 6 missing routes are added                                                                                                                                                                                                 | New Task     |
| TD-36 | Done in KAN-79's description                                                                                                                                                                              | As KAN-79 says. The comment adds that TD-37 waits on it                                                                                                                                                                                                                                                  | Reuse KAN-79 |

**Type rule** (FR-004): TD-22 and TD-23 are wrong behavior today, so they are Bugs. TD-20, TD-24,
TD-31 and TD-35 are gaps in process or tests, so they are Tasks. The reused bugs keep their type,
including KAN-80, which is a decision (spec Edge Cases).

## R7. Register freshness

**Decision**: just before publishing, read `docs/shared/debt-register.md` on `origin/main` again. If an
item closed, its draft is dropped. If a row was added, a draft is written and approved before
publishing. The register's "Updated" line still says 2026-11-02, and #64 (forecasting) merged after it,
so TD-21's draft states that.

**Out of scope here**: KAN-82 (deleting an account deletes its loans), and the register rows that #64
may close. Both go to the first register update at review.
