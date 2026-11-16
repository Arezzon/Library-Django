# Test Summary Report: LibrarySys v2.0

2026-11-16

## Summary

**Conclusion: the build is ready for release.** All executed checks passed, all key reservation, loan and access scenarios work, and there are no critical or serious defects. The only known issue is one cosmetic defect (see section 4). The report covers the latest build, 9ee1369.

| Type | What was checked | Result |
| --- | --- | --- |
| Manual | Acceptance checklist, 40 scenarios | 40 of 40 passed; all 26 mandatory-for-release scenarios passed |
| Manual | Retest of three fixes, 15 test cases | 15 of 15 passed |
| Manual | Check of three new changes, 3 checks | 3 of 3 passed |
| Automatic | Project tests (unit, integration, concurrent requests), 765 | 761 passed, 4 skipped, 0 failed |
| Automatic | Linter and code style check | no remarks |

Defects: 0 critical, 0 serious, 1 cosmetic.

## 1. What was checked

Build 9ee1369 (the latest state of the main branch on 16 November 2026). Period: 14–16 November. Author: Dmytro. All scenarios are described in the [checklist](https://docs.google.com/spreadsheets/d/1VtGUVkRDp2HA35NBh3QCITpQTE01ZkfEoxVvFk4_loM/edit?usp=sharing).

| Area | Manual testing | Automated project tests |
| --- | --- | --- |
| Catalog, search, recommendations | Pass: catalog, search, recommendations, mandatory book title | cover it |
| Loans | Pass: issuing, changing the due date, return | cover it |
| Reservations | Pass: reserving, cancelling, issuing from a reservation, limits, two readers for one copy, reservation duration setting, showing the reader the end date | cover it, including the deadline, concurrent requests and the duration setting |
| Accounts and roles | Pass: rights of a guest, a reader, a librarian, an administrator; account deletion | cover the rights of every role |
| REST API | Pass (partly): access rights, field validation, account deletion | cover every operation for every role |
| Analytics | Pass (partly): only the effect of deleting a reader | cover the overview and the demand forecast |
| Audit log | Pass (partly): viewing, entries about role changes and cancellations | cover it |
| Menu, keyboard, NVDA, mobile width, mobile menu icons | Pass | cover it partly (the "skip to content" link, time zones) |
| Backups and restore | not checked | not in the executed set |

## 2. How we tested

### 2.1. Manual acceptance testing (checklist)

The checklist consists of 40 scenarios. Each describes the role, preconditions, test data, steps, expected result and priority. The expected results are taken from the product documentation, not invented. The scenarios are split into six groups:

| Group | Scenarios | What it checks |
| --- | --- | --- |
| Reader | 11 | sign-in and sign-out, catalog, search, recommendations; reserving for 48 hours, "My reservations", cancelling; refusals (repeat reservation, limit of three, overdue loan); notification about a cancellation by the library |
| Second reader | 2 | conflict over the only copy; an expired reservation does not hold a copy |
| Librarian | 10 | list of reservations on the Desk, issuing for 14 days, repeat issue, issuing an expired reservation, cancelling with and without a reason, direct loan, block for a reader with an overdue loan, changing the due date, return |
| Administrator | 2 | changing the role between reader and librarian, audit log |
| General | 7 | menu by role, keyboard (reader and librarian), NVDA screen reader, mobile width, clear errors, confirmation of irreversible actions |
| Access rights | 8 | guest, reader and librarian on pages and in the API: what is allowed, what is closed (401, 403, 404), sign-up without a choice of role |

Priority: 26 scenarios are mandatory for release (reservations, loans, access rights), 12 are important, 2 are nice to have.

### 2.2. Retest of fixes and check of new changes

Three errors were fixed in this cycle. For each of them, separate test cases were run on test accounts and temporary data. They were run on both builds; on the latest one everything passed.

| What was fixed | Test cases | What was checked |
| --- | --- | --- |
| Book without a title: previously a book with an empty title could be created or saved | 4 | creating and editing on the site, in the admin site and through the API; an empty title and a title of spaces only; changing other fields with a normal title |
| Removing authors: the function removed all authors instead of the given ones | 3 | removing one author, several, an empty list, an absent author; changing authors in the book form and in the admin site, other books of these authors are not affected |
| Deleting an account erased loans and reservations that belong to the library | 8 | open and closed loan, active reservation, who cancelled the reservation, bulk deletion in the admin site, API, analytics, privacy (the name and email of the deleted reader are not visible anywhere) |

Accounts were deleted in the admin site and through the API, because the site has no such button. The function that removes authors from a book is not called by any page, so it was checked through the developer console.

After the first run, three planned changes reached the main branch, and they were checked separately:

| Change | What was checked | Result |
| --- | --- | --- |
| Icons in the mobile menu | every item in the reader menu (8 items) and the librarian menu (11 items) has an icon | Pass |
| Reservation duration setting | page for the librarian: a value of 1–168 hours, 48 by default; a new reservation is held for the set duration, existing ones do not change; 0 and 169 are not saved; a reader gets 404, a guest is sent to sign-in | Pass |
| Showing the reader the reservation end date | the date in the message after reserving matches the date in the list and the deadline in the database, the time zone is shown | Pass |

### 2.3. Automated project tests

This is a set of 765 tests that the developers wrote in the project. The tests work without a person: each one prepares data, performs an action and compares the result with the expected one. They were not changed, only run on the latest build.

**What they cover** (number of tests by area; the sum is 765):

| Area | Tests | What they check |
| --- | --- | --- |
| Books, search, recommendations, ratings | 260 | number of available copies; creating a book and the mandatory title; protecting a book with history from deletion; removing the given authors; semantic search and the search form, counting clicks from search results; recommendations and their reasons; saved books; ratings; book covers; building vectors for search |
| Loans and reservations | 167 | reservation with a set duration and all its states; duration setting; refusals (limit, overdue loan, no copy); automatic expiry of overdue reservations; Desk list, cancellation notices, time left; issuing and returning as one indivisible action; account deletion (open loan, closed loan, reservation, who cancelled) |
| Accounts, access rights, logs | 127 | what each role may do on every page and API operation; deny by default; the "not found" page; templates (messages, action names, time zones, forms); log format, hiding of secrets, request identifier; creating an administrator; migrations |
| Events and analytics | 117 | recording events and actions in the browser; overview by period, empty state, access; demand forecast; saving search queries and clicks |
| Catalog assistant | 47 | searching books in natural language, interface, navigation |
| Authors | 24 | creating, changing, deleting on the site, in the API and in the admin site |
| Audit log | 23 | entries about changes of accounts, loans and books; guarantees of completeness and immutability of entries |

**Types of checks in the set:**

- **Unit tests:** separate rules and formulas (for example, the forecast formula, the countdown to the end of a reservation).
- **Integration tests:** site pages, the API and the admin site together with the database.
- **Concurrent request tests:** two readers reserve the last copy at the same time, simultaneous loans, ratings and settings from several users.
- **Migration tests:** changes to the database structure do not break existing data.
- **Query count tests:** pages do not make more queries when there are more records.

## 3. Results

### Manual testing

| What | Build | Executed | Passed | Failed |
| --- | --- | --- | --- | --- |
| Checklist | 9ee1369 | 40 | 40 | 0 |
| Book without a title | 9ee1369 | 4 | 4 | 0 |
| Removing authors | 9ee1369 | 3 | 3 | 0 |
| Deleting an account | 9ee1369 | 8 | 8 | 0 |
| Three new changes | 9ee1369 | 3 | 3 | 0 |

### Automated project tests

| What | Executed | Passed | Failed | Skipped |
| --- | --- | --- | --- | --- |
| Unit, integration and concurrent request tests | 765 | 761 | 0 | 4 |
| Linter and code style check | 2 | 2 | 0 | 0 |

## 4. Defects

There are no critical or serious defects. One cosmetic defect has not been filed in Jira as a Bug yet.

| Severity | What was found | Where to see it |
| --- | --- | --- |
| Cosmetic | The heading of the Lend Directly page is cut to "Lend Dir…" although there is enough room on the screen. The defect is also present in the latest build | sign in as a librarian → Desk → the Lend Directly button |

## 5. Environment

| Item | Value |
| --- | --- |
| Build | 9ee1369 (first run: 5edca17) |
| OS | Windows 10 22H2 (19045.6466) |
| Browser | Google Chrome 157.0.8103.78 |
| Screen reader | NVDA |
| Python, Django | 3.14.3, 5.2.18 |
| PostgreSQL | 18 with pgvector 0.8.7 |
| Redis | Memurai 4.1.2 (Redis 7.2.5) |
| Data | demo data and test accounts (readers, librarian, administrator, a reader with an overdue loan, a book with one copy) |

## 6. Approval

| Role | Name | Decision | Date |
| --- | --- | --- | --- |
| Test lead | Dmytro | | |
| Product owner | | | |
