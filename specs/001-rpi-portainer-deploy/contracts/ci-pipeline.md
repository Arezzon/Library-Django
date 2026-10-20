# Contract: CI pipeline (`.github/workflows/docker-build.yml`)

**Covers**: FR-001 – FR-005, FR-015 – FR-020, FR-025, FR-032, FR-035, FR-036, US2, US3 and the
constitution's quality gates (v2.0.0, item 4).

## Triggers

| Event | `lint` | `smoke-test` | `publish` → `merge` → `promote` → `deploy` |
|---|---|---|---|
| `push` to `main` | ✔ | ✔ (amd64 and arm64) | ✔ after both gates pass |
| `push` of tag `v*` | ✔ | ✔ (amd64 and arm64) | ✔ after both gates pass |
| `pull_request` to `main` | ✔ | ✔ (amd64 and arm64) | ✘ |
| Any other push | ✘ | ✘ | ✘ |

## Jobs

| Job | Runner(s) | Needs | Pass condition |
|---|---|---|---|
| `lint` | `ubuntu-latest` | none | `ruff check` and `black --check` are clean |
| `smoke-test-matrix` | matrix of native amd64 and arm64 runners (currently `ubuntu-latest`, `ubuntu-24.04`, `ubuntu-24.04-arm`, `ubuntu-26.04`, `ubuntu-26.04-arm`); each leg reports as `smoke-test (<runner>)` | none | Every step in the next section passes on **every** leg, within the 30-minute job timeout |
| `smoke-test` | `ubuntu-latest`, `if: always()`, no permissions | `smoke-test-matrix` | `needs.smoke-test-matrix.result` is `success`. This is the check that the `main` ruleset requires, so its name never changes with the runner list. It fails, rather than being skipped, when a leg fails or is cancelled. |
| `publish` | matrix: `ubuntu-26.04`, `ubuntu-26.04-arm` | `lint`, `smoke-test` | Each architecture's image is pushed by digest, with build argument `APP_COMMIT=${{ github.sha }}` |
| `merge` | `ubuntu-latest` | `publish` | The multi-architecture manifest is created and tagged `sha-<short>` (plus the version for `v*`), and both architectures are verified |
| `promote` | `ubuntu-latest` (checkout with `fetch-depth: 0`) | `merge` | `main` is moved following the rules below. It sets the output `deploy`. |
| `deploy` | `ubuntu-latest`, `environment: production` | `promote` (`if: needs.promote.outputs.deploy == 'true'`) | The webhook returns 2xx and the redeploy is confirmed, or each is skipped with a visible annotation (see below) |

Concurrency (`cancel-in-progress: false` everywhere):
- `promote` runs in `publish-${{ github.ref }}`, so the forward-only check and the `main` write
  for one ref never interleave. GitHub keeps only the newest pending job in a group, so when
  three or more runs overlap, a middle run's `promote` can be cancelled. That is harmless: the
  newer run moves `main` further and deploys.
- `merge` has no group. Its tags belong to one commit, and a cancelled pending `merge` would leave
  that build without its `sha-` tag.
- `deploy` runs in the single group `deploy-production`, because every ref redeploys the same
  stack through the same webhook.
- The `publish` matrix has no group: its legs push by digest only, and a shared group would
  serialize them and let newer pending jobs cancel older ones.

## `smoke-test-matrix` steps (per runner)

1. `node --test scripts/test_tracking_js.cjs`
2. Server file validity: `docker compose -f docker-compose.yml config --quiet`, with placeholder
   `SECRET_KEY` and `DB_PASSWORD` values.
3. Generate disposable secrets and mask them.
4. Build the app image with the per-architecture GHA cache and `APP_COMMIT=${{ github.sha }}`,
   and load it as `library-django:dev`.
5. `docker compose -f docker-compose-dev.yml up -d --wait --wait-timeout 300 --no-build`, with
   `DJANGO_SEED=true`.
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
13. Stack logs (`failure()`), then teardown (`always()`).

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
| Trigger | No answer within 300 s, but the request was sent (`size_request` > 0) | Continue to confirmation | `::warning::` "Portainer did not answer within 300 s; it may still be pulling the images for <tags>. Waiting for the site to confirm the redeploy." |
| Trigger | Non-2xx, timeout before the request was sent, DNS failure or TLS failure | **Job fails** | `::error::` "Images <tags> were published, but the server was not redeployed (HTTP <code> / curl exit <n>)." |
| Confirm | `SITE_URL` is empty after a trigger timeout | **Job fails** | `::error::` "Portainer did not answer in time and SITE_URL is not configured, so the redeploy for <tags> can't be confirmed. Check the stack in Portainer." |
| Confirm | `SITE_URL` is empty | Job succeeds | `::notice::` "Redeploy not confirmed: SITE_URL is not configured for the production environment." |
| Confirm | Within 15 min, `/api/v1/version/` reports `github.sha` or a descendant of it | Job succeeds | "Redeploy confirmed: the site runs <commit>." |
| Confirm | 15 min pass without that | **Job fails** | `::error::` "Redeploy for <tags> was triggered but not confirmed: the site reports <commit / no response>. The stack may be pinned, unhealthy or still starting." |

**Call details**:
- The trigger is `curl --silent --output /dev/null --write-out '%{http_code} %{size_request}'
  --max-time 300 --request POST "$PORTAINER_WEBHOOK_URL" 2>/dev/null`. Portainer answers only
  after pulling the images, so a timeout after the request was sent is handed to confirmation.
- Confirmation polls every 15 s with `curl --silent --max-time 10 "$SITE_URL/api/v1/version/"`.
- TLS verification is always on; `-k` is never used (FR-020).
- The secret is passed through `env:` only, never as a command-line argument or in workflow
  text.

## Required repository settings

These are done by an admin and documented in the guide:
- Environment `production`, with deployment branches and tags limited to `main` and `v*`.
- Environment secret `PORTAINER_WEBHOOK_URL`.
- Optional environment variable `SITE_URL`.
- Workflow permissions: `packages: write` for `publish`, `merge` and `promote`, `contents: read` for all
  jobs.
- GHCR package visibility: public, as it is today.
