# Progress: KAN-90 debt fixes

Running record for [tasks.md](tasks.md). Local only; never staged.

## Baseline (T004), 2026-11-04

- `main` = `origin/main` = `76f4f0d`. CI on `76f4f0d`: Docker Build and CodeQL success.
- Lint: `ruff check .` all passed; `black --check .` 169 files unchanged.
- Full suite (`authentication author book order events audit ai`): 672 tests, 1 failure, 4 skipped.
  - The failure: `book.test_queries.BookListQueryTests.test_the_api_search`, 503 instead of 200. The
    search publishes to the dev stack's real Redis broker (`CELERY_BROKER_CONNECTION_TIMEOUT = 1`),
    and the publish timed out once during the 6-minute run. Alone it passes twice; `book` alone passes
    (OK, 4 skipped). Treated as a local broker flake, not a code fault.

## Issues (T005)

| Key | TD | Group | Status | PR | CI | Comment ID | Moves |
| --- | -- | ----- | ------ | -- | -- | ---------- | ----- |
| KAN-79 | TD-36 | A | In Review | #66 | green | 10033 | To Do→In Progress, In Progress→In Review 2026-11-04 |
| KAN-80 | TD-37 | A | In Review | #66 | green | 10034 | To Do→In Progress, In Progress→In Review 2026-11-04 |
| KAN-94 | TD-20 | B | In Review | #67 | green | 10035 | To Do→In Progress, In Progress→In Review 2026-11-04 |
| KAN-96 | TD-22 | C | In Review | #65 | green | 10030 | To Do→In Progress, In Progress→In Review 2026-11-04 |
| KAN-97 | TD-23 | C | In Review | #65 | green | 10031 | To Do→In Progress, In Progress→In Review 2026-11-04 |
| KAN-101 | TD-31 | D | In Review | #68 | green | 10037 | To Do→In Progress, In Progress→In Review 2026-11-04 |
| KAN-102 | TD-35 | D | In Review | #68 | green | 10038 | To Do→In Progress, In Progress→In Review 2026-11-04 |

## KAN-90 snapshot (T006), 2026-11-04

`parent = KAN-90`: 16 children. "Mine" = @fazelukario; "teammate" = any other assignee.

| Key | Status | Assignee |
| --- | ------ | -------- |
| KAN-78 | Idea | teammate |
| KAN-79 | To Do | mine |
| KAN-80 | To Do | mine |
| KAN-81 | Idea | teammate |
| KAN-91 | Idea | teammate |
| KAN-92 | Idea | teammate |
| KAN-93 | Idea | teammate |
| KAN-94 | To Do | mine |
| KAN-95 | Idea | teammate |
| KAN-96 | To Do | mine |
| KAN-97 | To Do | mine |
| KAN-98 | Idea | teammate |
| KAN-99 | Idea | teammate |
| KAN-100 | Idea | teammate |
| KAN-101 | To Do | mine |
| KAN-102 | To Do | mine |

T007: all seven are assigned to @fazelukario and in To Do. None skipped.

T008: on all seven issues, transition `31` leads to "In Progress" and `41` to "In Review" (also
`11` Idea, `21` To Do, `51` Done, unused).

## Comment drafts (T009)

Checked: one line per paragraph, plain link labels, no gendered past-tense verbs.

### KAN-96

