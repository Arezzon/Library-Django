# Feature Specification: Remaining Technical Debt Epic

**Feature Branch**: `004-tech-debt-jira-epic` (spec directory; no git branch was created)

**Created**: 2026-11-03

**Status**: Published 2026-11-03 (KAN-90)

**Input**: User description: "Create Epic on Jira for current sprint to deal with rest of tech debt, for every open item in tech debt create Task or Bug in this Epic and assign corespondent people, in description write what assigne should do or if this is decision TD then decision subject and options. Also in description include feedback instruction: when comleted if this is task required code change then assigne should move task to In Review and leave link to PR that closes this Task in comments so latter you can review all of them and update tech debt using this as evidence, if this is decision Task then assigne should answer with decision in comments and place task In Review."

## User Scenarios & Testing *(mandatory)*

The [technical debt register](../../docs/shared/debt-register.md) has 16 open items. None is P1, and
none has an issue in the team's Jira project (KAN) that groups the work. Four have a Jira bug of their
own. The register's target sprints for the items are Lab 5 · Testing, the sprint that started
on 2026-11-03, and Final · Product v2.0. This feature turns the open items into assigned Jira work under
one Epic in the active sprint, and sets one way for owners to report back, so that the register can be
updated from the answers.

### User Story 1 - Each owner gets an assigned issue for their open item (Priority: P1)

The technical lead, @fazelukario, wants every open register item to be an issue in one Epic in the
active sprint. Each issue is assigned to the item's owner and tells them what to do, or what to decide,
without their having to read the register.

**Why this priority**: an item with no assigned issue in the sprint gets no time, and the register's
target sprint for eight of the 16 items is the sprint now running.

**Independent Test**: open the Epic and compare its issues with the register's open rows: one issue per
row, and each issue's assignee, type and description match the row.

**Acceptance Scenarios**:

1. **Given** the register has 16 open items, **When** the Epic is published, **Then** it holds exactly
   one issue for each of them, and no issue for a closed item.
2. **Given** a change item such as TD-22, **When** its owner opens the issue, **Then** the description
   says what is wrong, what to change, where, and what counts as done.
3. **Given** a decision item such as TD-26, **When** its owner opens the issue, **Then** the
   description states what is to be decided, who decides, and at least two options with what each
   leads to.
4. **Given** the drafts of the Epic and its issues, **When** the technical lead has not approved them,
   **Then** nothing is published in Jira.
5. **Given** the published issues, **Then** every one of them is in the active sprint.

---

### User Story 2 - Owners report back in a form the register can use (Priority: P1)

Every issue tells its assignee how to report completion. For a change, they move the issue to In
Review and comment with the link to the pull request that closes it. For a decision, they comment
with their decision and move the issue to In Review.

**Why this priority**: the register closes an item only with linked evidence, and accepts one only with
the product owner's decision, its reason and a review date. Without a fixed format, each answer needs a
follow-up conversation.

**Independent Test**: read any issue. It carries exactly one feedback instruction, and that instruction
matches the issue's kind. For a new issue, the instruction ends the description. For a reused issue, it
is in the comment added under FR-013.

**Acceptance Scenarios**:

1. **Given** a change issue, **When** the assignee has the pull request that closes it, **Then** the
   instruction tells them to comment with its link and move the issue to In Review.
2. **Given** a decision issue, **When** the assignee has decided, **Then** the instruction tells them
   to comment with the chosen option, its reason and, when the debt is accepted, a review date, and then
   to move the issue to In Review.
3. **Given** either kind, **Then** the instruction says that the issue stays in In Review until the
   technical lead has updated the register, and who then moves it to Done.

---

### User Story 3 - The technical lead updates the register from the answers (Priority: P2)

As issues reach In Review, the technical lead reviews each one and updates its register row, using the
linked pull request or the decision comment as the evidence.

**Why this priority**: the register is the record the team keeps, and the Epic is the means of
updating it. The review can only start once owners answer, so it follows Stories 1 and 2.

**Independent Test**: take one issue in In Review whose pull request is merged, and update its register
row using only what the issue holds.

**Acceptance Scenarios**:

1. **Given** a change issue in In Review whose pull request is merged, **When** it is reviewed,
   **Then** its register row becomes `closed`, links the pull request and the issue, and the date at the
   top of the register changes.
2. **Given** a change issue in In Review whose pull request is not merged, **When** it is reviewed,
   **Then** the row stays `open`, and the issue gets a comment saying what is still missing.
