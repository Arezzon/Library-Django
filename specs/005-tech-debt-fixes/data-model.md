# Data Model: Technical Lead's Debt Fixes (KAN-90)

No database change and no migration. The entities below describe the work and the access answers it
changes.

## Issue

A KAN issue in this feature's scope.

| Field | Values |
| ----- | ------ |
| key | KAN-79, KAN-80, KAN-94, KAN-96, KAN-97, KAN-101, KAN-102 |
| register item | TD-36, TD-37, TD-20, TD-22, TD-23, TD-31, TD-35 |
| kind | `change`, or `decision` (KAN-80 only, decided by @Arezzon) |
| assignee | must be @fazelukario when it is moved |
| status | To Do → In Progress → In Review |
| group | A, B, C or D |

**State transitions** (the only moves this work makes):

```text
To Do ──(group starts; transition 31)──▶ In Progress ──(PR open and CI passed; comment; transition 41)──▶ In Review
```

- **Guard on both moves**: just before the move, the issue is still @fazelukario's and in the source
  status. Otherwise it is skipped and reported.
- **Not made**: Idea, To Do (back), Done. A failed CI keeps the issue In Progress.

## Group

| Group | Issues | Branch | Order |
| ----- | ------ | ------ | ----- |
| C | KAN-96, KAN-97 | `fix/kan-96-97-sign-out-and-admin-password` | 1 |
| A | KAN-79, KAN-80 | `fix/kan-79-80-not-found-page` | 2 |
| B | KAN-94 | `test/kan-94-browser-sign-in-ci` | 3 |
| D | KAN-101, KAN-102 | `test/kan-101-102-route-list-and-test-command` | 4 |

**State**: waiting → in progress → in review. Only one group is in progress at a time.

## Pull request

| Field | Rule |
| ----- | ---- |
| base | `main`, branched from a freshly fetched `origin/main` |
| title | `<action>(<service>): <description>` with the issue keys ([contracts/pull-requests.md](contracts/pull-requests.md)) |
| description | `.github/PULL_REQUEST_TEMPLATE.md`, with the keys and TD IDs, verification steps and only true DoD items checked |
| changelog | one new entry at the top of `docs/shared/changelog.md` |
| assignee | @fazelukario, checked after creation |
| CI | every check passed before its issues move to In Review |
| merge | not merged by this work |

## Web access answer

One row of the web access table (`authentication/test_routes.py::ROUTES`, copied from
`specs/003-priority-tech-debt/contracts/access-control.md`): method, route, and the expected answer
for an anonymous caller, a reader and a librarian. An answer is a status (200, 403, 404, 405) or a
redirect target.

Changes made by this feature (details in [contracts/web-access.md](contracts/web-access.md)):

| Change | Group |
| ------ | ----- |
| Reader on a librarian-only route: 403 → 404 | A |
| `GET /authentication/logout/`: signs out → 405, session kept | C |
| `POST /authentication/logout/`: added, signs out | C |
| Seven web patterns with no row get rows | D |
| A walk of the URL configuration requires a row for every web pattern | D |

**Validation**: every row except sign-in, registration and sign-out has at least one permitted and
one refused caller (Principle II).

## Admin user form

| Form | Password field | On save |
| ---- | -------------- | ------- |
| Change an existing user | Read-only hash with a link to `<id>/password/` | Password unchanged |
| Add a user | Password and confirmation | Password set, hashed |
| Change password (`<id>/password/`) | New password and confirmation | Password set, if `may_change_account` allows the actor |
