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
(`/order/reservations/`) lists it with the time you reserved, its deadline in Kyiv time with the
zone, for example "31 Oct 2026, 14:05 EET", and the time left, such as "1 day 23 hours left".
While it is active, the copy counts as taken everywhere: in the catalog, on the book's page, in
search and in the API.

### What to do next

My reservations says what comes next for each reservation:

- **Active**: collect the book from a librarian before the deadline.
- **Issued**: the book is on loan; return it by the loan's due date. Once it is back, the date
  it was returned.
- **Expired**: reserve it again if a copy is available.
- **Cancelled**: whether you or the library cancelled it, and the library's reason.

### The 48 hours

- The deadline is exactly 48 hours after you reserve.
- Collect the book from a librarian before the deadline. The librarian issues it, and your
  reservation becomes the loan.
- At the deadline the reservation expires. The copy is free again at once, and My reservations
  shows the reservation as expired. To read the book, reserve it again if a copy is available.

### Cancelling

If you no longer need the book, choose **Cancel** next to the reservation in My reservations, then
**Yes, Cancel Reservation**. You give no reason, and the copy is free for other readers at once.

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

When the place to act is My reservations or My orders, the book's page links to it.

## The librarian's side

### The desk

**Desk** in the navigation (`/order/reservations/desk/`) lists every active reservation, the
nearest deadline first, with the reader, the book, the deadline and the time left, such as "1 day
3 hours left". A reservation leaves the list when it is issued, cancelled or expires.

### Issuing a reserved book

When the reader comes to the desk, choose **Issue** next to their reservation, check the loan
period (14 days unless you choose 1 to 30), and choose **Issue Book**. In one step the reservation
becomes issued and the loan starts with the copy it held, so the available count does not change.
Issuing the same reservation again, by a double click or from another desk, starts no second loan:
you are told it was already issued, with the loan's number.

When a reservation cannot be issued, its issue page says why instead of showing the form, and
offers the next step:

- **Expired**: **Lend Directly**, with the reader and the book filled in. The loan then needs a
  free copy.
- **Already issued**: the loan it became.
- **The reader has an overdue loan, or already has the book**: the reader's loans, where you
  record the return.
- **Cancelled**: back to the desk.

### Lending directly

**Lend Directly**, on the desk or on a book's page (`/order/lend/`), lends a book to any reader for
1 to 30 days. If the reader holds an active reservation of that book, it is issued and its copy
becomes the loan. Otherwise the loan needs a free copy, and a copy that another reader's
reservation holds is not free. Loans started in the admin site follow the same rules.

### Cancelling with a reason

1. Choose **Cancel** next to a reservation on the desk.
2. Write a reason of 1 to 500 characters and choose **Continue**.
3. Check the reason as the reader will see it, then choose **Yes, Cancel Reservation**, or
   **Change Reason** to edit it. Nothing changes before this step.

The copy is free at once. The reservation records who cancelled it, when and why, and the audit
trail keeps the same. The reader sees the reason, so write it for them, for example "The copy is
damaged; please reserve another book."

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
changes. The pages show the same messages.

| `code` | When | The body adds |
|---|---|---|
| `overdue_loan` | The reader has a loan past its due date. Reserving, issuing and lending stop; corrections do not. | `book`, `due` |
| `already_on_loan` | The reader already has the book on loan | |
| `already_reserved` | The reader already holds an active reservation of the book | |
| `reservation_limit` | The reader already holds 3 active reservations | |
| `no_copy_available` | No copy is free; a copy that another reader's reservation holds is not | |
| `reservation_expired` | Issuing at or after the deadline | |
| `already_issued` | Issuing a reservation a second time | `loan` |
| `not_active` | Cancelling or issuing a reservation that was already cancelled, issued or expired | |

`state` is always the current one: an active reservation past its deadline reads `expired`, even
before the library's scheduled job records it. Times carry the library's offset, `+02:00` or
`+03:00`.

## Simultaneous requests

Each request checks its rules with the reader's and the book's records locked, so requests that
arrive together are checked one after another. When 100 readers reserve a book's last copy at the
same moment, exactly one gets it and the others are told that no copy is available. A double click
on Issue starts one loan.

`scripts/smoke_reservation_load.py` checks this against a running stack. CI sends 100
simultaneous reservations for one copy, 20 times, on every pull request, and fails unless exactly
one succeeds each time. On the Raspberry Pi, the operator also times reserving, issuing and
cancelling while 30 readers reserve at once; see "Check reservations under load" in the
[operator guide](../deployment/raspberry-pi-portainer.md#check-reservations-under-load).
