# Architecture decision records

Each record explains one significant decision: its context, what was decided, its consequences,
and the alternatives that were rejected. A record is never rewritten after it is accepted. A
later decision that changes it gets a record of its own, which names the one it supersedes.

Numbers are assigned when a decision is proposed, so the list can have gaps while other records
are under review.

| Record | Decision | Status |
|---|---|---|
| [0001](0001-reservations-hold-a-unit-of-stock.md) | Reservations hold a unit of stock, not a particular copy | Accepted, 2026-10-28 |
| [0002](0002-audit-trail.md) | An audit trail written with each critical change | Accepted, 2026-10-28 |
| [0003](0003-database-backups.md) | Database backups: a sidecar on the database image | Accepted, 2026-10-28 |
