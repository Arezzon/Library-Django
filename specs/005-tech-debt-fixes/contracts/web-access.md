# Contract: web answers this feature changes

This is a delta to [spec 003's access-control contract](../../003-priority-tech-debt/contracts/access-control.md).
Rows not named here keep their answers. API answers do not change.

## Signing out (group C, KAN-96)

| Request | Anonymous | Reader | Librarian or administrator |
| ------- | --------- | ------ | -------------------------- |
| `GET /authentication/logout/` | 405 | 405, still signed in | 405, still signed in |
| `POST /authentication/logout/` with a CSRF token | 302 to `/authentication/login/` | Signs out, 302 to `/authentication/login/` | Signs out, 302 to `/authentication/login/` |
| `POST /authentication/logout/` without a CSRF token | 403 (CSRF failure) | 403, still signed in | 403, still signed in |

The header and the mobile menu each render a `<form method="post">` with `{% csrf_token %}` and a
"Log Out" `<button type="submit">`, with the look the links had.

## The "not found" page (group A, KAN-79)

With `DEBUG=False`, any address that resolves to nothing answers **404** with
`library/library/templates/404.html`:

- built on `base.html`, so it shows the caller's header and navigation;
- title "Page Not Found | LibrarySys", a heading, one line of explanation, and a "Go to the home page"
  link to `/`;
- no echo of the requested path;
- WCAG 2.2 AA, checked by `scripts/a11y/check_pages.mjs` for a visitor and for a reader.

## Librarian-only pages and actions (group A, KAN-80)

Every route guarded by `librarian_required`, and any future one guarded by `role_required`:

| Caller | Before | After |
| ------ | ------ | ----- |
| Anonymous | 302 to sign-in with `next` | unchanged |
| Signed-in reader | 403 page | **404**, the same page as an unknown address |
| Librarian, administrator | the page | unchanged |

Owner-scoped routes (`librarian_or_owner_required`, and `user_update` for administrator accounts) keep
403. So do all API endpoints.

**Amendment to spec 003, FR-004**: add this sentence after the existing text.

> Exception (KAN-80, @Arezzon's decision, recorded on 2026-11-04): a signed-in caller who opens a web
> page or action limited to librarians or administrators MUST get the same "not found" answer as an
> address that does not exist, so that the page's existence is not confirmed. The API keeps answering
> 403.

**Contract tables**:

- In "Web routes", the reader cell `403` becomes `404 (KAN-80)` for every librarian-only route.
- In "Refusal responses", the row "Signed in, not allowed" gets, under Web: "404 page for librarian-only
  pages (KAN-80); 403 page for owner-scoped pages".

## The admin user form (group C, KAN-97)

| Admin page | Password |
| ---------- | -------- |
| `/admin/authentication/customuser/<id>/change/` | Shown read-only (algorithm and salt summary), with a link to `../password/`. A submitted `password` value is ignored. |
| `/admin/authentication/customuser/<id>/password/` | Sets a new password. Refused with 403 when `may_change_account` refuses the actor (a librarian on an administrator's account). |
| `/admin/authentication/customuser/add/` | Email, names, and a password with confirmation. The password is stored hashed. |

## Every web route is in the access table (group D, KAN-102)

- `web_routes()` returns every URL pattern outside `api/`, with the whole admin site counted as
  `admin/`.
- Each `ROUTES` entry, once its IDs are filled in, resolves to one of those patterns.
- A test fails, naming the patterns, when a walked pattern matches no entry.
- Rows added (answers are measured on the branch and written into the table and the contract):
  - `GET /assistant/`
  - `GET /assistant/result/`
  - `GET /book/recommendations/`
  - `GET /book/preferences/`
  - `POST /book/<id>/rating/`
  - `POST /book/<id>/preferences/`
  - `GET` and `POST` `/authentication/logout/`
- Sign-out joins sign-in and registration as open to every caller. The "permitted and refused caller"
  check skips these three.