3. **Given** a decision issue in In Review, **When** it is reviewed, **Then** the register row records
   the decision: `accepted`, with the decision, its reason and a review date, or still `open` with the
   new plan, its owner and its target sprint.
4. **Given** an issue in In Review without the comment its instruction asks for, **When** it is
   reviewed, **Then** the issue gets a comment asking for it, and the register row does not change.

---

### Edge Cases

- **An item already has a Jira issue**: TD-29 (KAN-81), TD-34 (KAN-78), TD-36 (KAN-79) and TD-37
  (KAN-80) were filed as bugs before this feature. They are reused under the Epic (FR-013). Three of
  them belong to teammates. Placing those under the Epic and in the sprint, and commenting on them, are
  shown in the draft review like the new issues. Their status does not change (FR-012).
- **A reused issue's type disagrees with its kind**: KAN-80 is a Bug, but TD-37 is now a decision
  (FR-014). The reused issue keeps its type, and the comment added under FR-013 frames the decision.
- **The register's owner and the existing issue's assignee differ**: TD-36's owner is @fazelukario,
  but KAN-79 is assigned to another team member. TD-37's owner is @fazelukario, and KAN-80 is assigned
  to the technical lead, but its plan starts with the product owner's decision. The draft shows each mismatch, and the
  technical lead chooses the assignee.
- **An item has two owners**: TD-25 is owned by @Arezzon with @anastasiiaMirovska. A Jira issue has one
  assignee, so it goes to the first-named owner, and the description names the second as consulted.
- **A decision is followed by a change**: TD-17, TD-19, TD-25 and TD-37 need a decision before any code
  changes. TD-18 needs a change only if the search text is dropped. See FR-014.
- **The owner chooses how to fix the item**: TD-20's plan is "run them in CI, or remove them". The QA
  lead both chooses and does the work, so it is a change issue whose description gives both options.
- **The plan conflicts with the constitution**: TD-24's plan is to build the CSS. The constitution
  allows a frontend build step only through a feature spec that justifies it. The description says so,
  so that the assignee raises it before writing code.
- **The register has a wrong cross-reference**: TD-37's row says "Depends on TD-37". It means TD-36
  (KAN-79, the 404 page): the [tasks](../003-priority-tech-debt/tasks.md) numbered KAN-79 and KAN-80 as
  TD-37 and TD-38 before the register renumbered them. TD-37's issue names the correct dependency, and
  the row is corrected at its review.
- **Register targets later than this sprint**: eight items target Final · Product v2.0. The request
  pulls all of them into the active sprint. Their target sprint in the register is updated when their
  rows are next changed.
- **The register changes between drafting and publishing**: the register is read again before
  publishing. An item closed in the meantime gets no issue, and a new open item gets a draft.
- **The Epic cannot be placed in a sprint**: if Jira does not allow it, the Epic's start and due dates
  are set to the sprint's dates, and its issues are in the sprint.
- **One pull request closes several items**: each issue links the same pull request, and each row cites
  it.
- **The sprint ends with issues not in In Review**: their rows stay `open`, with the reason, and the
  team's usual sprint planning carries the issues over. This feature moves no issue between sprints.

## Requirements *(mandatory)*

### Functional Requirements

**The Epic**

- **FR-001**: The KAN project MUST have one Epic for the remaining technical debt. It is assigned to the
  technical lead, @fazelukario, and linked to the active sprint, Lab 5 · Testing (2026-11-03 to
  2026-11-17).
- **FR-002**: The Epic's description MUST state its purpose, link the register at the commit the issues
  were drafted from, list its issues by register ID, and repeat the feedback rules (FR-009) and the
  review procedure (FR-015 and FR-016).

**The issues**

