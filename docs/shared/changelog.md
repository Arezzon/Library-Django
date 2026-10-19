2026-10-19
Lint and format checks in CI
Added ruff and black settings in pyproject.toml with pinned versions in requirements-dev.txt, and a CI lint job that must pass before the image is published. Formatted the code with black and fixed the lint findings without changing behavior; migrations are excluded.

2026-10-19
Secrets only from environment variables
Removed default secrets: Django refuses to start without SECRET_KEY, DEBUG is off unless explicitly enabled, the database password has no default, and DATABASE_URL is supported ahead of the DB_* values. The Docker image no longer bakes in a SECRET_KEY, Compose requires SECRET_KEY and DB_PASSWORD from .env, CI generates disposable secrets and checks that the image refuses to start without a key, and .env.example and the README document the required values.

2026-10-19
CodeQL code scanning
Added a CodeQL workflow that scans GitHub Actions workflows, JavaScript and Python code for security and quality issues on pushes and pull requests to main and every Saturday, and reports findings as code scanning alerts in the repository's Security tab.

2026-10-18
Code ownership by module
Assigned owners for borrowing, books, and events; grouped business analysis and shared documentation; and updated test ownership so Dima and Arezzon can review test changes.

2026-10-18
Delete books from the edit page
Added a librarian-only delete action beside the edit controls using the logout button style, with confirmation, CSRF protection, a borrowing-history guard, and focused tests for deletion and access control.

2026-10-13
Template guidance for GitHub contributions
Updated the repository guidance and PR delivery skill to follow the pull request template and use the bug report template when drafting GitHub defects.

2026-10-13
GitHub review and bug-report templates
Added a pull request template with a Definition of Done checklist and a bug-report template with reproduction, expected result, actual result, and environment fields. Existing CODEOWNERS already assigns repository, documentation, and test owners.

2026-10-08
README and mobile analytics navigation
Reworked the README with Docker and venv quick starts, prerequisites, platform-specific commands, Memurai/Redis guidance, troubleshooting, API and analytics documentation. Added the mobile Analytics icon to match the other navigation items.

2026-10-07
Fresh base for feature branches
Added a skill and repository rule to create feature branches from an updated origin/main, with a verified feature branch base when a dependency requires it.

2026-10-06
Code ownership by role
Limited Anastasiia's code ownership to documentation and Dima's to test files and test directories. The other four collaborators remain owners across the repository.

2026-10-06
Repository guidance and delivery skills
Added AGENTS.md and two skills for reviewing commits and pull requests. PR guidance covers changelog updates, readable titles, descriptions, and assignees.
