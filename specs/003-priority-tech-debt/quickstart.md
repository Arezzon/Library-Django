# Quickstart: Validating the Priority Technical Debt Work

**Plan**: [plan.md](plan.md) | **Contracts**: [contracts/](contracts/)

Run the checks from the repository root with Docker, in Git Bash or another POSIX shell, unless a
step says otherwise. Each pull request has its own section. CI repeats the automated parts on both
architectures; steps marked **(manual)** are done by a person, and **(Pi)** steps by the operator on
the Raspberry Pi.

Shorthand used below:

```bash
DC="docker compose -f docker-compose-dev.yml"
APPS="authentication author book order events"      # PR 8 adds audit
BASE=http://localhost:8000
```

## 0. Shared checks

### 0.1 Before every pull request

```bash
python -m pip install -r requirements-dev.txt
ruff check . && black --check .
DJANGO_SEED=true $DC up --build -d --wait
$DC exec -T web python manage.py collectstatic --noinput
$DC exec -T -e CELERY_TASK_ALWAYS_EAGER=True web python manage.py test $APPS
```

Coverage of the lines the pull request adds or changes (FR-051). PRs 1 and 2 record this result in
their description; from PR 3 on, CI posts it:

```bash
$DC exec -T -e CELERY_TASK_ALWAYS_EAGER=True web sh -c \
  "pip install -q coverage==7.16.2 && coverage run --rcfile=/app/pyproject.toml manage.py test $APPS \
   && coverage xml --rcfile=/app/pyproject.toml -o coverage.xml"
git fetch origin main
(cd library && diff-cover coverage.xml --compare-branch=origin/main)
```

**Expected**: lint, format and tests pass, and diff coverage is at least 85%. If it is lower, the
pull request lists the uncovered lines and why.

### 0.2 Record counts

Used by PRs 4 and 9, and on the Pi. Add `order_reservation` from PR 4 and `audit_auditentry` from
PR 8.

```bash
COUNTS="select 'accounts', count(*) from authentication_customuser
union all select 'authors', count(*) from author_author
union all select 'author-book links', count(*) from author_author_books
union all select 'books', count(*) from book_book
union all select 'book vectors', count(*) from book_bookembedding
union all select 'loans', count(*) from order_order
union all select 'events', count(*) from events_userevent"
$DC exec -T db psql -U postgres -d library_db -At -F ' ' -c "$COUNTS"
```

On the Pi, use `docker exec library-db-1 psql -U <DB_USER> -d <DB_NAME> …`, replacing `library`
with the stack name.

### 0.3 Sign in from the shell

```bash
login() {  # login <email> <password> <cookie jar>
  curl -fsS -c "$3" -b "$3" -o /dev/null "$BASE/authentication/login/"
  curl -fsS -c "$3" -b "$3" -o /dev/null -X POST "$BASE/authentication/login/" \
    -H "Referer: $BASE/authentication/login/" \
    --data-urlencode "csrfmiddlewaretoken=$(awk '$6 == "csrftoken" {print $7}' "$3")" \
    --data-urlencode "email=$1" --data-urlencode "password=$2"
}
login reader@library.com reader123password /tmp/reader.jar          # seeded demo accounts
login librarian@library.com admin123password /tmp/librarian.jar
```

## 1. PR 1: access control (KAN-24)

### 1.1 Automated

