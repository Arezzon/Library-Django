# Reservations

A reservation holds one copy of a book for a reader for 48 hours, so that it is still there when
they come to the desk. It holds a copy, not a particular one: any copy of the book will do. Every
loan starts with a librarian: readers reserve, and librarians issue the reserved book or lend one
directly.

## The reader's side

### Reserving a book

1. Open the book's page in the catalog.
2. If a copy is available, choose **Reserve for 48 Hours**.

The reservation is active at once; no librarian needs to approve it. **My reservations**
(`/order/reservations/`) lists it with the time you reserved and its deadline, in Kyiv time with
the zone, for example "31 Oct 2026, 14:05 EET". While it is active, the copy counts as taken
everywhere: in the catalog, on the book's page, in search and in the API.

### The 48 hours

- The deadline is exactly 48 hours after you reserve.
- Collect the book from a librarian before the deadline. The librarian issues it, and your
  reservation becomes the loan.
- At the deadline the reservation expires. The copy is free again at once, and My reservations
  shows the reservation as expired. To read the book, reserve it again if a copy is available.

### Cancelling

If you no longer need the book, choose **Cancel** next to the reservation in My reservations and
confirm. You give no reason, and the copy is free for other readers at once.

The library can also cancel a reservation, for example when the copy is damaged. The next page you
open then shows which book it was, when the library cancelled it and why, until you choose
**Dismiss**. My reservations always shows each cancellation's time and reason.

### When you cannot reserve

The book's page says why, and so does the message if you try anyway. The library checks these in
order and tells you the first that applies:

1. **You have an overdue loan.** The message names the book and its due date. Return it first; you
   can then reserve and borrow again.
2. **You already have this book on loan.**
3. **You already reserved this book.** Collect it before its deadline.
4. **You already hold 3 active reservations**, the most allowed. Collect or cancel one to reserve
   another.
5. **No copy is available.** Try again later, or choose another book.

## The librarian's side

### The desk

**Desk** in the navigation (`/order/reservations/desk/`) lists every active reservation, the
nearest deadline first, with the reader, the book, the deadline and the time left. A reservation
leaves the list when it is issued, cancelled or expires.

### Issuing a reserved book

When the reader comes to the desk, choose **Issue** next to their reservation, check the loan
period (14 days unless you choose 1 to 30), and choose **Issue Book**. In one step the reservation
becomes issued and the loan starts with the copy it held, so the available count does not change.
Issuing the same reservation again, by a double click or from another desk, starts no second loan:
you are told it was already issued, with the loan's number.

A reservation whose deadline has passed is not issued. You can still lend the book directly if a
copy is available.

### Lending directly

**Lend Directly**, on the desk or on a book's page (`/order/lend/`), lends a book to any reader for
1 to 30 days. If the reader holds an active reservation of that book, it is issued and its copy
becomes the loan. Otherwise the loan needs a free copy, and a copy that another reader's
reservation holds is not free. Loans started in the admin site follow the same rules.

### Cancelling with a reason

Choose **Cancel** next to a reservation on the desk, write a reason of 1 to 500 characters, and
confirm. The copy is free at once. The reservation records who cancelled it, when and why, and the
audit trail keeps the same. The reader sees the reason, so write it for them, for example "The copy
is damaged; please reserve another book."

### The overdue block

A reader with an overdue loan, one not returned by its due date, is neither issued a reserved book
nor lent one. The message names the overdue book and its due date: they return it first. There is
no override. If the overdue book is not returned within the reservation's 48 hours, the
reservation expires.

### Corrections

Reopening a return recorded by mistake, or moving a loan to the right reader or book, is a
correction, not a new loan. The edit form, the API and the admin site make corrections without the
overdue block, but a correction still needs a free copy. Loans that readers started for themselves
before issuing moved to the desk stay valid and are returned as usual.

## Through the API

Sign in first, as the README's REST API section describes.

| Request | Who | Answer |
|---|---|---|
| `POST /api/v1/reservation/` with `{"book": <id>}` | Signed in | `201` with the reservation, made for you. |
| `GET /api/v1/reservation/` | Signed in | Your reservations, or every one for a librarian: active ones first, by deadline, then the rest, newest first. `?state=active`, `issued`, `cancelled` or `expired` filters by the current state. |
| `GET /api/v1/reservation/<id>/` | Its reader, or a librarian | One reservation. Another reader's answers `404`. |
| `POST /api/v1/reservation/<id>/cancel/` | Its reader, or a librarian | `200` with the reservation. A librarian cancelling someone else's sends `{"reason": "..."}`, 1 to 500 characters; without it the answer is `400`. Another reader's answers `404`. |
| `POST /api/v1/reservation/<id>/issue/` | Librarian | `201` with `{"reservation": {...}, "loan": {...}}`. `{"days": 1 to 30}` is optional; the default is 14. |
| `POST /api/v1/order/` with `{"user", "book", "plated_end_at"}` | Librarian | `201` with the loan. A reservation the reader holds for the book is issued. |

A refusal answers `409` with a `code` and a `detail` message that says what to do next, and nothing
changes: `overdue_loan` (the body adds `book` and `due`), `already_on_loan`, `already_reserved`,
`reservation_limit`, `no_copy_available`, `reservation_expired`, `already_issued` (the body adds
`loan`) or `not_active`, for a reservation that was already cancelled, issued or expired.

`state` is always the current one: an active reservation past its deadline reads `expired`, even
before the library's scheduled job records it. Times carry the library's offset, `+02:00` or
`+03:00`.
