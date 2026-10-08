---
name: fresh-feature-branch
description: Create a new feature branch from an up-to-date base in this repository. Use when starting feature work or when asked to create a feature branch.
---

# Create a feature branch from a current base

1. Check the current branch and working tree. Preserve uncommitted work; do not discard or overwrite it to switch branches.
2. By default, fetch `origin/main` and create the new branch directly from the refreshed `origin/main`, not from a possibly stale local `main`. If the fetch fails, do not claim the base is current; resolve the failure or tell the user that currency could not be verified before creating the branch.
3. Use another feature branch as the base only when the requested feature depends on it. Fetch that branch's remote tracking ref and compare it with the local branch before use. If the local branch is behind, use the updated remote ref or fast-forward the local branch. If it has unpushed commits, no upstream, or has diverged, establish which commits are intended for the new feature before branching; do not silently use a stale or ambiguous base.
4. Create the new branch from the verified base and report its name and base commit. Leave existing branches and unrelated changes untouched.
