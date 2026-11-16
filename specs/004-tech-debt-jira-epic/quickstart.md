# Quickstart: checking the Epic

These checks prove the feature works, before and after publishing. The Jira checks are read-only JQL
queries on the site `arsensworkspace-47040086`, project KAN.

## Before approval: check the drafts

1. Read the register on `origin/main` again (`git fetch origin` and then
   `git show origin/main:docs/shared/debt-register.md`), and list the rows whose status is `open`.
   **Expected**: 16 rows, matching [the issue set](data-model.md#the-issue-set), unless the register
   changed (research R7).
2. List `drafts/`. **Expected**: `epic.md`, 12 files named `TD-NN.md` and 4 named `TD-NN-comment.md`,
   for TD-29, TD-34, TD-36 and TD-37. Together they cover all 16 IDs once.
3. In each draft, check the following:
   - The field block matches the issue set.
   - The kind line says **зміна коду** or **рішення**.
   - The text ends with exactly one feedback block, the one for its kind, copied verbatim from
     [contracts/issue-texts.md](contracts/issue-texts.md).
4. Search the drafts for real names, email addresses and secrets. **Expected**: none. People appear only
   as handles.
5. Show the technical lead every draft, in full, and record the approval (FR-011). If the review
   chooses assignees for TD-36 and TD-37, record those choices too.

## After publishing: check Jira

| Check | JQL or step | Expected |
| ----- | ----------- | -------- |
| One issue per item | `parent = <Epic> ORDER BY key` | 16 issues. Their `td-NN` labels cover the 16 IDs once |
| No stray issues | `project = KAN AND labels in (td-17, td-18, td-19, td-20, td-21, td-22, td-23, td-24, td-25, td-26, td-29, td-31, td-34, td-35, td-36, td-37) AND (parent is EMPTY OR parent != <Epic>)` | None. The `tech-debt` label alone is not used: KAN-17 to KAN-19 carry it from the v1.0 work |
| In the sprint | `parent = <Epic> AND sprint != 5` | None |
| Assigned | `parent = <Epic> AND assignee is EMPTY` | None, and each assignee matches the issue set or the choice made at the draft review |
| Priorities | `parent = <Epic> AND priority not in (Medium, Low)` | None |
| Statuses untouched | Compare the reused issues' statuses with the ones before publishing (all `Idea`) | Unchanged (FR-012) |
| Texts as approved | Open each issue and compare it with its draft | Identical, apart from Jira's formatting |
| Epic | Open the Epic | Its table lists 16 keys, it is in sprint 5 or carries the sprint's dates, and it is assigned to @fazelukario |

## The first review

1. When the first issue reaches In Review, run the query in
   [contracts/review-and-register.md](contracts/review-and-register.md#finding-issues-to-review).
2. Apply the checks and outcomes there, and draft the register pull request.
3. **Expected**: the row changes using only the issue and its comments (SC-006), within 2 days (SC-007).
