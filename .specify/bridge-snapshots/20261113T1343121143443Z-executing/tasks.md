---

description: "Task list for the Remaining Technical Debt Epic"
---

# Tasks: Remaining Technical Debt Epic

**Input**: Design documents from `specs/004-tech-debt-jira-epic/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: no automated tests. The feature changes no application code. Checks are the draft
validations and the JQL checks of [quickstart.md](quickstart.md), which run as tasks below.

**Organization**: tasks are grouped by user story. Stories 1 and 2 are both P1 and ship in one publish:
every Jira text carries its feedback instruction from the start, because adding it later would mean
editing descriptions that teammates own. They share Phase 3.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story the task serves (US1, US2, US3)

## Conventions for every task

- **Paths**:
  - `FEATURE` is `specs/004-tech-debt-jira-epic`.
  - `DRAFTS` is `specs/004-tech-debt-jira-epic/drafts`.
  - `README` is `specs/004-tech-debt-jira-epic/drafts/README.md`.
- **Jira site**: the `cloudId` that `getAccessibleAtlassianResources` returns, project `KAN`, board 1, sprint 5
  ("Лаб 5 · Тестування", 2026-11-03 to 2026-11-17).
- **Accounts**: look each handle's Jira account up with `listJiraIssueAssignableUsers`, using the
  evidence in [research.md R1](research.md#r1-who-gets-which-issue). Account IDs are not recorded
  in the repository.
- **Drafts**: each draft follows [contracts/issue-texts.md](contracts/issue-texts.md): an HTML-comment
  field block that is not published, then the Ukrainian text that is.
  - Links in a Jira text are absolute GitHub URLs at the snapshot commit recorded in T003:
    `https://github.com/Arezzon/Library-Django/blob/<commit>/<path>`.
  - People are named by handle. No real names, emails or secrets appear in any repository file or Jira
    text.
- **Approval**: nothing is created, edited or commented in Jira without the technical lead's approval
  of the exact text (FR-011).
- **Status changes**: `transitionJiraIssue` is never called with a transition. Assignees move their
  own issues (FR-012).

---

## Phase 1: Setup

**Purpose**: a working branch, the drafts folder and a fresh view of the register.

- [X] T001 Create the local branch `004-tech-debt-jira-epic` from a freshly fetched `origin/main`,
  following `.agents/skills/fresh-feature-branch/SKILL.md`. Keep the untracked `specs/004-tech-debt-jira-epic/`
  files, and commit nothing (commits happen only on request, T050).
- [X] T002 Create `specs/004-tech-debt-jira-epic/drafts/README.md` with these empty sections, in order:
  "Register snapshot", "Reused issues before publishing", "Accounts", "Approval log", "Published",
  "Checks", "Reviews".
