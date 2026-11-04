# SDD ledger — plan: %LOCALAPPDATA%/Temp/speckit-bridge-library-django-005/plan.md

Spec: specs/005-tech-debt-fixes/spec.md (binding). Canonical tasks: specs/005-tech-debt-fixes/tasks.md.

Pre-flight (shared interfaces between tasks):
- T012/T018 (C) vs T074 (D): sign-out rows in ROUTES depend on whether C merged — handled by T074 branch on base; Ruling: follow tasks.md as written.
- T019 (C, button) vs T059/T060 (B, LOG_OUT locator): locator accepts link or button — consistent.
- T035 (A, NOT_FOUND) vs T074 (D): D measures on its own base; conflicts resolved at T084 — consistent.
- T077 (D constitution names B step) vs T061 (B CI step name): step name "Verify the browser sign-in tests" — consistent.
- Ruling: no git worktree; each group gets its own branch from origin/main in the main checkout, as tasks.md T011/T033/T057/T070 prescribe — spec dir is untracked and lives there — cost if wrong: stray untracked files risk being staged (mitigated by git status before each commit).
Task 1-9 (T001-T009): complete (setup/foundational/US1 prep; no commits; baseline 671/672, 1 broker flake; Jira snapshot + transitions confirmed)
Task 4: Ruling: baseline accepted with 1 transient broker 503 (test_the_api_search) — passes alone and book app green; main CI green — cost if wrong: a real regression masked, rechecked in each full run
Task 21: Ruling: add form keeps is_active (model default False; data-model says "the add page creates a user who can sign in") — cost if wrong: one extra checkbox on the add page
Task 17: Ruling: T012(c) CSRF test passes on unchanged code because CsrfViewMiddleware already refuses token-less POSTs; kept as a guard against csrf_exempt — cost if wrong: one test that never fails
Task 26: Ruling: sign-out row split per caller column (GET 405 in route cell) instead of one cell with blanks — cost if wrong: wording only
Task 25: browser check done with a Playwright script (scratchpad check_group_c.cjs), 15/15 ok; demo reader password restored
Tasks 10-29 (T010-T029): complete (commits 76f4f0d..f4e6cf3, tests: manage.py test authentication author book order events audit ai -> OK 4 skipped; PR #65)
Tasks 30-31: complete (CI green run 41739864978; comments 10030/10031; KAN-96/97 In Review)
Tasks 32-53: complete (commits 76f4f0d..1438f23, tests: full suite OK 4 skipped; a11y 45/0; PR #66)
Task 45: Ruling: two unlisted tests (authentication.tests reader permission page; order.test_reservations readers_cannot_lend) changed 403->404 for librarian-only pages; owner-scoped profile kept at 403 — FR-013a requires it — cost if wrong: none, spec-mandated
Task 34: Ruling: HEADING constant unescaped (template text is not auto-escaped) — test bug — cost if wrong: none
Tasks 54-56: complete (#66 CI green; comments 10033/10034; KAN-79/80 In Review; KAN-94 In Progress)
Tasks 57-66: complete (commits 537613d..78d83d9, tests: selenium x3 -> 4 passed each; PR #67)
Tasks 67-69: complete (#67 CI green, browser step 4 passed; comment 10035; KAN-94 In Review; KAN-101/102 In Progress)
Tasks 70-81: complete (commits 44d05da..0f9b984, tests: full suite OK 4 skipped; removal check named book/preferences/; PR #68)
Task 74: Ruling: POST sign-out row placed last in ROUTES (it ends the session for later rows); rating/preferences POST rows expect 400 for signed-in callers (empty form passes access, fails validation) — cost if wrong: weaker permitted-caller signal on 2 rows
Tasks 82-88: complete (#68 green; comments 10037/10038; end state verified; KAN-98 moved outside this work)
Final review: self-review (no subagent tool used: agents are spawned only on the user's request), against code-reviewer.md, range 76f4f0d..0f9b984 plus 537613d..78d83d9 (#67)
Final: Ruling: admin add path now saves through ModelAdmin.save_model instead of update_account — audit lives in CustomUser.save (AUDITED_ACCOUNT_FIELDS), the add form has no role field, and staff-only admin satisfies LIBRARIAN_ONLY_FIELDS — cost if wrong: an admin-added account skips check_changes on is_active (librarians may already set it)
Final: minor (deferred): POST rating/preferences rows in ROUTES assert 400 (empty form) rather than a successful save
Final: minor (deferred): test_the_admin_user_form_shows_the_password_read_only uses assertNotRegex on the whole page, so a failure dumps the full HTML
Final: minor (deferred): with DEBUG=True a reader on a staff page sees Django's technical 404 (URL list); production runs DEBUG=False
