# Test cases: deleting an account keeps loans and reservations

Retest of the fix: when a reader's account is deleted, the library's loans and reservations are kept (the reader is shown as "Deleted reader").

| Field | Value |
| --- | --- |
| Build | 9ee1369 (first run: 5edca17) |
| Date | 2026-11-16 |
| Account | librarian (`librarian@library.com`); readers are temporary test accounts |
| Executed | by script in Chrome and through the API |

**Preparation:** a fresh `main`, local run, migrations applied. Sign in as a librarian. Use separate test accounts and delete only those. The site has no button to delete a user, so accounts are deleted in the admin site (Custom users) or through the API. Take a database backup before running the cases.

### TC-1. Open loan of a deleted reader

**Steps**

1. The librarian issues a book to a reader (Desk → Lend Directly).
2. Delete this reader.
3. Open All Orders.

**Expected result:** the loan stays and the reader column shows "Deleted reader"; the status is "Pending return". Record Return closes the loan and the book goes back in stock. Edit opens without an error and the reader field shows "Deleted reader".

**Result:** Pass

### TC-2. Closed loans

**Steps**

1. A reader has a closed loan. Delete the account.

**Expected result:** the loan stays in All Orders with the status Closed and "Deleted reader". The book page in the admin site (Books → the book → its loans section) opens and the reader is empty.

**Result:** Pass

### TC-3. Active reservation of a deleted reader

**Steps**

1. A reader reserves a book (book page → Reserve).
2. Delete the reader's account.
3. The librarian opens the Desk.

**Expected result:** the reservation is listed with "Deleted reader". Issue opens a page that explains the account was deleted and the book cannot be issued, with a Cancel Reservation button. Cancelling with a reason frees the copy; the success message does not say that the reader will see the reason.

**Result:** Pass

### TC-4. Who cancelled the reservation

**Steps**

1. Reader A cancels their own reservation. The librarian cancels reader B's reservation with a reason.
2. Reader B sees a notice about the cancellation by the library; reader A does not.
3. Delete the account of the librarian who cancelled (a test librarian).

**Expected result:** on "My Reservations" reader B still sees "The library cancelled it…" and reader A sees "You cancelled it". In the API (`/api/v1/reservation/`) `cancelled_by_library` is `true` for B and `false` for A.

**Result:** Pass

### TC-5. Bulk deletion in the admin site

**Steps**

1. Admin → Users → select two or more test readers who have loans → Delete selected → confirm.

**Expected result:** the confirmation page does not offer to delete loans or reservations. After the deletion they remain in Orders and Reservations in the admin site with "Deleted reader".

**Result:** Pass

### TC-6. API

**Steps**

1. `DELETE /api/v1/user/<id>/` by a librarian for a reader who has a loan.
2. `GET /api/v1/order/`.
3. `POST` a new loan with `"user": null`.
4. `PATCH` the old loan with `user: null` (for example, change `end_at`).

**Expected result:** step 1 answers `204`. In step 2 the loan is there with `"user": null`. Step 3 answers `400` with "A loan needs a reader." Step 4 succeeds.

**Result:** Pass

### TC-7. Analytics

**Steps**

1. Open Analytics before and after deleting a reader who has loans in the period.

**Expected result:** the number of issued books does not change; the number of active readers and the "loans per borrower" distribution do not count the deleted reader. The demand forecast for a book does not change.

**Result:** Pass

### TC-8. Privacy

**Steps**

1. After the deletion, look through the site pages, the admin site and the API.

**Expected result:** the name and email of the deleted reader are not visible anywhere, only "Deleted reader" or `null`. Audit entries created before the deletion are not changed.

**Result:** Pass
