---
name: preview-commit
description: Review repository changes and create a Git commit when the user asks to commit work. Use for the commit stage, including a pre-commit preview; do not push or create a pull request.
---

# Preview and create a commit

1. Inspect the branch, working tree, and diff. Identify the files that belong to the requested change and leave unrelated work untouched.
2. Run checks appropriate to those files. Report checks that could not run.
3. Stage only the task's files and preview the staged diff. Check for unintended files, secrets, and whitespace errors.
4. If the intended changes are already committed, do not create an empty commit. Otherwise, create a concise commit that describes the change.
5. Report the commit hash, included files, and checks. Do not push or create a PR unless the user requested those steps separately.
