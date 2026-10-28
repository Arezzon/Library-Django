# Contract: Reservations and loans at the desk (PRs 5, 6 and 7)

**Requirements**: FR-009 to FR-024, FR-061 | **Research**: R10 to R17 | **Access**:
[access-control.md](access-control.md)

Each stage describes, in the API schema, the operations it adds (FR-021). Every refusal says what
happened and what the person can do next (FR-020).

## Times

API datetimes are ISO 8601 with the library's offset (Europe/Kyiv, +02:00 or +03:00) from PR 5, the
same instants as before (R16). Pages show `j M Y, H:i T`, for example "29 Oct 2026, 14:05 EET". A
reservation is active while `now < expires_at`, where `expires_at` is `created_at` plus 48 hours.

## Resource: reservation

```json
{
  "id": 41,
  "book": 7,
  "user": 12,
  "state": "active",
  "created_at": "2026-10-29T14:05:00+02:00",
  "expires_at": "2026-10-31T14:05:00+02:00",
  "loan": null,
  "cancelled_at": null,
  "cancel_reason": "",
  "cancelled_by_library": false
}
```

- `state` is the effective state: an active reservation past its deadline reads `expired`, whether
  or not the scheduled task has run.
- Librarians also see `cancelled_by`, an account id.
- `loan` is the loan's id once the reservation is issued.

## API operations

| Operation | PR | Audience | Request | Success |
|---|---|---|---|---|
| `GET /api/v1/reservation/` | 5 | Signed-in. Readers see their own; librarians see all. | Optional `?state=active\|issued\|cancelled\|expired` | 200, a list. Active reservations come first, by deadline; the others follow, newest first. |
| `GET /api/v1/reservation/{id}/` | 5 | The reservation's reader, or a librarian | — | 200, one reservation |
| `POST /api/v1/reservation/` | 5 | Signed-in; reserves for the caller | `{"book": 7}` | 201, the reservation |
| `POST /api/v1/reservation/{id}/cancel/` | 6 | The reservation's reader, without a reason; a librarian, with one | `{"reason": "Copy damaged"}`. The reason is required for a librarian cancelling someone else's reservation, 1 to 500 characters. | 200, the reservation |
| `POST /api/v1/reservation/{id}/issue/` | 6 | Librarian | `{"days": 14}`. Optional; 1 to 30, 14 by default. | 201, `{"reservation": {…}, "loan": {…}}` |
| `POST /api/v1/order/` | 6 | Librarian (lending directly) | `{"user": 12, "book": 7, "plated_end_at": "…"}`, as today | 201, the loan. If the reader holds an active reservation of the book, that reservation is issued. |

The 401, 403 and 404 responses follow [access-control.md](access-control.md). Validation errors
answer 400 in DRF's field-error format.

## Refusals: HTTP 409

```json
{
  "code": "overdue_loan",
  "detail": "“Dune” was due on 20 Oct 2026. Return it before reserving or borrowing another book.",
  "book": 3,
  "due": "2026-10-20T12:00:00+03:00"
}
```

| `code` | When | Reader's message | Librarian's message |
|---|---|---|---|
| `overdue_loan` | The reader has an unreturned loan past its due date. It applies to reserving, issuing and lending, but not to corrections. | "“{book}” was due on {due}. Return it before reserving or borrowing another book." | "{reader} has an overdue loan: “{book}”, due {due}. It must be returned first." |
| `already_on_loan` | The reader already has this book on loan | "You already have “{book}” on loan." | "{reader} already has “{book}” on loan." |
| `already_reserved` | The reader already has an active reservation of this book | "You already reserved “{book}”. Collect it from a librarian before {deadline}." | — |
| `reservation_limit` | The reader has 3 active reservations | "You already have 3 active reservations, the most allowed. Collect or cancel one to reserve another book." | — |
| `no_copy_available` | No unit of stock is free | "No copy of “{book}” is available right now. Try again later or choose another book." | "No copy of “{book}” is available. A reservation may be holding the last one." |
| `reservation_expired` | Issuing at or after the deadline | — | "This reservation expired at {deadline}. You can lend the book directly only if a copy is available." |
| `already_issued` | Issuing a reservation twice | — | "This reservation was already issued as loan #{loan}." The body adds `"loan": <id>`. |
| `not_active` | Cancelling or issuing a cancelled or expired reservation | "This reservation is no longer active." | "This reservation is {state}; nothing was changed." |

The rules run in the order of R13, and the first one that fails is the one reported. A refusal
changes nothing.

## Web routes

| Route | Method | PR | Audience | Effect |
|---|---|---|---|---|
| `/book/<id>/` | GET | 5 | Signed-in | Shows the reserve button. When reserving is not possible, it shows why instead, using the message above. |
| `/order/reserve/<book_id>/` | POST | 5 | Signed-in | Reserves. Success redirects to My reservations with the deadline in the message; a refusal returns to the book page with its message. |
| `/order/reservations/` | GET | 5 | Signed-in | My reservations: the state, the creation time, the deadline and the next step (FR-019). Cancellations show their time and reason. |
| `/order/reservations/<id>/cancel/` | GET, POST | 6 | The reservation's reader, or a librarian | GET confirms what will happen; the librarian's form asks for the reason. POST cancels. |
| `/order/reservations/<id>/notice/dismiss/` | POST | 6 | The reservation's reader | Hides the library's cancellation notice |
| `/order/reservations/desk/` | GET | 6 | Librarian | Active reservations by deadline: the reader, the book, the time left, and issue and cancel. PR 7 completes the page. |
| `/order/reservations/<id>/issue/` | GET, POST | 6 | Librarian | The loan period form (14 days by default, 1 to 30), then issue |
| `/order/lend/` | GET, POST | 6 | Librarian | Lend directly: reader, book and loan period |
| `/order/create/<book_id>/` | GET | 6 | Signed-in | Redirects readers to the book page and librarians to `/order/lend/?book=<id>` |

Data changes use POST with CSRF (Principle II). Pages that show a deadline also show the time left
and the zone.

## Analytics (FR-023)

- The reserve button carries `data-track-event="borrow_intent"` and `data-book-id`. The client
  event API is unchanged.
- `order_created` is recorded for the reader, with `properties.issued_by` set to the librarian's id.
  It is recorded after commit, and a broker outage never blocks the loan.
- Reservations create no analytics events of their own.

## Concurrency guarantees (FR-011, FR-012, FR-015)

| Situation | Result |
|---|---|
| N readers reserve the last copy at once | Exactly 1 succeeds; the others get `no_copy_available` |
| A reservation and a librarian's loan race for the last copy | Exactly 1 succeeds |
| One reader sends several reservations at once | They never hold more than 3 active reservations |
| A double click, a retry or two librarians issue the same reservation | One loan; the other request gets `already_issued` |
| A reservation expires while it is being issued | The deadline is checked again at commit, so the reservation is either issued in time or refused |
