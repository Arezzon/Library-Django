# Quickstart: Validating the Django 5.2 LTS Upgrade and Dependency Refresh

**Plan**: [plan.md](plan.md) | **Contracts**: [contracts/](contracts/)

Run these checks from the repository root with Docker, unless a step says otherwise. Each pull
request has its own section. CI repeats the automated parts on both architectures; the manual
parts are marked **(manual)**.

Shorthand used below:

```bash
DC="docker compose -f docker-compose-dev.yml"
TEST="python manage.py test authentication author book order events"
```

## 1. Re-check the target versions (before each pull request)

Versions change after 2026-10-20. Re-run this check and replace any pin a newer release
supersedes (FR-001, FR-003).

```bash
python -m pip index versions Django           # newest 5.2.x
python -m pip index versions djangorestframework
# …repeat for each package in the direct group (contracts/runtime-dependencies.md)
```

Confirm that the direct pins resolve to wheels on both architectures:

```bash
for arch in x86_64 aarch64; do
  python -m pip install --dry-run --ignore-installed --only-binary=:all: \
    --python-version 3.12 --implementation cp \
    --platform manylinux_2_17_$arch --platform manylinux_2_28_$arch --platform manylinux_2_34_$arch \
    --target /tmp/resolve-$arch -r requirements.txt
done
```

**Expected**: both runs end with "Would install …" and list the same packages.

## 2. PR 1: runtime dependencies

### 2.1 Baseline from `main` (before changing any pin)

```bash
git switch --detach origin/main
$DC up --build -d --wait
curl -fsS http://localhost:8000/api/schema/ > /tmp/schema-main.yaml
$DC exec -T db psql -U postgres -d library_db -At -c \
  "select (select count(*) from authentication_customuser), (select count(*) from author_author),
          (select count(*) from book_book), (select count(*) from order_order),
          (select count(*) from events_userevent), (select count(*) from book_bookembedding)" \
  > /tmp/counts-main.txt
git switch chore/kan-17-django-5.2-lts      # keep the stack and its volumes running
```

### 2.2 Upgrade in place over the same data (SC-003, FR-006, FR-007)

```bash
$DC up --build -d --wait                    # no `down -v`: the 4.1 database is reused
$DC logs web | grep -E "Applying (authentication|order)\.0003"   # both new migrations ran
$DC exec -T db psql -U postgres -d library_db -At -c "<same query as 2.1>" | diff - /tmp/counts-main.txt
$DC exec -T web python manage.py shell -c "
from django.contrib.auth import authenticate
u = authenticate(email='reader@library.com', password='reader123password')
print(bool(u), u.password.split('\$')[1])"
```

**Expected**:
- the counts are identical (`diff` prints nothing);
- the shell prints `True 1000000`: the stored hash was upgraded from 390000 at sign-in.

### 2.3 API unchanged (SC-004, [contracts/api-compatibility.md](contracts/api-compatibility.md))

```bash
curl -fsS http://localhost:8000/api/schema/ > /tmp/schema-branch.yaml
diff -u /tmp/schema-main.yaml /tmp/schema-branch.yaml
```

**Expected**: no output, or only differences the contract allows. List each one in the PR
description.

### 2.4 Full test suite as CI runs it (SC-001)

```bash
$DC exec -T web python manage.py collectstatic --noinput
$DC exec -T -e RUN_BOOK_EMBEDDING_MODEL_TESTS=1 -e CELERY_TASK_ALWAYS_EAGER=True web $TEST --verbosity 2
```

**Expected**: all tests pass, including the new ones (storage backend, no missing migrations,
password re-hash) and the 18-query evaluation set. No existing test is skipped or weakened.

### 2.5 Deprecation warnings (SC-002, FR-010, FR-012)

```bash
$DC exec -T -e PYTHONWARNINGS=always::DeprecationWarning,always::PendingDeprecationWarning \
  -e CELERY_TASK_ALWAYS_EAGER=True web $TEST 2>&1 \
  | grep -E "Warning:" | sort | uniq -c | sort -rn > /tmp/warnings.txt
grep -E "/app/(library|scripts)/" /tmp/warnings.txt     # warnings from project code
```

