# 1. Reservations hold a unit of stock

- **Status**: Accepted, 2026-10-28
- **Issue**: KAN-55 (part of KAN-48)

## Context

The library keeps one number per book: its total copies (`Book.count`). It does not tell its
physical copies apart. There is no copy record, barcode or shelf mark, and the LR2 feasibility
review confirms that the product keeps only a count per book. A loan (`Order`) takes one of the
book's copies while it is open, and the number available is derived from the open loans, never
stored (KAN-18).

KAN-55 to KAN-58 add reservations. A reader holds a book for 48 hours, with no librarian's
approval, and a librarian then issues the held book at the desk or cancels the hold with a reason.
While a reservation is active it must keep a copy for its reader, so every rule that counts copies
must count reservations too: the catalog, the book page, search, the API, the admin site, and the
checks made before a loan or a reservation.

## Decision

- **A reservation holds one unit of a book's stock, not a particular copy.** It records the
  reader, the book and the times, and it lowers the number available by one while it is active.
  Which copy the reader takes home is decided at the desk, as it is for a loan today.
- **Availability** is the total copies minus the open loans minus the active, unexpired
  reservations, and never less than 0. One implementation computes it for every page, the API, the
  admin site and each loan and reservation check.
- **The deadline is stored.** `expires_at` is set once, 48 hours after `created_at`. A check
  constraint holds the elapsed time at exactly 48 hours, whatever the time zone of the database
  session, so a restore into a server set to a zone with summer time keeps every row. A
  reservation stops holding its copy at its deadline, whether or not the scheduled expiry has
  recorded it yet.
- **Four states, and only these changes**:

  ```mermaid
  stateDiagram-v2
      [*] --> active: a reader reserves (a copy is available, the rules are met)
      active --> issued: a librarian issues it before the deadline (the loan starts in the same step)
      active --> cancelled: a librarian with a reason, or the reader without one
      active --> expired: the deadline passes (the system)
      issued --> [*]
      cancelled --> [*]
      expired --> [*]
  ```

  Issued, cancelled and expired are final. `Reservation.change_state()` refuses every other change
  and leaves the reservation as it was. The queryset refuses bulk writes of the state, the loan and
  the cancellation fields, so each change passes through one place.
- **One active reservation per reader and book.** A partial unique index backs up the checks that
  the reservation service makes first.
- **History protects a book.** Loans and reservations refer to their book with `PROTECT`, so a
  book with either cannot be deleted through the web, the API or the admin site.

The reservation stages build on this: reserving and availability (KAN-56), issuing and cancelling
at the desk (KAN-57) and the complete pages (KAN-58).

## Consequences

- A reader cannot reserve a particular copy. Copies of one book are interchangeable; a different
  edition needs a book record of its own.
- A librarian may lower a book's total below its open loans and reservations. Availability then
  shows 0.
- A book with any loan or reservation, returned or not, stays in the catalog. Before this change,
  the API and the admin site deleted a book together with its loans.
- Loans are no longer deleted with their book, a case that ADR 0002's table still lists. Its
  `post_delete` receiver now records loans deleted alone or with their account.
- Availability queries count reservations as well as loans, in the same query.

## Alternatives considered

- **Tracking physical copies**: one record per copy, with loans and reservations of a copy. It
  needs data the library does not have, a stocktake to create it, and screens to maintain it, for
  a benefit that no requirement asks for.
- **Deriving the deadline from `created_at`** instead of storing it. Queries for availability and
  for the desk list could not use an index on it.
