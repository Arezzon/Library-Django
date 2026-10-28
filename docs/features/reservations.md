# Reservations: the reader's side

A reservation holds one copy of a book for you for 48 hours, so that it is still there when you
come to collect it. It holds a copy, not a particular one: any copy of the book will do.

## Reserving a book

1. Open the book's page in the catalog.
2. If a copy is available, choose **Reserve for 48 Hours**.

The reservation is active at once; no librarian needs to approve it. **My reservations**
(`/order/reservations/`) lists it with the time you reserved and its deadline, in Kyiv time with
the zone, for example "31 Oct 2026, 14:05 EET". While it is active, the copy counts as taken
everywhere: in the catalog, on the book's page, in search and in the API.

## The 48 hours

- The deadline is exactly 48 hours after you reserve.
- Collect the book from a librarian before the deadline. Until librarians issue reserved books at
  the desk (KAN-57), you can also borrow it yourself from the book's page: your reservation becomes
  the loan, and the copy stays yours.
- At the deadline the reservation expires. The copy is free again at once, and My reservations
  shows the reservation as expired. To read the book, reserve it again if a copy is available.

## When you cannot reserve

The book's page says why, and so does the message if you try anyway. The library checks these in
order and tells you the first that applies:

1. **You have an overdue loan.** The message names the book and its due date. Return it first; you
   can then reserve and borrow again.
2. **You already have this book on loan.**
3. **You already reserved this book.** Collect it before its deadline.
4. **You already hold 3 active reservations**, the most allowed. Collect one to reserve another;
   cancelling a reservation arrives with KAN-57.
5. **No copy is available.** Try again later, or choose another book.

## Through the API

Sign in first, as the README's REST API section describes.

| Request | Answer |
|---|---|
| `POST /api/v1/reservation/` with `{"book": <id>}` | `201` with the reservation, made for you. A refusal answers `409` with a `code` and a `detail` message: `overdue_loan` (the body adds `book` and `due`), `already_on_loan`, `already_reserved`, `reservation_limit` or `no_copy_available`. |
| `GET /api/v1/reservation/` | Your reservations: active ones first, by deadline, then the rest, newest first. `?state=active`, `issued`, `cancelled` or `expired` filters by the current state. Librarians see every reservation. |
| `GET /api/v1/reservation/<id>/` | One of your reservations. Another reader's answers `404`. |

`state` is always the current one: an active reservation past its deadline reads `expired`, even
before the library's scheduled job records it. Times carry the library's offset, `+02:00` or
`+03:00`.
