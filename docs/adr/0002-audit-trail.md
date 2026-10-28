# 2. An audit trail written with each critical change

- **Status**: Accepted, 2026-10-28
- **Issue**: KAN-67 (part of KAN-62)

## Context

Librarians change who may do what and what the library holds: they grant and remove the
librarian role, activate and deactivate accounts, start, return, reopen, reassign and delete
loans, and change or delete a book's copies. KAN-62 requires a record of each of these changes,
saying who made it, what changed, when, through which channel and, where one is required, why.
The record must not be editable through the application, must survive the deletion of the
account or book it describes, and must never hold a password or other secret.

These changes reach the database through four channels: the web pages, the API, the Django admin
site and code run outside a request, such as management commands and Celery tasks. The `events`
app already records activity, but as analytics: best effort, written by the worker after the
change commits, and allowed to be lost.

## Decision

- **Audit entries are part of the business record.** Each entry is written in the same
  transaction as its change. If the entry cannot be written, the change rolls back, and a change
  that rolls back leaves no entry.
- **A Django app of its own**, `audit`. It holds the `AuditEntry` model, the `record()` service,
  the context that says who is acting and through which channel, and a read-only admin page. It
  imports no domain app; the domain apps call it.
- **Entries are written where every channel already passes**, so no channel can skip them:

  | Change | Written in |
  |---|---|
  | Role granted or removed; account activated or deactivated | `CustomUser.save()`, made atomic, comparing with the stored row locked until the save commits |
  | Account deleted | A `post_delete` receiver, which also fires for the admin site's bulk delete |
  | Loan started, returned, reopened or reassigned | `Order.save()`, which already locks the row in a transaction |
  | Loan deleted, including with its account or book | A `post_delete` receiver |
  | Book's total copies changed | `Book.save()`, which is already atomic |
  | Book deleted | A `post_delete` receiver |

  The reservation stages (KAN-56 to KAN-57) record their transitions through the same service.
- **Bulk writes that would skip those points are refused**: `update()` and `bulk_update()` of an
  account's role or status, of a loan's book, reader or return time, and of a book's copies, and
  `bulk_create()` of loans.
- **Who and where** come from a context variable. The request middleware sets the signed-in
  account and the channel from the path (`/admin/`, `/api/` or the web). Celery tasks act as the
  system, and anything else defaults to a command with no actor.
- **Unchangeable**: an entry cannot be saved again or deleted, through the model, the queryset or
  the admin site, and no API exposes entries. Librarians read them in the admin site, the only
  place that shows them.
- **Ids and labels, not foreign keys**, so an entry outlives what it describes. Each entry keeps
  the request identifier of the technical logs, and only the fields that changed.

## Consequences

- An audited save takes one more query to lock and read the stored row, and one insert.
- A failure of the audit table stops the change it would record, as it must.
- Code that changed these fields in bulk must save each row instead. Two tests did; none of the
  application's code did.
- Entries hold names and account ids and are kept indefinitely. The debt register asks the product
  owner and the business analyst to set a retention period.

## Alternatives considered

- **Audit rows in the `events` app.** Its records are best effort and written by the worker after
  commit. Keeping transactional records in the same app invites the wrong guarantee.
- **Signals only.** `CustomUser.save()` was not atomic, so a failed audit insert could have left
  the change committed.
- **`ATOMIC_REQUESTS`.** It does not cover commands and tasks, and it wraps every request in a
  transaction.
- **A third-party audit package.** It is a new runtime dependency, and its generic diffs record
  more personal data than needed.
