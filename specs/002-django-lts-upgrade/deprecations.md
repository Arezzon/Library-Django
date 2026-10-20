# Deprecation baseline: Django 5.2 LTS Upgrade

**Feature**: [spec.md](spec.md) (US2, FR-010–FR-012) | **Recorded**: 2026-10-20 |
**Django**: 5.2.18 | **Pins**: the root `requirements.txt` at this branch's head

## Method

The full suite ran inside the `web` service of `docker-compose-dev.yml`, with real-model tests
enabled (quickstart.md §2.5):

```bash
docker compose -f docker-compose-dev.yml exec -T \
  -e PYTHONWARNINGS=always::DeprecationWarning,always::PendingDeprecationWarning \
  -e RUN_BOOK_EMBEDDING_MODEL_TESTS=1 -e CELERY_TASK_ALWAYS_EAGER=True \
  web python manage.py test authentication author book order events 2>&1 \
  | grep -E "Warning:" | sort | uniq -c
```

`DeprecationWarning` and `PendingDeprecationWarning` include Django's `RemovedInDjango60Warning`
and `RemovedInDjango61Warning`. As a control, the same environment shows a
`RemovedInDjango60Warning` for `format_html()` called without arguments. The filter therefore
reports warnings rather than hiding them.

## Result

No deprecation warnings remain. The run reported 156 tests, `OK`, and printed no warnings, from
the project's code or from third-party packages.

| Warning | Raised by | Removed in | Expected resolution |
|---|---|---|---|
| — | — | — | — |

Repeat this check when moving to the next Django release line, and add a row for each new warning.
