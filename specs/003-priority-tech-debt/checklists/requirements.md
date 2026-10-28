# Specification Quality Checklist: Close the Priority Technical Debt of v1.0

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-27
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Iteration 1 (2026-10-27): three [NEEDS CLARIFICATION] markers remain, in FR-012 (further limits on
  reserving and issuing, which KAN-57 requires to be agreed before implementation), FR-026 (whether a
  copy of each backup leaves the Raspberry Pi) and FR-059 (how the KAN-62 work without its own Jira
  issue is split into pull requests). They are presented to the user as questions.
- Iteration 1 fixes applied before review: FR-007, FR-031, FR-032, FR-045 and FR-053 no longer write
  to the debt register before pull request 12 creates it; each reservation stage now describes its own
  API operations in the schema as it adds them (Principle I); FR-060 allows for what the
  access-control pull request itself has to show; and an assumption no longer names database
  transactions.
- Technology terms that remain are the stakeholders' own acceptance terms or the product's interfaces,
  not design choices: "database queries" and "N+1" come from KAN-18 and KAN-62's third acceptance
  criterion; WCAG 2.2 AA, the 2 s and 3 s targets and the 85% coverage target come from the LR2
  requirements; the REST API, CI checks, code scanning and the Raspberry Pi are existing product
  interfaces, project gates and the deployment target. "Django 5.2 LTS" appears only in the starting
  point table as a record of completed work.
- FR-043's "plain language" is made verifiable by the walkthrough in FR-045 and SC-009.
- Iteration 2 (2026-10-27): all three markers resolved with the user's answers, recorded under
  Clarifications. FR-012 now sets a limit of 3 active reservations per reader and blocks reserving
  and issuing while the reader has an overdue loan, with scenarios added to Stories 2 and 3 and
  edge cases for simultaneous requests, loans that become overdue and loan corrections. FR-026 keeps
  daily backups on the Pi apart from the database and adds a weekly manual copy to another machine;
  SC-006 and FR-055 state the remaining risk of up to a week of lost data if the Pi is lost. FR-059
  creates four KAN-62 sub-tasks, with the assignee's confirmation, and gives each its own pull
  request. Re-validation found no failing item: 62 functional requirements, 14 success criteria, no
  template placeholders.
- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`