PR, що закриває цю задачу: [#<n> <PR title>](<PR url>). Цей самий PR закриває й KAN-97 (TD-23).

Вихід із системи тепер працює лише через POST-форму з CSRF-токеном; GET-запит до `/authentication/logout/` отримує 405, і сесія лишається.

Перевірки CI пройшли, тож задача переходить в **In Review**.

### KAN-97

PR, що закриває цю задачу: [#<n> <PR title>](<PR url>). Цей самий PR закриває й KAN-96 (TD-22).

Форма користувача в адмінці показує хеш пароля лише для читання, з посиланням на форму зміни пароля; збереження форми пароль не змінює.

Перевірки CI пройшли, тож задача переходить в **In Review**.

### KAN-79

PR, що закриває цю задачу: [#<n> <PR title>](<PR url>). Цей самий PR закриває й KAN-80 (TD-37).

Неіснуюча адреса отримує 404 і сторінку `404.html` у стилі LibrarySys, з навігацією й посиланням на головну; перевірка доступності її охоплює.

Перевірки CI пройшли, тож задача переходить в **In Review**.

### KAN-80

Рішення @Arezzon: варіант 1, ховати службові сторінки від читачів.

Причина: відповідь 403 підтверджує читачу, що службова сторінка існує, і розкриває структуру адрес.

Що змінилося: читач, який відкриває сторінку чи дію бібліотекаря або адміністратора, отримує ту саму сторінку 404, що й для неіснуючої адреси. Гостя, як і раніше, перенаправлено на вхід. API лишає 403. FR-004 специфікації 003 доповнено цим винятком.

Борг не залишається, тож дати перегляду немає.

PR: [#<n> <PR title>](<PR url>). Цей самий PR закриває й KAN-79 (TD-36). Перевірки CI пройшли, тож задача переходить в **In Review**.

### KAN-94

PR, що закриває цю задачу: [#<n> <PR title>](<PR url>).

Обрано шлях 1: обидва файли браузерних тестів залишено, і CI запускає їх на кожному PR.

Перевірки CI пройшли, тож задача переходить в **In Review**.

### KAN-101

PR, що закриває цю задачу: [#<n> <PR title>](<PR url>). Цей самий PR закриває й KAN-102 (TD-35).

Конституція й `AGENTS.md` наводять ту саму команду тестів, що й CI, разом з `ai`. Версія конституції 2.5.0, MINOR, а не PATCH: та сама поправка додає до переліку перевірок CI браузерні тести входу з KAN-94 (рішення технічного ліда від 04.11.2026).

Перевірки CI пройшли, тож задача переходить в **In Review**.

### KAN-102

PR, що закриває цю задачу: [#<n> <PR title>](<PR url>). Цей самий PR закриває й KAN-101 (TD-31).

Новий тест обходить усі вебмаршрути й падає, якщо якогось немає в `WebRouteAccessTests`; відсутні маршрути додано.

Перевірки CI пройшли, тож задача переходить в **In Review**.

## Group C (KAN-96, KAN-97)

- Branch `fix/kan-96-97-sign-out-and-admin-password` from `origin/main` `76f4f0d`; group B not merged (T024 not applicable).
- RED (T017), on unchanged code: `test_opening_the_sign_out_address_keeps_the_session` (302≠405), `test_both_log_out_controls_are_buttons_in_csrf_protected_forms` (0≠2), `test_the_admin_user_form_shows_the_password_read_only` (text input), `test_saving_the_admin_user_form_keeps_the_password`, `test_the_admin_password_page_sets_a_new_password`, `test_the_admin_site_sets_passwords_and_a_librarian_adds_readers`, `test_a_librarian_cannot_open_an_administrators_password_page` (302≠403). The CSRF test passed already (middleware); kept as a guard.
- GREEN: `authentication events` OK; full suite OK (4 skipped); lint clean; `smoke_test_tracking` PASS after a web restart; axe 42 pages, 0 violations.
- Browser (T025, Playwright): 15/15 checks ok; header and mobile Log Out by mouse and keyboard; GET 405 keeps the session; admin hash read-only, save keeps the password, password page sets it (demo password restored).
- Commit `f4e6cf3`; PR https://github.com/Arezzon/Library-Django/pull/65, assignee @fazelukario, base `main`.
- CI (T030): run 41739864978 green on all five smoke-test runners, lint, CodeQL. Comments 10030 (KAN-96), 10031 (KAN-97); both In Review (T031).

## Group A (KAN-79, KAN-80)

- Branch `fix/kan-79-80-not-found-page` from `origin/main` `76f4f0d`; group C (#65) not merged.
- RED (T041): full suite on unchanged code: 42 failures and 1 error, all in the tests T034–T040 add or change (23 `ROUTES` subtests, test_not_found ×6, author ×3, book web ×3, book delete, events ×3, order ×3, test_access, role_required error).
- Two tests the plan did not list also expected 403 for a reader on a librarian page: `authentication.tests.AccountWebAccessTests.test_reader_on_a_librarian_page_gets_the_permission_page` (split: `/authentication/users/` → 404 page; another account's profile keeps the 403 page) and `order.test_reservations.DeskTests.test_readers_cannot_lend_issue_or_cancel_someone_elses` (lend, desk, issue → 404). FR-013a covers both.
- GREEN: full suite OK (4 skipped); lint clean; stack on `DEBUG=False`; axe 45 pages, 0 violations, including "not found (visitor)", "not found (reader)" and "staff page as reader".
- Commit `1438f23`; PR https://github.com/Arezzon/Library-Django/pull/66, assignee @fazelukario, base `main`.
- CI (T054) green on all runners, lint, CodeQL. Comments 10033 (KAN-79), 10034 (KAN-80, decision); both In Review (T055).

## Group B (KAN-94)

- Branch `test/kan-94-browser-sign-in-ci` from `origin/main` `537613d`, which already holds group C (#65, merged by @fazelukario). The tests therefore run against the sign-out button.
- T062: three headless runs, `SELENIUM_HEADLESS=1 BASE_URL=http://localhost:8000`, on the restarted web service: 4 passed (22.16 s), 4 passed (17.11 s), 4 passed (17.55 s).
- Lint clean; the workflow YAML parses.
- Commit `78d83d9`; PR https://github.com/Arezzon/Library-Django/pull/67, assignee @fazelukario, base `main`.
- CI (T067): all green; `smoke-test (ubuntu-latest)` job 126297493656, step "Verify the browser sign-in tests": collected 4 items, 4 passed in 13.14 s. Comment 10035; KAN-94 In Review (T068).

## Group D (KAN-101, KAN-102)

- Branch `test/kan-101-102-route-list-and-test-command` from `origin/main` `44d05da`, which includes C (#65) and A (#66), both merged by @fazelukario; B (#67) is open. The new rows therefore use POST-only sign-out and reader 404s.
- T073 RED: `test_every_web_route_is_in_the_table` listed exactly `assistant/`, `assistant/result/`, `authentication/logout/`, `book/<int:book_id>/preferences/`, `book/<int:book_id>/rating/`, `book/preferences/`, `book/recommendations/`.
- T074: answers measured with a throwaway probe test (not committed). Rating and settings POSTs answer a signed-in caller 400 with an empty form. The POST sign-out row moved last, because it ends each client's session.
- T075 (FR-024): with `/book/preferences/` removed, the test failed with `Add these routes to ROUTES: ['book/preferences/']`; restored, `authentication.test_routes` ran 8 tests, OK.
- T077: handoff `blocked` ("constitution amendment for KAN-101"), `/speckit-constitution` to 2.5.0 (item 4: `ai` and the browser sign-in tests; Last Amended 2026-11-04), then handoff `executing`. The Sync Impact Report was removed before the commit and summarised in the PR.
- T079: one hit each in `AGENTS.md:4` and the constitution; `browser sign-in` present; version 2.5.0; the command matches `docker-build.yml`; lint clean; full suite OK (4 skipped).
- Commit `0f9b984`; PR https://github.com/Arezzon/Library-Django/pull/68, assignee @fazelukario, base `main`; asks to merge after #67.
- CI (T082) green on all runners, lint, CodeQL. Comments 10037 (KAN-101), 10038 (KAN-102); both In Review (T083).

## End state (T084–T088), 2026-11-04

- T084: no conflicts. #65 and #66 were merged by @fazelukario during the work; #67 and #68 report MERGEABLE against `main` `44d05da`.
- T085: #65 MERGED, #66 MERGED, #67 OPEN, #68 OPEN; all base `main`, assignee @fazelukario, every check SUCCESS.
- T086: the seven issues are In Review, none in Done, each with exactly one comment from this work that links its PR.
- T087: against the T006 snapshot, the seven changed To Do → In Review; no assignee changed. One teammate issue changed: KAN-98 (TD-24) Idea → To Do → In Progress → In Review at 03:42:29–03:42:36, by the @fazelukario account, outside this work (no Jira call was made between 03:27 and 03:45). Recorded, not touched.

| Criterion | Result | Evidence |
| --------- | ------ | -------- |
| SC-001 | Met for this work | Seven In Review, one PR comment each (10030, 10031, 10033, 10034, 10035, 10037, 10038), none Done. KAN-98 moved outside this work (above) |
| SC-002 | Met, with two already merged | Four PRs, one per group, each assigned to @fazelukario, with a changelog entry and every check green. #65 and #66 were merged by the technical lead, so two remain open |
| SC-003 | Met | `test_opening_the_sign_out_address_keeps_the_session`, `test_signing_out_by_post_...`; browser check 15/15 |
| SC-004 | Met | `test_saving_the_admin_user_form_keeps_the_password`; browser: old password still signs in after save |
| SC-005 | Met | `test_not_found.py`; axe 0 violations on "not found (visitor)" and "not found (reader)" |
| SC-006 | Met | `test_a_reader_on_a_staff_page_gets_the_same_page`; 23 `ROUTES` rows; librarian still 200 |
| SC-007 | Met | #67 CI: "Verify the browser sign-in tests", 4 passed; no other browser test file exists |
| SC-008 | Met | Removal check named `book/preferences/`; 0 routes missing on #68 |
| SC-009 | Met on #68 | Command matches `docker-build.yml` in the constitution and `AGENTS.md`; item 4 names the browser sign-in step |

## Deviations

- Group A: two tests not listed in tasks.md also expected 403 for readers on librarian pages; changed under FR-013a (see Group A).
- Group D: the POST sign-out row sits last in `ROUTES`, not next to sign-in, because it ends the session.
- #65 and #66 were merged by the technical lead during the work, so groups B and D started from a `main` that included them.
- KAN-98 (teammate's) changed status outside this work.
