# Repository guidance

- The Django project lives in `library/`; run management commands from that directory.
- For app changes, use the relevant Django tests. CI runs `python manage.py test authentication author book order` inside the Docker Compose `web` service; see `.github/workflows/docker-build.yml` for the full check.
- For a requested commit, use `.agents/skills/preview-commit/SKILL.md`. For a requested push or GitHub pull request, use `.agents/skills/preview-pr/SKILL.md`. When both are requested, apply the commit skill first.
