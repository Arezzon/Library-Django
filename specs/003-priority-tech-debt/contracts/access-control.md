# Contract: Who may call each operation (PR 1, extended by PRs 5, 6 and 11)

**Requirements**: FR-001 to FR-007, FR-063, SC-001 | **Research**: R2 to R7, R26

This table is the source for PR 1's access tests. A change to it changes the tests, the schema's
`x-audience` labels and the README's API table in the same PR.

## Audiences

| `x-audience` | Who | Permission class |
|---|---|---|
| `anonymous` | Anyone, signed in or not | DRF `AllowAny` |
| `signed-in` | Any active, signed-in account | `IsSignedIn` |
| `signed-in-read` | Signed-in accounts read; librarians change | `ReadOnlyOrLibrarian` |
| `self-or-librarian` | The account the record belongs to, or a librarian. Readers see only their own records. | `IsSelfOrLibrarian` |
| `librarian` | Librarians; from PR 11, also administrators | `IsLibrarian` |
| `administrator` (PR 11) | Administrators | `IsAdministrator` |
| none declared | Nobody: the default is `DenyAll` | `DenyAll` |

## API operations (from PR 1)

"Own" means that the record belongs to the caller. A dash means that the operation does not apply.

| Path | Method | Anonymous | Reader | Librarian |
|---|---|---|---|---|
| `/api/v1/` | GET | 200 | 200 | 200 |
| `/api/v1/version/` | GET | 200 | 200 | 200 |
| `/api/schema/`, `/api/docs/`, `/api/redoc/` | GET | 200 | 200 | 200 |
| `/api/v1/books/search/?q=` | GET | 401 | 200 | 200 |
| `/api/v1/book/`, `/api/v1/book/{id}/` | GET | 401 | 200 | 200 |
| `/api/v1/book/` | POST | 401 | 403 | 201 |
| `/api/v1/book/{id}/` | PUT, PATCH | 401 | 403 | 200 |
| `/api/v1/book/{id}/` | DELETE | 401 | 403 | 204; from PR 4, 409 if the book has loans or reservations |
| `/api/v1/author/`, `/api/v1/author/{id}/` | GET | 401 | 200 | 200 |
| `/api/v1/author/` | POST | 401 | 403 | 201 |
| `/api/v1/author/{id}/` | PUT, PATCH, DELETE | 401 | 403 | 200 or 204 |
| `/api/v1/user/` | GET, POST | 401 | 403 | 200 or 201 |
| `/api/v1/user/{id}/` | GET | 401 | Own: 200. Other: 404. | 200 |
| `/api/v1/user/{id}/` | PUT, PATCH | 401 | Own: 200 for name fields. 403 if the body has `role`, `is_active`, `email` or `password`. Other: 404. | 200. From PR 11, 403 if the body changes `role` and the caller is not an administrator. |
| `/api/v1/user/{id}/` | DELETE | 401 | 403 | 204 |
| `/api/v1/order/` | GET | 401 | 200, own loans only | 200, all loans |
| `/api/v1/order/{id}/` | GET | 401 | Own: 200. Other: 404. | 200 |
| `/api/v1/order/` | POST | 401 | 201 for themselves until PR 6, 403 for another reader. From PR 6, 403. | 201 |
| `/api/v1/order/{id}/` | PUT, PATCH, DELETE | 401 | 403 | 200 or 204 |
| `/api/v1/user/{uid}/order/` | GET | 401 | `uid` is self: 200. Otherwise: 404. | 200 |
| `/api/v1/user/{uid}/order/` | POST | 401 | `uid` is self: 201 until PR 6, then 403. Otherwise: 404. | 201 |
| `/api/v1/user/{uid}/order/{id}/` | GET | 401 | Own: 200. Otherwise: 404. | 200 |
| `/api/v1/user/{uid}/order/{id}/` | PUT, PATCH, DELETE | 401 | 403 | 200 or 204 |
| `/api/v1/events/` | POST | 401 | 202 | 202 |

Operations added later, detailed in [reservations-api.md](reservations-api.md):

| Path | Method | PR | Anonymous | Reader | Librarian |
|---|---|---|---|---|---|
| `/api/v1/reservation/` | GET | 5 | 401 | 200, own | 200, all |
| `/api/v1/reservation/{id}/` | GET | 5 | 401 | Own: 200. Other: 404. | 200 |
| `/api/v1/reservation/` | POST | 5 | 401 | 201 or 409 | 201 or 409 (for themselves) |
| `/api/v1/reservation/{id}/cancel/` | POST | 6 | 401 | Own: 200. Other: 404. | 200, with a reason unless the reservation is their own |
| `/api/v1/reservation/{id}/issue/` | POST | 6 | 401 | 403 | 201 or 409 |

