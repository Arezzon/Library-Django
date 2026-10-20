---
name: preview-pr
description: Review and deliver GitHub pull requests, or draft GitHub bug reports, using this repository's templates. Use for a requested push, PR, or bug report; leave commits to preview-commit.
---

# Deliver pull requests and draft bug reports

## Pull requests

Use the repository's Git remote and GitHub CLI (`gh`) when available. Complete only the delivery actions the user requested.

1. Inspect the branch, working tree, remote, and diff against the PR base. Use the base named by the user, or the repository's default branch.
2. When preparing a PR, create or update `docs/shared/changelog.md` before publishing it. Add the newest change as one entry with these three lines in order (separate entries with a blank line):

   ```text
   YYYY-MM-DD
   <topic>
   <changes description>
   ```

   Use the current date, a concise human-readable topic, and a changes description of fewer than 200 words. Keep it brief and avoid a duplicate entry. Ensure the changelog update is committed with the PR changes; use `preview-commit` for uncommitted task changes.
3. Preview the changes that will be published and note the relevant checks. If a push was requested or is needed to create or update the requested PR, push the branch and set its upstream when needed. Never force-push or rewrite shared history unless explicitly requested.
4. If a PR was requested, check for an existing PR from the branch. Create one only if needed, then ensure both new and existing PRs meet these requirements:
   - Title: `<action>(<service>): <description>`, for example `feat(bookings): show bookings in the admin panel`. Choose an action such as `feat`, `fix`, `docs`, `chore`, or `refactor`; use the affected service or area as the scope. Make the description clear to a human reader without requiring the diff. Branch names may use any convention.
   - Description: read `.github/PULL_REQUEST_TEMPLATE.md` at the current branch revision and use its sections and Definition of Done checklist. Fill in the change and verification details, mark only completed checklist items, and explain any unchecked items. Never leave template prompts or an empty description in the published PR.
   - Assignee: assign the person named by the user, or the authenticated GitHub user if none was named. Verify the assignment; report any failure.
5. Report the branch, PR link, and relevant checks or blockers. Do not merge the PR unless asked.

## GitHub bug reports

When drafting or creating a GitHub bug report, read `.github/ISSUE_TEMPLATE/bug_report.md` and follow its fields. Replace every placeholder with the known facts, distinguish expected from actual behavior, and state what is unknown instead of inventing reproduction steps or environment details. Remove secrets and personal data from logs and screenshots. Create or modify a GitHub issue only when the user requested that action; this does not authorize changing a Jira issue.
