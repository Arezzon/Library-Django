# Contract: Technical logs and the audit trail (PR 8)

**Requirements**: FR-034 to FR-040, SC-007, SC-008 | **Research**: R18 to R21

## Log line

```text
line         = header " " logger ": " message
continuation = header " | " text          ; each further line of a traceback or message
header       = time " " level " " service " " request-id
time         = UTC, ISO 8601, milliseconds, "Z"     e.g. 2026-10-27T10:15:30.123Z
level        = DEBUG | INFO | WARNING | ERROR | CRITICAL
service      = web | worker | backup
request-id   = 8 to 64 characters of [A-Za-z0-9._-], or "-" outside a request
```

Example of a failing request with its traceback:

```text
2026-10-27T10:15:30.123Z ERROR web 8f14e45fceea167a5a36dedd4bea2543 django.request: Internal Server Error: /book/5/
2026-10-27T10:15:30.123Z ERROR web 8f14e45fceea167a5a36dedd4bea2543 | Traceback (most recent call last):
2026-10-27T10:15:30.123Z ERROR web 8f14e45fceea167a5a36dedd4bea2543 |   File "/app/library/book/views.py", line 57, in book_detail
2026-10-27T10:15:30.124Z ERROR web 8f14e45fceea167a5a36dedd4bea2543 | RuntimeError: …
```

- Every line of a record carries the header, so a search for the request id finds the whole record.
  A newline in user input therefore cannot start a line of its own.
- `entrypoint.sh` writes as service `web`, logger `entrypoint`, request id `-`.
- The backup script writes as service `backup`, logger `backup`, request id `-`.

## Request identifier

| Step | Behavior |
|---|---|
| Request arrives | `X-Request-ID` is accepted if it matches `[A-Za-z0-9._-]{8,64}`. Otherwise a UUID4 hex is made. |
| Response | Returns `X-Request-ID: <id>` |
| Task published during the request | The id travels in the Celery message headers |
| Task runs in the worker | Its log lines carry the request's id |
| Task with no request, such as a scheduled one | Its lines carry its Celery task id |

## What is logged (FR-035)

| Event | Level | Logger |
|---|---|---|
| Unhandled error in a request, with its traceback | ERROR | `django.request` |
| Refused request (401, 403), along with every other 4xx response | WARNING | `django.request` (path only, never the query string) |
| Failed sign-in | WARNING | `authentication`: "Sign-in failed for account #12", or "Sign-in failed for an unknown account" |
| Task failure or retry | ERROR, WARNING | `celery.app.trace`, `celery.worker` |
| Broker unavailable | ERROR | `events.services` |
| Embedding failure | ERROR | `book.embeddings` |
| Startup steps: migrations, seeding, re-encoding, server start | INFO | `entrypoint` |
| Backup result | INFO or ERROR | `backup` |
| Reservations expired by the schedule | INFO | `order.tasks`: the count only |

## Never in a log line or an audit entry (FR-039)

| Item | Rule |
|---|---|
| Passwords and password hashes | The values of keys such as `password` and `passwd` are replaced with `[redacted]`. Audit entries never include them. |
| Secrets and keys | The values of keys named like `secret`, `key` or `token`, and the literal `SECRET_KEY` and `DB_PASSWORD` values, are replaced |
| Session and CSRF identifiers | The values of `sessionid`, `csrftoken`, `csrfmiddlewaretoken`, and the `Cookie` and `Authorization` headers, are replaced |
| Connection URLs | `scheme://user:password@host` becomes `scheme://user:***@host` |
| Search text | The `q` parameter of any URL becomes `q=[redacted]`. Messages never include a query. Gunicorn's access log stays off. |

Analytics events are database rows, not log lines. The search events keep their text as KAN-30
designed, and the register records the open question (FR-055).

## Level and rotation (FR-036)

| Setting | Value |
|---|---|
| `LOG_LEVEL` | Default `INFO`. It applies to the application loggers, gunicorn and the worker. |
| Docker logging, every service | `json-file`, `max-size: 10m`, `max-file: "5"`: at most 50 MB per container and 250 MB for the 5 containers, against a 500 MB limit |

## Operator search (SC-008)

```bash
id=8f14e45fceea167a5a36dedd4bea2543
for c in library-web-1 library-worker-1; do docker logs "$c" 2>&1 | grep "$id"; done
```

Replace `library` with the stack name. In Portainer, open each container's **Logs** and search for
the id.

## Audit entry (FR-037, FR-038, FR-040)

The fields are in [data-model.md](../data-model.md) §5. The table below shows what `before` and
`after` hold for each action: only the fields that changed.

| Action | `before` | `after` | Reason |
|---|---|---|---|
| `role_granted`, `role_removed` | `{"role": "reader"}` | `{"role": "librarian"}` | Optional |
| `account_activated`, `account_deactivated` | `{"is_active": false}` | `{"is_active": true}` | Optional |
| `account_deleted` | `{"role": …, "is_active": …}` | `{}` | — |
| `loan_started` | `{}` | `{"book": 7, "user": 12, "due": "…"}` | — |
| `loan_returned` | `{"end_at": null}` | `{"end_at": "…"}` | — |
| `loan_reopened` | `{"end_at": "…"}` | `{"end_at": null}` | — |
| `loan_reassigned` | `{"book": 7}` or `{"user": 12}` | the new value | — |
| `loan_deleted` | `{"book": 7, "user": 12, "end_at": …}` | `{}` | — |
| `reservation_created` | `{}` | `{"book": 7, "user": 12, "expires_at": "…"}` | — |
| `reservation_issued` | `{"state": "active"}` | `{"state": "issued", "loan": 55}` | — |
| `reservation_cancelled` | `{"state": "active"}` | `{"state": "cancelled"}` | Required when the library cancels |
| `reservation_expired` | `{"state": "active"}` | `{"state": "expired"}` | — |
| `book_copies_changed` | `{"count": 3}` | `{"count": 2}` | — |
| `book_deleted` | `{"name": "…", "count": 3}` | `{}` | — |

| Channel | Set when |
|---|---|
| `web` | A request outside `/admin/` and `/api/` |
| `api` | A request under `/api/` |
| `admin` | A request under `/admin/` |
| `system` | A Celery task, such as the reservation expiry |
| `command` | Anything else: management commands, scripts, the shell |

**Guarantees**:
- **Written with the change**: one entry per completed critical change, in the same transaction.
  None for a change that fails or rolls back (Story 5 scenarios 2 and 3).
- **Never changed**: no edit or delete through the application, including the admin site, the API
  and the ORM's bulk methods (scenario 4).
- **Read by librarians only**, at `/admin/audit/auditentry/`, filtered by action, channel and date.
  No other page or API exposes entries.
- **Linked to the logs**: an entry's `request_id` matches the request's technical log lines.