**Validation runs after the access check**: a permitted caller can still get 400 for an invalid
body, or 409 for a refused reservation.

## Web routes (from PR 1)

| Route | Anonymous | Reader | Librarian |
|---|---|---|---|
| `/authentication/login/`, `/authentication/register/` | The page | Redirect home | Redirect home |
| `/authentication/logout/` | Redirect to sign-in | Signs out | Signs out |
| `/authentication/` | Redirect to sign-in | Redirect home | Redirect home |
| `/` | Redirect to sign-in | Home | Home |
| `/book/`, `/book/<id>/` | Redirect to sign-in | The page | The page |
| `/book/create/`, `/book/update/<id>/`, `/book/user/<id>/` | Redirect to sign-in | 403 | The page |
| `/book/delete/<id>/` (POST) | Redirect to sign-in | 403 | Deletes, or refuses if the book has history |
| `/author/`, `/author/create/`, `/author/update/<id>/`, `/author/delete/<id>/` | Redirect to sign-in | 403 | The page |
| `/order/my/` | Redirect to sign-in | Own loans | Own loans |
| `/order/create/<book_id>/` | Redirect to sign-in | Self-loan until PR 6. From PR 6, redirect to the book page. | The lend form, from PR 6 |
| `/order/all/`, `/order/update/<id>/`, `/order/close/<id>/` (POST) | Redirect to sign-in | 403 | The page |
| `/authentication/users/` | Redirect to sign-in | 403 | The page |
| `/authentication/users/<id>/` | Redirect to sign-in | Own: the page. Other: 403. | The page |
| `/authentication/users/<id>/update/` | Redirect to sign-in | Own: names only. A POST with `role` or `is_active` gets 403, and nothing changes. Other: 403. | Names, role and status. From PR 11, role only for administrators. |
| `/events/` | Redirect to sign-in | 403 | The dashboard |
| `/admin/` | Admin sign-in | Admin sign-in (not staff) | The admin site. From PR 11, `role` is read-only unless the caller is an administrator. |

PRs 5 to 7 add the reservation routes listed in [reservations-api.md](reservations-api.md).

## Refusal responses

| Case | Web | API |
|---|---|---|
| Not signed in | 302 to `/authentication/login/?next=<path>`, which shows "Sign in to continue." | 401, `{"detail": "Authentication credentials were not provided."}`, `WWW-Authenticate: Session` |
| Signed in, not allowed | 403 page: "You don't have permission to do this." with a link home | 403, `{"detail": "You do not have permission to perform this action."}` |
| A record the caller may not read | 403, before any lookup | 404, `{"detail": "No … matches the given query."}`, the same as for a missing record |
| A forbidden field (role, status) | 403, and nothing changes | 403, and nothing changes |

No refusal returns any field of the protected record (FR-004).

## Schema annotation (FR-005)

Every operation in `/api/schema/` has:
- `x-audience`, with one of the values above;
- a description that ends with `Audience: <plain-language audience>`;
- the 401 and 403 responses, unless its audience is `anonymous`, and 404 when readers see only their
  own records. Each response uses DRF's `{"detail": string}` body.

## Identities for automated clients (FR-006)

| Client | Identity |
|---|---|
| CI endpoint checks | The seeded demo reader (`reader@library.com`), signed in with a cookie jar. CI also checks that anonymous search answers 401. |
| `scripts/smoke_stack_budget.py` | `--email`, with the password from `BUDGET_CHECK_PASSWORD` or a prompt |
| `manage.py smoke_test_tracking` | Signs in already; unchanged |
| `scripts/smoke_reservation_load.py` (PR 7) | Temporary readers with sessions, made inside the web container and deleted afterwards |

## Tests that enforce this contract

- **Every API URL pattern**: each view declares `permission_classes` itself, without inheriting the
  default. Each operation answers as the table says, for an anonymous caller, a reader and a
  librarian (SC-001).
- **Every web route**: at least one permitted and one refused caller. PR 1 covers the routes that
  change roles or data; PR 3 covers every route (FR-049).
- **Sign-up and the profile page**: a posted `role` or `is_active` never takes effect.
- **The schema**: every operation has `x-audience`.
