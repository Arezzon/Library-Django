# Contract: CI pipeline (`.github/workflows/docker-build.yml`)

**Covers**: FR-001 – FR-005, FR-015 – FR-020, FR-025, FR-032, FR-035, FR-036, US2, US3 and the
constitution's quality gates (v2.0.0, item 4).

## Triggers

| Event | `lint` | `smoke-test` | `publish` → `merge` → `deploy` |
|---|---|---|---|
| `push` to `main` | ✔ | ✔ (amd64 and arm64) | ✔ after both gates pass |
| `push` of tag `v*` | ✔ | ✔ (amd64 and arm64) | ✔ after both gates pass |
| `pull_request` to `main` | ✔ | ✔ (amd64 and arm64) | ✘ |
| Any other push | ✘ | ✘ | ✘ |

## Jobs

| Job | Runner(s) | Needs | Pass condition |
|---|---|---|---|
| `lint` | `ubuntu-latest` | none | `ruff check` and `black --check` are clean |
| `smoke-test` | matrix: `ubuntu-24.04`, `ubuntu-24.04-arm` (native) | none | Every step in the next section passes on **both** |
| `publish` | matrix: `ubuntu-24.04`, `ubuntu-24.04-arm` | `lint`, `smoke-test` | Each architecture's image is pushed by digest, with build argument `APP_COMMIT=${{ github.sha }}` |
| `merge` | `ubuntu-latest` (checkout with `fetch-depth: 0`) | `publish` | The multi-architecture manifest is created and tagged following the rules below. It sets the output `deploy`. |
| `deploy` | `ubuntu-latest`, `environment: production` | `merge` (`if: needs.merge.outputs.deploy == 'true'`) | The webhook returns 2xx and the redeploy is confirmed, or each is skipped with a visible annotation (see below) |

`publish`, `merge` and `deploy` share
`concurrency: { group: publish-${{ github.ref }}, cancel-in-progress: false }`.

## `smoke-test` steps (per architecture)

1. `node --test scripts/test_tracking_js.cjs`
2. Server file validity: `docker compose -f docker-compose.yml config --quiet`, with placeholder
   `SECRET_KEY` and `DB_PASSWORD` values.
3. Generate disposable secrets and mask them.
4. Build the app image with the per-architecture GHA cache and `APP_COMMIT=${{ github.sha }}`,
   and load it as `library-django:dev`.
5. `docker compose -f docker-compose-dev.yml up -d --wait --no-build`, with `DJANGO_SEED=true`.
6. Check the image refuses to start without `SECRET_KEY`.
7. Collect static files for the mounted source.
8. `manage.py test authentication author book order events`, with
   `RUN_BOOK_EMBEDDING_MODEL_TESTS=1` and `CELERY_TASK_ALWAYS_EAGER=True`. This includes the
   18-query evaluation set, which must rank all 18 expected books first, and the version
   endpoint tests.
9. Endpoint checks: `/api/docs/`, `/api/schema/`, `/api/v1/version/` (which must report
   `github.sha`), semantic search and `/api/v1/`.
10. `manage.py smoke_test_tracking`
11. `python scripts/smoke_tracking_recovery.py --compose-file docker-compose-dev.yml`
12. `python scripts/smoke_stack_budget.py --compose-file docker-compose-dev.yml --max-memory-gib 4`
13. Teardown (`always()`).

No Render step remains.

## Image references

The image is `ghcr.io/<lowercased repository>` (`ghcr.io/arezzon/library-django`). Each image
carries the `org.opencontainers.image.revision` label, set by `docker/metadata-action`.

| Run | Tags written | `deploy` output | `latest` |
|---|---|---|---|
| `main` push, and no `main` tag exists yet | `main`, `sha-<short>` | `true` | never |
| `main` push, and the current `main` revision is an ancestor of `github.sha` (or equal to it) | `main`, `sha-<short>` | `true` | never |
| `main` push, and the current `main` revision is **not** an ancestor (a newer build already moved it) | `sha-<short>` only; `::notice::` | `false` | never |
| `v1.2.3` tag | `1.2.3`, `sha-<short>` (`main` is never touched) | `true` | never |

**Rule**: `main` only moves forward in `main`'s history. A newer commit whose pipeline failed
published nothing, so it can't block the last good build (FR-002, FR-019).

Every tag resolves to a manifest list with `linux/amd64` and `linux/arm64`.

## `deploy` behavior

The `production` environment allows only `main` and `v*`. It provides the secret
`PORTAINER_WEBHOOK_URL` and the optional variable `SITE_URL`.

| Step | Condition | Result | Log text (never a URL or host) |
|---|---|---|---|
| Trigger | `PORTAINER_WEBHOOK_URL` is empty | Job succeeds; confirmation is skipped | `::warning::` "Images <tags> published; server deployment skipped because PORTAINER_WEBHOOK_URL is not configured." |
| Trigger | POST returns 2xx | Continue to confirmation | "Redeploy triggered for <tags> (HTTP <code>)." |
| Trigger | Non-2xx, timeout (300 s), DNS failure or TLS failure | **Job fails** | `::error::` "Images <tags> were published, but the server was not redeployed (HTTP <code> / curl exit <n>)." |
| Confirm | `SITE_URL` is empty | Job succeeds | `::notice::` "Redeploy not confirmed: SITE_URL is not configured for the production environment." |
| Confirm | Within 15 min, `/api/v1/version/` reports `github.sha` or a descendant of it | Job succeeds | "Redeploy confirmed: the site runs <commit>." |
| Confirm | 15 min pass without that | **Job fails** | `::error::` "Redeploy for <tags> was triggered but not confirmed: the site reports <commit / no response>. The stack may be pinned, unhealthy or still starting." |

**Call details**:
- The trigger is `curl --silent --output /dev/null --write-out '%{http_code}' --max-time 300
  --request POST "$PORTAINER_WEBHOOK_URL" 2>/dev/null`.
- Confirmation polls every 15 s with `curl --silent --max-time 10 "$SITE_URL/api/v1/version/"`.
- TLS verification is always on; `-k` is never used (FR-020).
- The secret is passed through `env:` only, never as a command-line argument or in workflow
  text.

## Required repository settings

These are done by an admin and documented in the guide:
- Environment `production`, with deployment branches and tags limited to `main` and `v*`.
- Environment secret `PORTAINER_WEBHOOK_URL`.
- Optional environment variable `SITE_URL`.
- Workflow permissions: `packages: write` for `publish` and `merge`, `contents: read` for all
  jobs.
- GHCR package visibility: public, as it is today.