**Expected**:
- the second command prints nothing;
- every remaining line of `/tmp/warnings.txt` comes from `site-packages`, and each distinct one is
  a row in `deprecations.md`.

### 2.6 Static files and migration state (FR-008, FR-009, FR-011)

```bash
$DC exec -T web test -f staticfiles/staticfiles.json && echo "manifest storage active"
$DC exec -T web python manage.py makemigrations --check --dry-run   # "No changes detected"
$DC exec -T web python manage.py check --deploy --fail-level ERROR
```

### 2.7 Single dependency list (SC-007, FR-015, FR-016)

```bash
test ! -e library/requirements.txt && echo "duplicate removed"
git grep -n "library/requirements.txt" -- ':!specs/001-*' ':!specs/002-*' ':!.specify/bridge-snapshots' ':!docs/shared/changelog.md'
```

**Expected**: the `git grep` finds nothing. The excluded paths are historical records, plus this
feature's own documents, which describe the removal.

**(manual)** Follow the README's local setup on Windows (PowerShell) or on Linux/macOS from a
fresh virtual environment. A single `pip install -r requirements.txt` completes.

### 2.8 Lint and wrap-up

```bash
ruff check . && black --check .
$DC down -v
```

### 2.9 After merge, on the Pi (manual, SC-005)

Run "Measure the stack on the Pi" from the operator guide. **Expected**: `"result": "PASS"` with
at most 4 GiB and search p95 under 500 ms. Then close Dependabot's Django and DRF pull requests.

## 3. PR 2: lint and format tools

```bash
python -m pip install -r requirements-dev.txt     # black 26.10.1, ruff 0.17.1 (or newer, see §1)
ruff check .                                      # "All checks passed!", no settings warnings
black --check .                                   # "… files would be left unchanged."
```

If the tools ask for changes, apply them (`ruff check --fix .`, `black .`). Then run §2.4
unchanged: every test passes with no assertion edited (SC-008).

## 4. PR 3: database and broker images

### 4.1 Reference counts from a fresh seed

```bash
$DC up --build -d --wait          # new volumes pgdata18 and redisdata8 start empty and are seeded
$DC exec -T db psql -U postgres -d library_db -At -c "select version()"     # PostgreSQL 18.x
$DC exec -T redis redis-server --version                                     # v=8.10.x
$DC exec -T db psql -U postgres -d library_db -At -c \
  "select (select count(*) from author_author), (select count(*) from book_book), (select count(*) from order_order)"
```

Note the three counts. They are the reference values for §4.4 and for step 1 of the reset in
[contracts/service-images.md](contracts/service-images.md).

### 4.2 CI-equivalent checks

Run §2.4, then:

```bash
$DC exec -T web python manage.py smoke_test_tracking
python scripts/smoke_tracking_recovery.py --compose-file docker-compose-dev.yml
python scripts/smoke_stack_budget.py --compose-file docker-compose-dev.yml --max-memory-gib 4
```

**Expected**: all pass. The new test confirms both Compose files use the same images.

### 4.3 Rehearse the reset and rollback locally (manual)

1. On `main` (PostgreSQL 15), start the stack, sign in and create a book. This is your "old" data.
2. Switch to the PR 3 branch and run `$DC up -d --wait`. The site comes up freshly seeded
   (§4.1 counts) and the extra book is gone.
3. Switch back to `main` and run `$DC up -d --wait`. The extra book is back, because the old
   `pgdata` volume was never touched.
4. Clean up with `$DC down -v` and `docker volume rm <project>_pgdata <project>_redisdata`.

### 4.4 On the Pi (manual, SC-009)

Follow the reset in [contracts/service-images.md](contracts/service-images.md) §Reset, steps 1–6.

**Expected**:
- the counts equal the §4.1 reference;
- no book is missing a vector;
- every seeded book is found by search;
- the demo passwords are replaced;
- `smoke_stack_budget.py` passes.
