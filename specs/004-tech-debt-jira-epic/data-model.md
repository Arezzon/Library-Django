# Data Model: Remaining Technical Debt Epic

## Entities

### Register item

A row of `docs/shared/debt-register.md`. This feature only reads it, until the review.

| Field | Values |
| ----- | ------ |
| ID | `TD-NN`, never reused |
| Priority | P1, P2, P3. None open is P1 |
| Owner | GitHub handle and role |
| Status | `open`, `closed`, `blocked`, `accepted` |
| Plan, evidence or blocker | Text with links |
| Target sprint | Lab 5 · Testing, Final · Product v2.0 |

Rule: only rows with the status `open` when the issues are published get an issue (FR-003).

### Epic

| Field | Value |
| ----- | ----- |
| Project | KAN |
| Type | Epic |
| Summary | `Технічний борг: решта пунктів реєстру (Лаб 5)` |
| Assignee | @fazelukario |
| Labels | `tech-debt` |
| Sprint | 5, or start date 2026-11-03 and due date 2026-11-17 if Jira refuses it (research R2) |
| Description | [contracts/issue-texts.md, Epic](contracts/issue-texts.md#epic-description) |

### Debt issue

| Field | Rule |
| ----- | ---- |
| Register ID | Exactly one per issue. One issue per open item (FR-003) |
| Origin | `new` (12) or `reused` (4: KAN-78, KAN-79, KAN-80, KAN-81) |
| Type | Bug for wrong behavior, Task otherwise. Reused issues keep their type (FR-004) |
| Kind | `change` or `decision` (FR-005) |
| Summary | `TD-NN · <the item, in Ukrainian>` for new issues. Reused issues keep theirs |
| Assignee | The owner's account (research R1), unless the technical lead chose otherwise at the draft review |
| Priority | Medium for P2, Low for P3. Reused issues keep theirs, which already match |
| Labels | `tech-debt`, `td-NN`, plus the existing labels of a reused issue |
| Parent | The Epic |
| Sprint | 5 |
| Text | A new issue gets a description in the format for its kind. A reused issue keeps its description and gets a comment ([contracts](contracts/issue-texts.md)) |

### Feedback comment

The assignee writes it on the issue.

| Kind | Must contain |
| ---- | ------------ |
| change | A link to the pull request that closes the issue |
| decision | The chosen option, or another one, with its reason. A review date if the debt is accepted |

### Register update

A pull request that changes register rows and the "Updated" line, citing the issue and its evidence
([contracts/review-and-register.md](contracts/review-and-register.md)).

## The issue set

| ID | Origin | Type | Kind | Assignee | Priority |
| -- | ------ | ---- | ---- | -------- | -------- |
| TD-17 | new | Task | decision | @Arezzon | Medium |
| TD-18 | new | Task | decision | @anastasiiaMirovska | Medium |
| TD-19 | new | Task | decision | @anastasiiaMirovska | Medium |
| TD-20 | new | Task | change | @Dima22820 | Medium |
| TD-21 | new | Task | decision | @Arezzon | Medium |
| TD-22 | new | Bug | change | @fazelukario | Low |
| TD-23 | new | Bug | change | @fazelukario | Low |
| TD-24 | new | Task | change | @OLEkSandrKoniaiev | Low |
| TD-25 | new | Task | decision | @Arezzon (consulted: @anastasiiaMirovska) | Medium |
| TD-26 | new | Task | decision | @Arezzon | Low |
| TD-29 | reused KAN-81 | Bug | change | @OLEkSandrKoniaiev (unchanged) | Medium (unchanged) |
| TD-31 | new | Task | change | @fazelukario | Low |
| TD-34 | reused KAN-78 | Bug | change | @OLEkSandrKoniaiev (unchanged) | Low (unchanged) |
| TD-35 | new | Task | change | @fazelukario | Low |
| TD-36 | reused KAN-79 | Bug | change | Chosen at the draft review: @myrrhfawn, the current assignee, or @fazelukario | Low (unchanged) |
| TD-37 | reused KAN-80 | Bug | decision | Chosen at the draft review: @Arezzon, who decides, or @fazelukario, the current assignee | Low (unchanged) |

There are 12 new issues and 4 reused ones. By kind, there are 7 decisions and 9 changes.

## States

A debt issue moves through the team's workflow. Only the people named below change its status (FR-012).

```text
Idea / To Do ──(assignee starts)──▶ In Progress
In Progress ──(assignee: PR link or decision comment)──▶ In Review
In Review ──(technical lead: register updated, comment with the link)──▶ assignee moves it to Done
In Review ──(technical lead: something is missing, comment)──▶ assignee moves it back to In Progress
```

The Epic moves to Done when every issue in it is Done, or is carried over with the reason recorded in
the register. It is the technical lead's own issue, so it moves only with the technical lead's approval.

A decision that leads to a change (FR-014) opens a new change issue under the Epic after its review.
That issue has the origin `new` and the kind `change`, and it is drafted and approved like the rest.