- [X] T003 Run `git fetch origin` and `git show origin/main:docs/shared/debt-register.md`. Record the
  `origin/main` commit SHA and the IDs of every row whose status is `open` under "Register snapshot" in
  `specs/004-tech-debt-jira-epic/drafts/README.md`. The expected IDs are TD-17 to TD-26, TD-29, TD-31,
  TD-34, TD-35, TD-36 and TD-37. That is 16 IDs, matching
  [the issue set](data-model.md#the-issue-set).
  - If the set differs, stop. Drop the drafts of closed items, add rows for new ones to the issue set in
    `specs/004-tech-debt-jira-epic/data-model.md` and `spec.md`, and tell the technical lead before
    continuing (research R7).

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the facts and the shared text that every draft and every publishing step relies on.

**CRITICAL**: no drafting or publishing starts until this phase is complete.

- [X] T004 [P] Read KAN-78, KAN-79, KAN-80 and KAN-81 with `getJiraIssue`. Under "Reused issues before
  publishing" in `specs/004-tech-debt-jira-epic/drafts/README.md`, record each issue's status, sprint,
  assignee (as a handle, from research R1), priority, parent and full label list.
  - Expected: every status is `Idea`; KAN-78 has no sprint and the other three are in sprint 5; none has
    a parent.
  - Expected labels: those listed in research R3.
- [X] T005 [P] Confirm that every assignee account can be assigned in KAN. Find
  `listJiraIssueAssignableUsers` with `discover`, run it with `executeRead` for project `KAN`, and check
  the six account IDs of research R1 plus @myrrhfawn's. Record "assignable: yes/no" per handle under
  "Accounts" in `specs/004-tech-debt-jira-epic/drafts/README.md`, without names. Stop and tell the
  technical lead if any account cannot be assigned.
- [X] T006 [P] Check for duplicates with `searchJiraIssuesUsingJql`:
  `project = KAN AND labels in (tech-debt, td-17, td-18, td-19, td-20, td-21, td-22, td-23, td-24, td-25, td-26, td-31, td-35)`.
  The expected result is none. Also check that no Epic's summary contains "Технічний борг: решта". Record
  the result under "Checks" in `specs/004-tech-debt-jira-epic/drafts/README.md`, and stop if an existing
  issue covers an item.
- [X] T007 Copy the two feedback blocks from [contracts/issue-texts.md](contracts/issue-texts.md),
  verbatim and without the surrounding code fences:
  - the change block into `specs/004-tech-debt-jira-epic/drafts/_feedback-change.md`;
  - the decision block into `specs/004-tech-debt-jira-epic/drafts/_feedback-decision.md`.

  Each file starts at `## Як звітувати` and ends with a single newline.

**Checkpoint**: the register snapshot, the reused issues' state, the accounts and both feedback blocks
are recorded. Drafting can start.

---

## Phase 3: User Stories 1 and 2 — assigned issues that carry their feedback instruction (P1) MVP

**Goal**:
- **US1**: one issue per open register item, under one Epic in sprint 5, assigned to the item's
  owner, saying what to do or what to decide.
- **US2**: each issue carries the feedback instruction for its kind.

**Independent Test**:
- **US1**: the quickstart "After publishing" table passes. That means 16 issues under the Epic, all in
  sprint 5, all assigned, with no stray issues.
- **US2**: each of the 16 issues carries exactly one feedback instruction matching its kind. For a new
  issue it ends the description; for a reused issue it is in the comment.

### Drafting the new issues (US1)

Each task writes the field block and the body in the format for its kind, from
[contracts/issue-texts.md](contracts/issue-texts.md). The body stops before `## Як звітувати`, which
T025 adds. Every new issue's field block has `parent: <Epic key>` and `sprint: 5`.

- [X] T008 [P] [US1] Draft `specs/004-tech-debt-jira-epic/drafts/TD-17.md`.
  - **Fields**:
    - type: Task
    - summary: `TD-17 · Рішення: автоматичне копіювання резервних копій поза Raspberry Pi`
    - assignee: @Arezzon
    - priority: Medium
    - labels: `tech-debt, td-17`
  - **Body**: the decision format.
    - Kind line: `**TD-17** · пріоритет P2 · джерело: FR-055 (специфікація 003), ризик R7 · вид роботи: **рішення**`.
    - The question, the decider @Arezzon, consulted @fazelukario (operator), and options (a) to (c) from
      research R5's TD-17 row.
    - Context: ADR 0003 (link) says that losing the Pi can cost up to a week of data, and that the copy
      was deferred for lack of a destination and credentials.
- [X] T009 [P] [US1] Draft `specs/004-tech-debt-jira-epic/drafts/TD-18.md`.
  - **Fields**:
    - type: Task
    - summary: `TD-18 · Рішення: чи зберігати текст пошукових запитів в аналітиці`
    - assignee: @anastasiiaMirovska
    - priority: Medium
    - labels: `tech-debt, td-18`
  - **Body**: the decision format.
    - Kind line with P2 and source `FR-055 (специфікація 003)`.
    - Decider @anastasiiaMirovska, consulted @Arezzon. Options (a) keep and (b) drop, from research R5's
      TD-18 row.
    - Context: the three code locations (store, recommendations, the librarians' activity table), each
      linked, and the fact that logs already hold no search text.
- [X] T010 [P] [US1] Draft `specs/004-tech-debt-jira-epic/drafts/TD-19.md`.
  - **Fields**:
    - type: Task
    - summary: `TD-19 · Рішення: які сторінки й повідомлення перекладати українською першими`
    - assignee: @anastasiiaMirovska
    - priority: Medium
    - labels: `tech-debt, td-19`
  - **Body**: the decision format.
    - Kind line with P2 and source `FR-055 (специфікація 003)`.
    - Decider @anastasiiaMirovska, consulted @Arezzon. Options (a) to (c) from research R5's TD-19 row,
      plus the question of the default language.
    - Context: `LANGUAGE_CODE = "en-us"` and `USE_I18N = True` in `library/library/settings.py` (linked).
- [X] T011 [P] [US1] Draft `specs/004-tech-debt-jira-epic/drafts/TD-20.md`.
  - **Fields**:
    - type: Task
    - summary: `TD-20 · Браузерні тести в library/ не запускаються в CI`
    - assignee: @Dima22820
    - priority: Medium
    - labels: `tech-debt, td-20`
  - **Body**: the change format.
    - Kind line with P2 and source `FR-055 (специфікація 003), ризик R3`.
    - "Що зробити" gives both options, run them in CI or delete them with the reason in the PR, and says
      the QA lead chooses.
    - "Де" and "Готово, коли" come from research R6's TD-20 row.
- [X] T012 [P] [US1] Draft `specs/004-tech-debt-jira-epic/drafts/TD-21.md`.
  - **Fields**:
    - type: Task
    - summary: `TD-21 · Рішення: що лишилося від «P2 search і прогнозування попиту»`
    - assignee: @Arezzon
    - priority: Medium
    - labels: `tech-debt, td-21`
  - **Body**: the decision format.
    - Kind line with P2 and source `KAN-62`.
    - The facts first: forecasting was merged in #64 (linked) and KAN-35 is Done, so that half closes
      with #64 as evidence at review.
    - Then the question about "P2 search", options (a) and (b) from research R5's TD-21 row, and the
      request to say what "P2 search" covers.
- [X] T013 [P] [US1] Draft `specs/004-tech-debt-jira-epic/drafts/TD-22.md`.
  - **Fields**:
    - type: Bug
    - summary: `TD-22 · Вихід із системи працює через GET-запит замість POST-форми`
    - assignee: @fazelukario
    - priority: Low
    - labels: `tech-debt, td-22`
  - **Body**: the change format.
    - Kind line with P3 and source `знахідка під час закриття KAN-62`.
    - "Що не так": any page or link can sign a reader out without their intent, because GET changes
      state.
    - "Де" and "Готово, коли" come from research R6's TD-22 row.
- [X] T014 [P] [US1] Draft `specs/004-tech-debt-jira-epic/drafts/TD-23.md`.
  - **Fields**:
    - type: Bug
    - summary: `TD-23 · Адмінка показує хеш пароля як редаговане текстове поле`
    - assignee: @fazelukario
    - priority: Low
    - labels: `tech-debt, td-23`
  - **Body**: the change format.
    - Kind line with P3 and source `знахідка під час закриття KAN-62`.
    - "Що не так": since #54, a changed value in that field is saved as a new password.
    - "Де" and "Готово, коли" come from research R6's TD-23 row.
- [X] T015 [P] [US1] Draft `specs/004-tech-debt-jira-epic/drafts/TD-24.md`.
  - **Fields**:
    - type: Task
    - summary: `TD-24 · Сторінки завантажують Tailwind і шрифти зі сторонніх серверів`
    - assignee: @OLEkSandrKoniaiev
    - priority: Low
    - labels: `tech-debt, td-24`
  - **Body**: the change format.
    - Kind line with P3 and source `знахідка під час закриття KAN-62`.
    - "Що не так": readers' browsers contact third-party servers on every page.
    - "Де" and "Готово, коли" come from research R6's TD-24 row, including the constitution limit on a
      frontend build step, with a link to `.specify/memory/constitution.md`.
- [X] T016 [P] [US1] Draft `specs/004-tech-debt-jira-epic/drafts/TD-25.md`.
  - **Fields**:
    - type: Task
    - summary: `TD-25 · Рішення: строк зберігання записів аудиту`
    - assignee: @Arezzon
    - priority: Medium
    - labels: `tech-debt, td-25`
  - **Body**: the decision format.
    - Kind line with P2 and source `знахідка під час закриття KAN-62`.
    - Decider @Arezzon, consulted @anastasiiaMirovska. Options (a) to (c) from research R5's TD-25 row.
    - Context: entries keep names after an account is deleted (KAN-82), and the constitution treats
      audit entries as part of the business record.
- [X] T017 [P] [US1] Draft `specs/004-tech-debt-jira-epic/drafts/TD-26.md`.
  - **Fields**:
    - type: Task
    - summary: `TD-26 · Рішення: ненадійні дати створення акаунтів до PR 3`
    - assignee: @Arezzon
    - priority: Low
    - labels: `tech-debt, td-26`
  - **Body**: the decision format.
    - Kind line with P3 and source `знахідка під час закриття KAN-62`.
    - Options (a) accept and (b) mark as unknown, from research R5's TD-26 row.
    - Context: before #39 (linked), every save overwrote the value.
- [X] T018 [P] [US1] Draft `specs/004-tech-debt-jira-epic/drafts/TD-31.md`.
  - **Fields**:
    - type: Task
    - summary: `TD-31 · Конституція й AGENTS.md наводять команду тестів без ai`
    - assignee: @fazelukario
    - priority: Low
    - labels: `tech-debt, td-31`
  - **Body**: the change format.
    - Kind line with P3 and source `знахідка під час закриття KAN-62`.
    - "Де" and "Готово, коли" come from research R6's TD-31 row, with links to `AGENTS.md`, the
      constitution and the two workflow lines.
- [X] T019 [P] [US1] Draft `specs/004-tech-debt-jira-epic/drafts/TD-35.md`.
  - **Fields**:
    - type: Task
    - summary: `TD-35 · Сторінка без перевірки доступу не валить жодного тесту`
    - assignee: @fazelukario
    - priority: Low
    - labels: `tech-debt, td-35`
  - **Body**: the change format.
    - Kind line with P3 and source `знахідка під час закриття KAN-62`.
    - "Що не так" lists the 6 routes missing on 2026-11-02, from the register row: the assistant, For
      You, Saved Books, a book's rating, a book's preferences and signing out.
    - "Де" and "Готово, коли" come from research R6's TD-35 row.

### Drafting the reused-issue comments and the Epic (US1)

- [X] T020 [P] [US1] Draft `specs/004-tech-debt-jira-epic/drafts/TD-29-comment.md` for KAN-81.
  - **Fields**:
    - type: comment on KAN-81
    - labels: existing + `tech-debt` (`td-29` is already there)
    - parent: `<Epic key>`
    - assignee: unchanged @OLEkSandrKoniaiev
  - **Body**: the reused-issue comment format, kind **зміна коду**, P2.
- [X] T021 [P] [US1] Draft `specs/004-tech-debt-jira-epic/drafts/TD-34-comment.md` for KAN-78.
  - **Fields**:
    - type: comment on KAN-78
    - labels: existing + `tech-debt, td-34`
    - parent: `<Epic key>`
    - sprint: 5 (moved by T033)
    - assignee: unchanged @OLEkSandrKoniaiev
  - **Body**: the reused-issue comment format, kind **зміна коду**, P3.
- [X] T022 [P] [US1] Draft `specs/004-tech-debt-jira-epic/drafts/TD-36-comment.md` for KAN-79.
  - **Fields**:
    - type: comment on KAN-79
    - labels: existing + `tech-debt, td-36`
    - parent: `<Epic key>`
    - assignee: `@myrrhfawn or @fazelukario — chosen at T029`
  - **Body**: the reused-issue comment format, kind **зміна коду**, P3, with the line that TD-37 (KAN-80)
    waits on this 404 page.
- [X] T023 [P] [US1] Draft `specs/004-tech-debt-jira-epic/drafts/TD-37-comment.md` for KAN-80.
  - **Fields**:
    - type: comment on KAN-80
    - labels: existing + `tech-debt, td-37`
    - parent: `<Epic key>`
    - assignee: `@Arezzon or @fazelukario — chosen at T029`
  - **Body**: the reused-issue comment format, kind **рішення**, P3, followed by the decision sections.
    - The question "Що вирішити", with decider @Arezzon and consulted @fazelukario.
    - Options (a) hide and (b) keep 403, from research R5's TD-37 row.
    - Context: the conflict with FR-004 of spec 003, and the dependency on TD-36 (KAN-79).
- [X] T024 [US1] Draft `specs/004-tech-debt-jira-epic/drafts/epic.md` in the Epic format of
  [contracts/issue-texts.md](contracts/issue-texts.md#epic-description).
  - **Fields**:
    - type: Epic
    - summary: `Технічний борг: решта пунктів реєстру (Лаб 5)`
    - assignee: @fazelukario
    - labels: `tech-debt`
    - sprint: 5
  - **Body**: link the register at the T003 commit. The "Задачі" table lists all 16 IDs, with each kind
    and assignee from [data-model.md](data-model.md#the-issue-set) and "—" for each key.

### Feedback instruction (US2)

- [X] T025 [US2] Append the matching feedback block, after one blank line, as the last section of
  every draft.
  - Append `specs/004-tech-debt-jira-epic/drafts/_feedback-change.md` to `TD-20.md`, `TD-22.md`,
    `TD-23.md`, `TD-24.md`, `TD-31.md`, `TD-35.md`, `TD-29-comment.md`, `TD-34-comment.md` and
    `TD-36-comment.md`.
  - Append `specs/004-tech-debt-jira-epic/drafts/_feedback-decision.md` to `TD-17.md`, `TD-18.md`,
    `TD-19.md`, `TD-21.md`, `TD-25.md`, `TD-26.md` and `TD-37-comment.md`.
- [X] T026 [US2] Check `specs/004-tech-debt-jira-epic/drafts/epic.md`: its "Як звітувати" and "Як
  перевіряємо" sections must match the Epic format in
  [contracts/issue-texts.md](contracts/issue-texts.md#epic-description) and agree with both feedback
  blocks.

### Validating the drafts (US1, US2)

- [X] T027 [US2] Check that each of the 16 issue drafts in `specs/004-tech-debt-jira-epic/drafts/`
  contains `## Як звітувати` exactly once, and that everything from that heading to the end of the file
  equals `_feedback-change.md` or `_feedback-decision.md`, matching the kind in its kind line. Record
  "16/16" or the failures under "Checks" in `specs/004-tech-debt-jira-epic/drafts/README.md`, and fix any
  failure.
- [X] T028 [US1] Check the drafts against [data-model.md](data-model.md#the-issue-set) and record the
  result under "Checks" in `specs/004-tech-debt-jira-epic/drafts/README.md`:
  - Coverage: the 16 IDs each appear in exactly one draft.
  - Each field block matches the issue set in type, assignee, priority and labels.
  - Each new summary starts with `TD-NN ·`.
  - Each kind line says **зміна коду** or **рішення**, as the issue set says.
  - Nothing private: run `grep -rEn "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"` over the drafts to
    find emails, and check for real names against the names-to-handles mapping kept outside the
    repository. Never write names into a repository file.

### Approval (US1, US2)

- [X] T029 [US1] Present the drafts to the technical lead.
  - Give a link to each file in `specs/004-tech-debt-jira-epic/drafts/`, and offer to print any draft in
    full in chat.
  - Then ask with `AskUserQuestion` about these three things:
    - **Approval**: approve all, approve with changes, or not yet.
    - **TD-36's assignee**: keep @myrrhfawn, or move to @fazelukario.
    - **TD-37's assignee**: @Arezzon, who decides, or keep @fazelukario.
  - Apply requested changes to the drafts and re-run T027 and T028.
  - Record the date, the decision and both assignee choices under "Approval log" in
    `specs/004-tech-debt-jira-epic/drafts/README.md`.
  - **Do not continue until every draft is approved.**

### Publishing (US1, US2)

Publish only the text after the field block's closing `-->`, verbatim, as Markdown.

- [X] T030 [US1] Create the Epic with `createJiraIssue`: `issueType: "Epic"`, the summary, assignee,
  labels and body from `drafts/epic.md`, and `assignToSprint: "5"`.
  - If the response has `sprintAssignment.assigned: false`, set the start date to 2026-11-03 and the
    due date (`duedate`) to 2026-11-17 with `editJiraIssue` (research R2).
  - Record the key and URL under "Published" in `specs/004-tech-debt-jira-epic/drafts/README.md`, and put
    the key in place of `<Epic key>` in every draft's field block.
- [X] T031 [US1] Create the 12 new issues with `createJiraIssue`, in ID order from TD-17 to TD-35, each
  with the type, summary, assignee account, priority, labels and body from its draft, plus
  `parent: <Epic key>` and `assignToSprint: "5"`.
  - Record each key under "Published".
  - If a create fails, run JQL on its `td-NN` label first, so a retry never makes a duplicate. Retry once
    with the corrected input.
  - If `sprintAssignment.assigned` is false, record it, and move the issue with `transitionJiraIssue`
    `sprintId: 5`, with no transition.
- [X] T032 [US1] Reuse KAN-81, KAN-78, KAN-79 and KAN-80 with `editJiraIssue`.
  - Set `fields.parent: {"key": "<Epic key>"}`.
  - Set `labels` to the full list recorded in T004 plus `tech-debt` and the issue's `td-NN`. KAN-81
    keeps its existing `td-29`.
  - Change `assignee` only on KAN-79 and KAN-80, and only to the choices recorded in T029.
  - Do not touch any description.
- [X] T033 [US1] Move KAN-78 into sprint 5 with `transitionJiraIssue`, `sprintId: 5` and no
  transition, so its status stays `Idea`. Record the move under "Published" in
  `specs/004-tech-debt-jira-epic/drafts/README.md`.
- [X] T034 [US2] Post the 4 approved comments with `addOrEditJiraIssueComment` (Markdown):
  - `drafts/TD-29-comment.md` on KAN-81;
  - `drafts/TD-34-comment.md` on KAN-78;
  - `drafts/TD-36-comment.md` on KAN-79;
  - `drafts/TD-37-comment.md` on KAN-80.

  Record each comment ID under "Published" in `specs/004-tech-debt-jira-epic/drafts/README.md`.
- [X] T035 [US1] Fill the "Задачі" table in `specs/004-tech-debt-jira-epic/drafts/epic.md` with the 16
  keys. Show the technical lead the full edited text and wait for approval. Then replace the Epic's
  description with it using `editJiraIssue`, and record the approval under "Approval log".

### Verifying in Jira (US1, US2)

- [X] T036 [US1] Run every check in the "After publishing" table of [quickstart.md](quickstart.md)
  with `searchJiraIssuesUsingJql`, putting the real Epic key in the queries. Record each result under
  "Checks" in `specs/004-tech-debt-jira-epic/drafts/README.md`, and fix anything that fails.
- [X] T037 [US2] Open each of the 16 issues: read the description with `getJiraIssue`, and the
  comments of the 4 reused issues with `listJiraIssueComments`. Confirm that each carries exactly one
  feedback instruction, of its kind, identical to its draft apart from Jira's formatting. Record "16/16"
  under "Checks".
- [X] T038 [US1] Compare the 4 reused issues' statuses with the T004 snapshot. Expected: all still
  `Idea` (FR-012). Record the result under "Checks" in
  `specs/004-tech-debt-jira-epic/drafts/README.md`.

**Checkpoint**: US1 and US2 are delivered. Owners have their issues and know how to report back.
SC-001 to SC-005 can be judged.

---

## Phase 4: User Story 3 — the register is updated from the answers (P2)

**Goal**: each issue that reaches In Review leads to a register update or a comment saying what is
missing, within 2 days (FR-015, FR-016, SC-006, SC-007).

**Independent Test**: take one issue in In Review with a merged PR. Update its register row using only
the issue and its comments, and confirm the row passes the register's rules.

These tasks repeat for each round of reviews, from now to the end of sprint 5. The procedure is in
[contracts/review-and-register.md](contracts/review-and-register.md).

- [ ] T039 [US3] Find issues waiting for review with `searchJiraIssuesUsingJql`:
  `parent = <Epic key> AND status = "In Review" ORDER BY updated ASC`. List each one
  under "Reviews" in `specs/004-tech-debt-jira-epic/drafts/README.md`, with the date it reached In
  Review (`statuscategorychangedate`, or `listJiraIssueChangelogs`).
- [ ] T040 [P] [US3] For each change issue found, read its comments with `listJiraIssueComments` and
  take the PR link.
  - Run `gh pr view <number> --json state,mergedAt,baseRefName,statusCheckRollup,title,url,files`.
  - The evidence holds only if all of these are true: the PR is merged into `main`, its checks passed,
    and its files and description cover the issue's "Готово, коли".
  - Record the verdict and the reason under "Reviews" in
    `specs/004-tech-debt-jira-epic/drafts/README.md`.
- [ ] T041 [P] [US3] For each decision issue found, read its comments.
  - The evidence holds only if the deciding owner's account (research R1) wrote it, it names an option
    (or one of its own) with a reason, and it has a review date when the debt stays as it is.
  - Record the verdict and the reason under "Reviews" in
    `specs/004-tech-debt-jira-epic/drafts/README.md`.
- [ ] T042 [US3] For each issue whose evidence does not hold:
  - Draft a Ukrainian comment that names what is missing, show it to the technical lead, and post it
    with `addOrEditJiraIssueComment` after approval.
  - Leave the register row and the status unchanged; the assignee moves the issue back to In Progress.
- [ ] T043 [US3] For the issues whose evidence holds, prepare one register update on a branch made
  with `.agents/skills/fresh-feature-branch/SKILL.md`.
  - In `docs/shared/debt-register.md`, change each row per the outcomes table of
    [contracts/review-and-register.md](contracts/review-and-register.md#outcomes), citing the Jira key and
    the evidence, and set the "Updated" line to that day.
  - The first time TD-37's row is touched, change "Depends on TD-37" to "Depends on TD-36".
  - TD-21's forecasting half closes with #64.
  - Add one entry to `docs/shared/changelog.md`.
  - Name people only by handle.
- [ ] T044 [US3] When the technical lead asks for the update to be committed or opened as a PR, use
  `.agents/skills/preview-commit/SKILL.md`, then `.agents/skills/preview-pr/SKILL.md`. The PR follows
  `.github/PULL_REQUEST_TEMPLATE.md` and the title format `docs(shared): …`.
- [ ] T045 [US3] After the register PR merges, draft one Ukrainian comment per resolved issue: the
  register PR's link, and a note that the assignee can now move the issue to Done. Show the comments to
  the technical lead, post them after approval, and record them under "Reviews". Never change a status.
- [ ] T046 [US3] For each decision whose outcome is a change (FR-014):
  - Draft `specs/004-tech-debt-jira-epic/drafts/TD-NN-change.md` in the change format, with
    `_feedback-change.md` appended, assigned to the owner named in the new plan.
  - Get approval, then create the issue with `createJiraIssue` under the Epic, in the active sprint, with
    labels `tech-debt, td-NN`.
  - Record its key under "Published", and cite it in the register row.
- [ ] T047 [US3] Check SC-007 for each issue that reached In Review: within 2 days, its row was
  updated or it got a "what is missing" comment. Record late ones under "Reviews" with the reason.

**Checkpoint**: every issue that reached In Review is reflected in the register or has a clear request
for what is missing.

---

## Phase 5: Polish and cross-cutting concerns

- [X] T048 Set **Status** in `specs/004-tech-debt-jira-epic/spec.md` from `Draft` to `Published
  2026-MM-DD (<Epic key>)` once T038 passes.
- [X] T049 Run [quickstart.md](quickstart.md) end to end once more. Record SC-001 to SC-005 as met or not
  met, with the evidence, under "Checks" in `specs/004-tech-debt-jira-epic/drafts/README.md`.
- [X] T050 When the technical lead asks for it, commit `specs/004-tech-debt-jira-epic/` (spec, plan,
  research, data model, contracts, quickstart, tasks, checklists and drafts), with one entry in
  `docs/shared/changelog.md`, using `.agents/skills/preview-commit/SKILL.md`. Open the PR with
  `.agents/skills/preview-pr/SKILL.md`. Run `ruff check .` and `black --check .` first, as `AGENTS.md`
  requires; no Python changes are expected.
- [ ] T051 At the end of sprint 5 (2026-11-17), list the Epic's issues that are not Done.
  - Record their rows in `docs/shared/debt-register.md` as `open`, with the reason, through the Phase 4
    register flow.
  - Ask the technical lead before moving the Epic, which is the technical lead's own issue. Report which
    teammates' issues are still open, without moving them.

---

## Dependencies and execution order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on T003. It blocks all drafting and publishing.
- **US1 + US2 (Phase 3)**: depends on Phase 2.
  - Drafting comes first: T008–T024, then T025–T026 (US2).
  - Validation, T027–T028, follows.
  - Approval, T029, is a hard gate.
  - Publishing, T030–T035, follows in order: the Epic first, because every child needs its key. T035
    comes last.
  - Verification, T036–T038, comes after publishing.
- **US3 (Phase 4)**: depends on T036, and runs whenever an issue reaches In Review. It repeats until the
  sprint ends.
- **Polish (Phase 5)**:
  - T048 and T049 follow T038.
  - T050 runs on request.
  - T051 runs at the end of the sprint.

### User story dependencies

- **US1** needs only the foundation.
- **US2** adds its blocks to US1's drafts, so it depends on T008–T024, and it is published with US1.
- **US3** depends on US1 and US2 being published, and on owners answering.

### Within Phase 3

```text
T008…T023 [P] ─┐
T024 ──────────┴─▶ T025 ─▶ T026 ─▶ T027 ─▶ T028 ─▶ T029 (approval) ─▶ T030 ─▶ T031 ─▶ T032 ─▶ T033 ─▶ T034 ─▶ T035 ─▶ T036 ─▶ T037 ─▶ T038
```

### Parallel opportunities

- T004, T005 and T006 read different things and can run together.
- T008–T023 each write their own draft file, so they can run in parallel.
- T040 and T041 can run in parallel within a review round.

---

## Parallel example: drafting (Phase 3)

```text
Task: "Draft specs/004-tech-debt-jira-epic/drafts/TD-17.md (decision, @Arezzon)"
Task: "Draft specs/004-tech-debt-jira-epic/drafts/TD-20.md (change, @Dima22820)"
Task: "Draft specs/004-tech-debt-jira-epic/drafts/TD-24.md (change, @OLEkSandrKoniaiev)"
Task: "Draft specs/004-tech-debt-jira-epic/drafts/TD-37-comment.md (decision on KAN-80)"
```

## Parallel example: one review round (Phase 4)

```text
Task: "Check the PR evidence of every change issue in In Review"
Task: "Check the decision comments of every decision issue in In Review"
```

---

## Implementation strategy

### MVP (US1 + US2)

1. Phases 1 and 2: snapshot, accounts, feedback blocks.
2. Phase 3 up to T029: all 17 texts drafted, validated and approved.
3. Phase 3 from T030: publish, then verify. **Stop and validate** with the quickstart table: this is
   the deliverable the request asked for.

### Incremental delivery

1. MVP: owners have their issues in sprint 5.
2. US3: register updates arrive in batches as issues reach In Review. Each batch is one register PR.
3. Sprint end: carry-over recorded (T051).

---

## Notes

- Every Jira write is preceded by an approval of its exact text, recorded under "Approval log".
- No task changes an issue's status. Assignees move their own issues, and the Epic moves only with the
  technical lead's approval.
- `drafts/README.md` is the feature's running record: the snapshot, approvals, keys, checks and
  reviews.
- Repository files name people by handle only.
