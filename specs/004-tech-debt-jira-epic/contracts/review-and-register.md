# Contract: review and register update

This is how an issue in In Review becomes a register update (FR-015, FR-016). The technical lead does
the review, with the agent's help. The agent reads Jira, drafts the comments and the register pull
request, and publishes nothing without approval.

## Finding issues to review

```text
parent = <Epic key> AND status = "In Review" ORDER BY updated ASC
```

The query uses the Epic, not the `tech-debt` label, because KAN-17, KAN-18 and KAN-19 from the v1.0
debt work carry that label too.

## Checks

| Kind | The evidence holds when |
| ---- | ----------------------- |
| change | A comment links a pull request. The pull request is merged into `main`, its required checks passed, and its change does what the issue's "Готово, коли" lists |
| decision | A comment from the deciding owner (or the technical lead's record of their answer) names an option, or their own, and gives its reason. If the debt stays as it is, the comment also gives a review date |

## Outcomes

| Evidence | Register row | Issue |
| -------- | ------------ | ----- |
| Change, PR merged | `closed`, with the PR and the issue key linked in "Evidence, plan or blocker" | Comment: the register PR's link. Then the assignee moves it to Done |
| Change, PR not merged or not linked | Unchanged | Comment: what is missing. Then the assignee moves it back to In Progress |
| Decision: accept the debt | `accepted`, with the decision, its reason, its review date and the issue key | Comment: the register PR's link. Then the assignee moves it to Done |
| Decision: a change follows | `open`, with the new plan, its owner, its target sprint and the issue key | Comment: the register PR's link and the new change issue's key, which is drafted and approved under FR-011 |
| Decision without a reason, or without a review date for an acceptance | Unchanged | Comment: what is missing |

TD-21 can close one part as `closed` with #64 as the evidence, and record the decision on the rest.

## Register pull request

- It changes the rows reviewed, and moves the "Updated" date to the day of the change.
- In TD-37's row, it fixes "Depends on TD-37" to read "Depends on TD-36" the first time it touches
  that row.
- It follows workflow items 5 to 7 of the constitution: the title format, the template and one entry in
  `docs/shared/changelog.md`.
- It cites the Jira keys it resolves. Several rows can share one pull request.
- It names people by handle only.

## Timing

Within 2 days of an issue reaching In Review, either its row is updated or the issue has a comment
saying what is missing (SC-007). Issues still open at the end of sprint 5 keep their rows `open`, with
the reason.
