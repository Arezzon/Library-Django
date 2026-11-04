# Implementation Plan: Remaining Technical Debt Epic

**Branch**: `004-tech-debt-jira-epic` (spec directory; no git branch yet) | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-tech-debt-jira-epic/spec.md`

## Summary

Turn the debt register's 16 open items into one Jira Epic in the active sprint, Lab 5 · Testing
(sprint 5, 2026-11-03 to 2026-11-17). Twelve items get new issues. Four reuse their existing bugs:
KAN-81, KAN-78, KAN-79 and KAN-80. Each issue tells its owner what to change or what to decide. It
also ends with a fixed feedback instruction: for a change, a PR link and In Review; for a decision, the
decision in a comment and In Review. The technical lead can then update the register from the answers.

The work is writing and publishing, not code:

1. Draft every text in Ukrainian under [drafts/](drafts/).
2. Show the technical lead the full drafts and get approval.
3. Publish through the Atlassian connector.
4. Review issues as they reach In Review.

The text formats are in [contracts/issue-texts.md](contracts/issue-texts.md). The review procedure is in
[contracts/review-and-register.md](contracts/review-and-register.md).

## Technical Context

**Language/Version**: Ukrainian Markdown for the Jira texts, which the connector converts to Jira's
format. English for this plan and its artifacts.

**Primary Dependencies**: the Atlassian connector's Jira operations: `createJiraIssue`, `editJiraIssue`,
`addOrEditJiraIssueComment`, `transitionJiraIssue` (a sprint move only, never a status change) and
`searchJiraIssuesUsingJql`. See [research R3](research.md#r3-jira-operations).

**Storage**: the Jira project KAN, on the cloud site `arsensworkspace-47040086` (board 1, sprint 5).
The record itself is the register, `docs/shared/debt-register.md`.

**Testing**: JQL checks after publishing, and a check of the drafts against the contracts before
approval ([quickstart.md](quickstart.md)). No Django code changes, so no Django tests are needed.

**Target Platform**: Jira Cloud, a team-managed project. Its statuses are Idea, To Do, In Progress, In
Review and Done.

**Project Type**: a project-management operation, with documentation in the repository.

**Performance Goals**: N/A.

**Constraints**:
- Nothing is published before the technical lead approves the full text (FR-011).
- No status change on any issue (FR-012).
- Repository files name people only by GitHub handle.
- The texts hold no secrets, emails or other personal data (Principle IV).

**Scale/Scope**: 1 Epic, 12 new issues, 4 reused issues, 4 comments and 1 later edit of the Epic's
description.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle or rule | Applies? | Result |
| ----------------- | -------- | ------ |
| I. Domain-owned apps | No code changes | Pass (N/A) |
| II. Explicit role-based access | No code changes. TD-22, TD-35 and TD-37 describe access work that the assignees will do under this principle | Pass (N/A) |
| III. Test-backed changes | No code changes. Each change issue's done criteria require tests in the owning app that fail without the change ([contracts/issue-texts.md](contracts/issue-texts.md#change-issue-description)) | Pass |
| IV. Secrets and safe defaults | The Jira texts hold no secrets, credentials, emails or personal data. People are named by handle, and Jira's assignee field identifies the account | Pass |
| V. Consistent data | No code changes | Pass (N/A) |
| VI. Lean, portable deployment | No code changes. TD-24's description says that replacing the Tailwind CDN with a build step needs a feature spec and a Complexity Tracking entry, as Technology & Platform Constraints require. TD-17's says that an automatic copy adds a destination and credentials to justify | Pass |
| Workflow 1, branching | The spec files need a branch from a fresh `origin/main` before they are committed (`.agents/skills/fresh-feature-branch/SKILL.md`) | Pass, if done before commit |
| Workflow 5–7, pull requests and docs | Register updates at review go through pull requests that follow the template, with a changelog entry ([contracts/review-and-register.md](contracts/review-and-register.md)) | Pass |
| Governance, amendments | TD-31 needs a PATCH amendment through `/speckit-constitution`. Its issue says so; this feature does not amend anything | Pass |

**Post-design re-check** (after Phase 1): unchanged. All gates pass, so Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/004-tech-debt-jira-epic/
├── spec.md
├── plan.md                    # This file
├── research.md                # Phase 0: Jira facts, the account mapping, decision options, item facts
├── data-model.md              # Phase 1: entities, the issue set, states
├── quickstart.md              # Phase 1: how to check the drafts and the published Epic
├── contracts/
│   ├── issue-texts.md         # Formats of the Epic, the issues and the reuse comments, with the feedback blocks verbatim
│   └── review-and-register.md # How an issue in In Review becomes a register update
├── checklists/requirements.md
├── drafts/                    # Implementation: one Markdown file per Jira text, for approval
└── tasks.md                   # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

No application code changes. The only repository files that change are these:

```text
specs/004-tech-debt-jira-epic/   # this feature's documents and drafts
docs/shared/debt-register.md     # at review only (FR-016), through separate pull requests
docs/shared/changelog.md         # one entry per register-update pull request
```

**Structure Decision**: documentation only. The drafts live with the feature, so the approved text and
the published text can be compared later.

## Complexity Tracking

No violations.
