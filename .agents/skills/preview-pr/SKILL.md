---
name: preview-pr
description: Review a branch and create or update a GitHub pull request when the user asks to push or open a PR. Use for the push and PR stage, including a pre-PR preview; leave commits to preview-commit.
---

# Preview and deliver a pull request

Use the repository's Git remote and GitHub CLI (`gh`) when available. Complete only the delivery actions the user requested.

1. Inspect the branch, working tree, remote, and diff against the PR base. Use the base named by the user, or the repository's default branch.
2. When preparing a PR, create or update `docs/changelog.md` before publishing it. Add the newest change as one entry with these three lines in order (separate entries with a blank line):

   ```text
   YYYY-MM-DD
   <topic>
   <changes description>
   ```

   Use the current date, a concise human-readable topic, and a changes description of fewer than 200 words. Keep it brief and avoid a duplicate entry. Ensure the changelog update is committed with the PR changes; use `preview-commit` for uncommitted task changes.
3. Preview the changes that will be published and note the relevant checks. If a push was requested or is needed to create or update the requested PR, push the branch and set its upstream when needed. Never force-push or rewrite shared history unless explicitly requested.
4. If a PR was requested, check for an existing PR from the branch. Create one only if needed, then ensure both new and existing PRs meet these requirements:
   - Title: `<action>(<service>): <description>`, for example `feat(bookings): show bookings in the admin panel`. Choose an action such as `feat`, `fix`, `docs`, `chore`, or `refactor`; use the affected service or area as the scope. Make the description clear to a human reader without requiring the diff. Branch names may use any convention.
   - Description: explain what changed, why, and which checks ran or could not run. Never leave it empty or as a placeholder.
   - Assignee: assign the person named by the user, or the authenticated GitHub user if none was named. Verify the assignment; report any failure.
5. Report the branch, PR link, and relevant checks or blockers. Do not merge the PR unless asked.