The access tests and the schema test pass, along with the existing tests, which now sign in with
the role each one needs ([access-control.md](contracts/access-control.md), "Tests that enforce this
contract").

### 1.2 Anonymous callers (SC-001)

```bash
for url in /api/v1/ /api/v1/version/ /api/schema/ /api/docs/; do
  curl -s -o /dev/null -w "%{http_code} $url\n" "$BASE$url"; done      # 200 each
for url in "/api/v1/books/search/?q=detective" /api/v1/book/ /api/v1/author/ /api/v1/user/ /api/v1/order/ /api/v1/user/1/order/; do
  curl -s -o /dev/null -w "%{http_code} $url\n" "$BASE$url"; done      # 401 each
curl -s -o /dev/null -w "%{http_code}\n" -X POST -H 'Content-Type: application/json' \
  -d '{"name":"x","count":1}' "$BASE/api/v1/book/"                      # 401; no book is created
curl -sI "$BASE/api/v1/user/" | grep -i '^www-authenticate: Session'
```

### 1.3 A reader (Story 1 scenarios 2, 5 and 6)

```bash
me=$($DC exec -T db psql -U postgres -d library_db -At \
     -c "select id from authentication_customuser where email='reader@library.com'" | tr -d '\r')
csrf() { awk '$6 == "csrftoken" {print $7}' "$1"; }
curl -s -o /dev/null -w "%{http_code}\n" -b /tmp/reader.jar -X PATCH -H "X-CSRFToken: $(csrf /tmp/reader.jar)" \
  -H 'Content-Type: application/json' -d '{"first_name":"New","role":1}' "$BASE/api/v1/user/$me/"   # 403
curl -s -o /dev/null -w "%{http_code}\n" -b /tmp/reader.jar "$BASE/api/v1/user/1/"                 # 404 unless 1 is the reader
curl -s -o /dev/null -w "%{http_code}\n" -b /tmp/reader.jar "$BASE/api/v1/user/999999/"            # 404 as well
curl -s -o /dev/null -w "%{http_code}\n" -b /tmp/reader.jar -X DELETE \
  -H "X-CSRFToken: $(csrf /tmp/reader.jar)" "$BASE/api/v1/book/1/"                                  # 403
```

**Expected**: the reader's role and name are unchanged after the first call. Run the §0.2 counts
before and after to confirm that nothing changed.

**(manual)** In a browser, as the reader:
- The sign-up page shows no role or status.
- Registering while posting `role=1` (browser developer tools) creates a reader.
- The profile page shows names only.
- `/book/create/` shows the 403 page.

### 1.4 CI

The endpoint step shows anonymous search answering 401, then the signed-in search answering 200.
The memory check signs in as the demo reader.

### 1.5 After deployment (Pi)

1. `/api/v1/version/` reports the merge commit.
2. Review the librarian accounts (R7):
   - open `/admin/authentication/customuser/?role__exact=1`;
   - fix every account that is not an authorized librarian;
   - record the date, the number reviewed and the changes in the pull request.
3. Only now commit `specs/003-priority-tech-debt/`. It goes in the first pull request that opens
   next (FR-060).

## 2. PR 2: query counts (KAN-18)

1. Each `test_queries.py` passes. Each list uses the same number of queries with 1 row and with 50
   rows (SC-010).
2. Run the author API test on `main` first, to record the before count. It fails there, growing with
   the authors. Record the counts before and after in research.md's Measurements.
3. **(Pi)** Time the catalog:

   ```bash
   BUDGET_CHECK_PASSWORD=… python3 scripts/smoke_stack_budget.py --project-name library \
     --base-url http://localhost:8000 --email <account> --max-memory-gib 4 \
     --max-search-p95-ms 500 --max-catalog-p95-ms 2000
   ```

   **Expected**: `"result": "PASS"`, with the catalog p95 under 2000 ms. Record it, with the date.

## 3. PR 3: tests and coverage (KAN-21)

1. The new tests pass, including `author/tests.py` and `authentication/test_routes.py`.
2. The pull request shows the diff-coverage report: in the job summary and in one comment that each
   push updates.
3. The defects are fixed:
   - Saving a profile no longer changes the account's creation time.
   - A negative number of copies is refused by the form, the API and the admin site.

## 4. PR 4: reservation model (KAN-55)

### 4.1 Upgrade over existing data (FR-022)

```bash
git switch --detach origin/main && DJANGO_SEED=true $DC up --build -d --wait
$DC exec -T db psql -U postgres -d library_db -At -F ' ' -c "$COUNTS" > /tmp/counts-before.txt
git switch feat/kan-55-reservation-model && $DC up --build -d --wait     # no `down -v`
$DC exec -T db psql -U postgres -d library_db -At -F ' ' -c "$COUNTS" > /tmp/counts-after.txt
diff /tmp/counts-before.txt /tmp/counts-after.txt && echo "No existing row changed"
$DC logs web | grep "Applying order.0004"
```

### 4.2 Deletion is protected in every channel (FR-024)

As the librarian, try to delete a book that has a loan:
- API: 409.
- Web: the edit page shows the "has borrowing history" message.
- Admin site: "Cannot delete book", listing the protected loans.

The book and its loans remain.

### 4.3 Documents

`docs/adr/0001-reservations-hold-a-unit-of-stock.md` exists and is listed in `docs/adr/README.md`.

## 5. PR 5: reserving (KAN-56)

1. **(manual)** As the reader, reserve an available book on its page:
   - My reservations shows it as active, with a deadline exactly 48 hours later in Kyiv time and the
     zone shown (for example "EET").
   - The available count drops by one on the catalog, the book page, search and the API.
2. Through the API, each refusal answers 409 with its code
   ([reservations-api.md](contracts/reservations-api.md)):
   - `POST /api/v1/reservation/ {"book": <id>}` again: `already_reserved`;
   - a 4th reservation: `reservation_limit`;
   - a book with no free copy: `no_copy_available`;
   - a reader with an overdue loan, made by setting a past due date on a loan as the librarian:
     `overdue_loan`, naming the book and its due date.
3. The race and expiry tests pass:
   - Two readers on the last copy: exactly 1 succeeds.
   - A reservation racing a loan: exactly 1 succeeds.
   - One reader sending 5 at once: at most 3 active.
   - The deadline: 1 second before, the copy is held; at 48 hours, it is not.
4. The scheduled expiry runs: within 5 minutes of a deadline, the worker's log shows that
   reservations were expired.
5. The reader can still borrow (FR-061): their own loan of a reserved book issues that reservation,
   and the available count stays the same.
6. CI's memory check passes, with beat now running in the worker (Principle VI).

## 6. PR 6: issuing at the desk (KAN-57)

1. **(manual)** As the librarian, on the desk page, issue an active reservation with a 14-day loan:
   - exactly one loan exists;
   - the reservation is issued;
   - the available count did not change at that moment.
2. Issue the same reservation again through the API: 409 `already_issued`, with the loan's id. Still
   one loan.
3. An expired reservation: 409 `reservation_expired`.
4. Cancel without a reason: refused, and nothing changes. Cancel with a reason:
   - the copy is free at once;
   - the reader's next page shows the notice with the time and the reason;
   - Dismiss hides it.
5. As the reader:
   - starting a loan through the web goes to the book page;
   - the API answers 403;
   - issuing any reservation answers 403;
   - cancelling another reader's reservation answers 404;
   - cancelling their own needs no reason.
6. The analytics dashboard counts the borrow for the reader. The event's properties name the
   librarian in `issued_by`.

## 7. PR 7: complete pages and acceptance (KAN-58)

1. The journey tests pass, through the web and the API, from both sides of the desk.
2. CI's reservation burst prints PASS: 100 simultaneous attempts on one copy, exactly 1 success, 20
   times (SC-002).
3. **(Pi)** Run the load check at a quiet time:

   ```bash
   python3 scripts/smoke_reservation_load.py --project-name library --base-url http://localhost:8000 \
     --burst 100 --readers 30
   ```

   **Expected**:
   - the burst holds exactly 1 copy;
   - the p95 of reserve, issue and cancel is under 3000 ms (SC-003);
   - the temporary readers and book are removed afterwards.

   Record the JSON in Measurements.

## 8. PR 8: logs and audit (KAN-67)

1. Every response carries an identifier: `curl -sI "$BASE/" | grep -i '^x-request-id'`.
2. Find a request in both services (SC-008). Set `rid` to the `X-Request-ID` of a request that
   published an event, for example a book page view, then:

   ```bash
   $DC logs --no-log-prefix web worker | grep "$rid"
   ```

   **Expected**: the worker's lines for the event, each with the header and the id.
   `smoke_test_tracking` in CI asserts the same. A successful request writes no web line, because
   the access log stays off; a refused or failing request adds its web lines with the same id.
3. A failing request's traceback lines all carry its identifier (a test covers this).
4. **(manual)** Make each critical change once, for example a role change in the admin site or a loan
   return on the web. `/admin/audit/auditentry/` shows exactly one entry each, with the actor, the
   channel and the before and after values. The admin site offers no edit or delete.
5. A forced audit failure, in a test, rolls the change back.
6. CI's log check passes: no secret, demo password or search word appears in any service's log
   (SC-007).
7. Rotation is configured: `docker inspect --format '{{json .HostConfig.LogConfig}}' $($DC ps -q
   web)` shows `json-file` with `max-size` 10m and `max-file` 5.
8. `LOG_LEVEL=WARNING $DC up -d web` hides INFO lines.

## 9. PR 9: backups and restore (KAN-68)

### 9.1 A backup and a trial restore (FR-025, FR-029)

```bash
$DC exec -T backup library-backup once                   # INFO "created …; check passed"
$DC exec -T backup ls -l /backups                        # .dump and .sha256, mode -rw-------
file=$($DC exec -T backup sh -c 'ls -1t /backups/*.dump | head -1' | tr -d '\r')
$DC exec -T db createdb -U postgres library_restore
$DC exec -T backup pg_restore --no-owner --exit-on-error -d library_restore "$file"
diff <($DC exec -T db psql -U postgres -d library_db -At -F ' ' -c "$COUNTS") \
     <($DC exec -T db psql -U postgres -d library_restore -At -F ' ' -c "$COUNTS") && echo "Counts match"
$DC exec -T db dropdb -U postgres library_restore
```

### 9.2 Retention (Story 4 scenario 6)

```bash
$DC exec -T backup sh -c 'for d in 1 2 3 4 5 6 7 8 9 10; do
  f=/backups/library-$(date -u -d "$d days ago" +%Y%m%dT010000Z).dump; : > "$f"; touch -d "$d days ago" "$f"; done'
$DC exec -T backup library-backup once
$DC exec -T backup sh -c 'ls -1 /backups/*.dump | wc -l'   # 8: the new one plus ages 1 to 7 days
```

Then remove the fake files.

### 9.3 A failure (FR-027)

```bash
$DC stop db
$DC exec -T backup library-backup once; echo "exit $?"   # non-zero
$DC logs --tail 3 backup                                  # ERROR with the cause
$DC exec -T backup ls /backups                            # earlier backups still there
$DC start db
```

### 9.4 On the Pi (Pi)

1. **The daily backup**: the next morning, `docker logs --tail 5 library-backup-1` shows the
   successful run.
2. **The weekly copy** ([backups.md](contracts/backups.md)): `sha256sum -c` and `pg_restore --list`
   pass on the other machine.
3. **The restore rehearsal**: follow [backups.md](contracts/backups.md), "Restore into a separate
   database", and time it from `createdb` to a passing search. Record the rehearsal (FR-029).
4. **Persistence** (FR-030, SC-005): take the counts (§0.2), then for each service:

   ```bash
   for s in db redis web worker backup; do
     docker restart library-$s-1; start=$(date +%s)
     until curl -fsS -o /dev/null http://localhost:8000/api/v1/version/; do sleep 2; done
     echo "$s: back in $(( $(date +%s) - start )) s"
   done
   ```

   Repeat after a redeploy in Portainer and after `sudo reboot`, timing the reboot from another
   machine. **Expected**: the counts match every time, each recovery takes under 3 minutes, and
   every time is recorded.
5. **Cold start**: after 24 hours without traffic, run §2 step 3. The first catalog load is as fast
   as the rest.
6. **Limits** (FR-031):
   - `docker system df -v` for the volumes, and `df -h /`;
   - `sudo du -ch /var/lib/docker/containers/*/*-json.log | tail -1` for the logs;
   - memory, from §2 step 3;
   - confirm that the Render services are gone (operator guide, "Shut down Render").

   Record each.

## 10. PR 10: accessibility (KAN-69)

1. The automated check reports 0 violations:

   ```bash
   npm ci --prefix scripts/a11y && npx --prefix scripts/a11y playwright install chromium
   node scripts/a11y/check_pages.mjs --base-url "$BASE"
   ```

2. The template test passes: every displayed time shows its zone.
3. **(manual)** Keyboard only: complete each main task in Story 6. The focus order is logical, the
   focus is always visible and never trapped, and every action can be confirmed.
4. **(manual)** With NVDA in Firefox or Chrome, complete the reservation and issuing journeys. Every
   field, error and change of state, such as a new deadline or a refusal, is announced.
5. **(manual)** The walkthrough (FR-045):
   - at least 3 people new to the system, at least 1 of them with little digital experience;
   - for each attempt, record the task, whether it finished without help, and the problems seen;
   - **Expected**: at least 80% of attempts finish without help, and every problem is fixed or
     registered.

## 11. PR 11: administrator role (KAN-70)

1. `docker exec -it library-web-1 python manage.py createsuperuser` creates an administrator.
   `python manage.py set_administrator <email>` promotes an existing account, and `--remove`
   reverses it. Each leaves an audit entry with channel `command`.
2. As a librarian, granting or removing the librarian role is refused through the web, the API and
   the admin site, where the field is read-only. Activating and deactivating accounts still work.
3. As an administrator, the same role change works: the account is kept, and the audit entry exists
   (Story 1 scenario 8).

## 12. Repository settings (KAN-72, KAN-73, KAN-74; Arsen)

```bash
gh api repos/Arezzon/Library-Django/rulesets/23898585 > ruleset-$(date +%F).json
```

**Expected**:
- `required_status_checks` lists `lint` and `smoke-test`;
- a `code_scanning` rule names CodeQL;
- `require_code_owner_review` is `true`.

For each rule, open a draft pull request that breaks it:
- a lint error;
- a failing test;
- a new CodeQL alert;
- no approval from a code owner.

Each shows that merging is blocked. Record the links, then close the drafts (SC-012).

## 13. PR 12: the register and closing (KAN-71)

1. Every item that KAN-62 names has a row in `docs/shared/debt-register.md`.
2. Every `closed` row links its evidence.
3. Every `open` row has an owner, a plan and a target sprint.
4. No P1 row is `open` or `blocked` (SC-013).
5. The README and `docs/adr/` describe reservations, issuing by librarians, roles, backups and logs
   as delivered.
6. Jira:
   - KAN-18's and KAN-19's descriptions match the product;
   - KAN-62 links the register;
   - every sub-task's status matches its pull request.
