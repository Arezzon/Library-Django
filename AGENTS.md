# Repository guidance

- The Django project lives in `library/`; run management commands from that directory.
- For app changes, use the relevant Django tests. CI runs `python manage.py test authentication author book order` inside the Docker Compose `web` service; see `.github/workflows/docker-build.yml` for the full check.
- For Python changes, run `ruff check .` and `black --check .` from the repository root with the versions pinned in `requirements-dev.txt`; the CI `lint` job enforces both.
- Before creating a branch for a new feature, use `.agents/skills/fresh-feature-branch/SKILL.md`. Base it on an updated `origin/main` unless the feature depends on another feature branch; verify that branch is current before using it as the base.
- For a requested commit, use `.agents/skills/preview-commit/SKILL.md`. For a requested push or GitHub pull request, use `.agents/skills/preview-pr/SKILL.md`. When both are requested, apply the commit skill first.
- For a GitHub bug report, use `.agents/skills/preview-pr/SKILL.md` and the repository's bug report template.