- **FR-003**: The Epic MUST hold exactly one issue for each register item whose status is `open` when
  the issues are published. That is 16 items now, listed in the [issue set](#issue-set). Closed items
  get no issue.
- **FR-004**: An issue MUST be a Bug when its item describes behavior that is wrong today, and a Task
  otherwise, including every decision.
- **FR-005**: Each issue MUST be of one kind, stated at the top of its description. A **change** is done
  when the pull request that closes it is merged. A **decision** is done when the decision is recorded.
- **FR-006**: Each issue MUST be assigned to the Jira account of its item's owner in the register,
  except where the technical lead chooses otherwise at the draft review (see Edge Cases). Its summary
  MUST start with the register ID, for example "TD-22", and its Jira priority MUST follow the register's:
  Medium for P2 and Low for P3. Every issue MUST be in the active sprint.
- **FR-007**: A change issue's description MUST state:
  - what is wrong and why it matters;
  - what to do, from the register's plan;
  - where, using the files the register names;
  - what counts as done: tests in the owning app that fail without the change, and a pull request that
    follows the repository's rules;
  - the item's register ID, priority and source.
- **FR-008**: A decision issue's description MUST state:
  - the decision as a question;
  - who decides, and who is consulted;
  - at least two options, with what each leads to. They include the register's plan and, where the
    register's rules allow it, accepting the debt;
  - what the answer must contain: the chosen option or another one, its reason, and a review date if
    the debt is accepted.

**Feedback and review**

- **FR-009**: Every new issue's description MUST end with the feedback instruction for its kind. A reused
  issue gets it in a comment (FR-013).
  - **Change**: once a pull request that closes the issue exists, comment with its link and move the
    issue to In Review.
  - **Decision**: comment with the decision, its reason and, when the debt is accepted, a review date,
    then move the issue to In Review.
  - **Both kinds**: do not move the issue to Done. The technical lead reviews it, updates the register,
    and comments with the link to that update; the assignee then moves the issue to Done. If something
    is missing, the technical lead comments on what it is, and the assignee moves the issue back to In
    Progress.
- **FR-010**: The Epic's and the issues' texts MUST be written in Ukrainian, like the team's other KAN
  issues. Code identifiers, file paths, status names, register IDs and people's handles stay as they
  are.
- **FR-011**: Nothing MUST be published in Jira before the technical lead has seen the full text of the
  Epic and of every issue, with its type, assignee and priority, and has approved it. Changes the
  technical lead asks for are made before publishing.
- **FR-012**: The person or agent publishing the Epic MUST NOT change the status of any issue assigned
  to someone else. The technical lead's own issues are moved only with the technical lead's approval of each
  move.
- **FR-013**: An item that already has an open Jira issue MUST reuse it instead of getting a new one.
  This applies to TD-29 (KAN-81), TD-34 (KAN-78), TD-36 (KAN-79) and TD-37 (KAN-80).
  - The issue is placed under the Epic and in the active sprint.
  - Its description and type stay as written.
  - A comment adds what its description lacks: the kind, the feedback instruction (FR-009) and, for a
    decision, the content FR-008 requires. The comment is drafted and approved like the descriptions
    (FR-011).
  - Its assignee changes only if the technical lead chooses so at the draft review.
- **FR-014**: An item that needs a decision before a change MUST get one decision issue. This applies to
  TD-17, TD-18, TD-19, TD-25 and TD-37. The change it may lead to is not filed now:
  - at the item's review (FR-016), the register row gets its new plan;
  - the change then gets a new issue, drafted and approved under FR-011, and placed under the Epic while
    the Epic is open.
- **FR-015**: For each issue in In Review, the reviewer MUST check the evidence before changing the
  register:
  - for a change, that the linked pull request is merged into `main`, its checks passed, and it does
    what the issue asks;
  - for a decision, that the comment comes from the deciding owner and names an option and its reason,
    plus a review date when the debt is accepted.
- **FR-016**: When the evidence holds, the reviewer MUST update the item's register row through a pull
  request:
  - a change becomes `closed`, linking its pull request and its issue;
  - an accepted decision becomes `accepted`, with the decision, its reason and its review date;
  - any other decision stays `open`, with the new plan, its owner and its target sprint.

  The date at the top of the register changes with each update. When the evidence does not hold, the
  reviewer comments on the issue with what is missing and leaves the row unchanged.

### Issue set

The register's open items at `ba90838`, with the type and kind they get under FR-004, FR-005, FR-013 and
FR-014. That gives 12 new issues and 4 reused ones. The decision items name what is to be decided.

| ID    | Item                                                             | Priority | Owner (assignee)                           | Type | Kind                                          | Existing issue |
| ----- | ---------------------------------------------------------------- | -------- | ------------------------------------------ | ---- | --------------------------------------------- | -------------- |
| TD-17 | Copy backups off the Pi automatically                            | P2       | @Arezzon                                   | Task | Decision (where and how often to copy)        | —              |
| TD-18 | Analytics search events keep the search text                     | P2       | @anastasiiaMirovska                        | Task | Decision (keep the search text or drop it)    | —              |
| TD-19 | The interface is in English only                                 | P2       | @anastasiiaMirovska                        | Task | Decision (which pages and messages first)     | —              |
| TD-20 | Browser tests under `library/` do not run in CI                  | P2       | @Dima22820                                 | Task | Change (run them in CI, or remove them)       | —              |
| TD-21 | P2 search and demand forecasting                                 | P2       | @Arezzon                                   | Task | Decision (accept or plan)                     | —              |
| TD-22 | Signing out works through a GET request                          | P3       | @fazelukario                               | Bug  | Change                                        | —              |
| TD-23 | The admin user form shows the password hash as editable          | P3       | @fazelukario                               | Bug  | Change                                        | —              |
| TD-24 | Pages load Tailwind and fonts from third-party servers           | P3       | @OLEkSandrKoniaiev                         | Task | Change (the constitution limits the approach) | —              |
| TD-25 | Audit entries have no retention period                           | P2       | @Arezzon, with @anastasiiaMirovska         | Task | Decision (the retention period)               | —              |
| TD-26 | Account creation times before PR 3 are unreliable                | P3       | @Arezzon                                   | Task | Decision (accept or plan)                     | —              |
| TD-29 | Saving a book with an empty title creates a book without a name  | P2       | @OLEkSandrKoniaiev                         | Bug  | Change                                        | KAN-81         |
| TD-31 | The constitution and `AGENTS.md` omit `ai` from the test command | P3       | @fazelukario                               | Task | Change                                        | —              |
| TD-34 | `remove_authors` removes every author                            | P3       | @OLEkSandrKoniaiev                         | Bug  | Change                                        | KAN-78         |
| TD-35 | A page that forgets its access check fails no test               | P3       | @fazelukario                               | Task | Change                                        | —              |
| TD-36 | An unknown address shows Django's plain "Not Found" page         | P3       | @fazelukario (KAN-79 has another assignee) | Bug  | Change                                        | KAN-79         |
| TD-37 | Staff pages answer a reader with 403 instead of 404              | P3       | @fazelukario; the decision is @Arezzon's   | Bug  | Decision (hide staff pages from readers?)     | KAN-80         |

### Key Entities

- **Register item**: a row of the debt register, with its ID, item, source, priority, owner, status,
  plan and target sprint. The register is the record. The Epic only carries the work.
- **Epic**: the Jira container for this round of debt work, linked to the active sprint. It explains
  the rules and lists its issues.
- **Debt issue**: one Jira Task or Bug for one register item. It has a kind (change or decision), an
  assignee, a priority and the feedback instruction for its kind.
- **Feedback comment**: the assignee's answer on the issue. For a change, it is the link to the pull
  request that closes the issue. For a decision, it is the chosen option, its reason and, when the debt
  is accepted, a review date.
- **Register update**: a pull request that changes register rows using feedback comments as evidence,
  and cites the issues it closes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 16 open register items are covered by the Epic, each by exactly one issue: 12 new
  issues and 4 reused ones. No closed item has an issue, and no item has two.
- **SC-002**: Every issue is assigned and is in the active sprint. Its assignee is the register owner,
  or the person the technical lead chose at the draft review.
- **SC-003**: Every issue carries exactly one feedback instruction, and it matches the issue's kind. For
  a new issue, it ends the description. For a reused issue, it is in the comment added under FR-013.
- **SC-004**: Nothing was published in Jira that the technical lead had not seen and approved.
- **SC-005**: At the draft review, each description can be acted on without opening the register. It
  names the item, the action or decision, and what counts as done.
- **SC-006**: At least 90% of the issues that reach In Review can be resolved in the register from the
  issue and its comments alone, with no question to the assignee.
- **SC-007**: Within 2 days of an issue reaching In Review, either its register row is updated or the
  issue has a comment saying what is missing.

## Assumptions

- **Current sprint**: the active sprint of board 1, Lab 5 · Testing, from 2026-11-03 to 2026-11-17.
- **Open items**: the rows marked `open` in `docs/shared/debt-register.md` on `main` at `ba90838`. None
  is `blocked` or `accepted`.
- **Owners in Jira**: the register names owners by GitHub handle. The technical lead confirms which Jira
  account belongs to each handle at the draft review. Repository files, this spec included, name people
  only by handle.
- **Done**: the technical lead reviews the issues. Assignees move their own issues to In Review and,
  after the review, to Done, as the team's Jira practice expects.
- **Review pace**: issues are reviewed as they reach In Review, not in one pass. Register updates follow
  the repository's pull request rules.
- **Language**: the texts are in Ukrainian, like the team's existing KAN issues and sprint names.
- **Out of scope**: doing the debt work itself, changing the register before the review, and KAN-82
  (deleting an account deletes its loans and reservations). KAN-82 is a Jira bug, not a register item.
