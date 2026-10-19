# Contract: CI pipeline (`.github/workflows/docker-build.yml`)

**Covers**: FR-001 – FR-005, FR-015 – FR-020, FR-025, FR-032, US2, US3 and the constitution's
quality gates (v2.0.0, item 4).

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
| `publish` | matrix: `ubuntu-24.04`, `ubuntu-24.04-arm` | `lint`, `smoke-test` | Each architecture's image is pushed by digest |
| `merge` | `ubuntu-latest` | `publish` | The multi-architecture manifest is created and tagged |
| `deploy` | `ubuntu-latest` | `merge` | Webhook returns 2xx, the secret is absent (warning), or `merge` reports `main` moved on (notice) |

`publish`, `merge` and `deploy` share
`concurrency: { group: publish-${{ github.ref }}, cancel-in-progress: false }`.

## `smoke-test` steps (per architecture)

1. `node --test scripts/test_tracking_js.cjs`
2. Server file validity: `docker compose -f docker-compose.yml config --quiet`, with placeholder
   `SECRET_KEY` and `DB_PASSWORD` values.
3. Generate disposable secrets and mask them.
4. Build the app image with the per-architecture GHA cache and load it as `library-django:dev`.
5. `docker compose -f docker-compose-dev.yml up -d --wait --no-build`, with `DJANGO_SEED=true`.
6. Check the image refuses to start without `SECRET_KEY`.
7. Collect static files for the mounted source.
8. `manage.py test authentication author book order events`, with
   `RUN_BOOK_EMBEDDING_MODEL_TESTS=1` and `CELERY_TASK_ALWAYS_EAGER=True`. This includes the
   18-query evaluation set, which must rank all 18 expected books first.
9. Endpoint checks: `/api/docs/`, `/api/schema/`, semantic search and `/api/v1/`.
10. `manage.py smoke_test_tracking`
11. `python scripts/smoke_tracking_recovery.py --compose-file docker-compose-dev.yml`
12. `python scripts/smoke_stack_budget.py --compose-file docker-compose-dev.yml --max-memory-gib 4`
13. Teardown (`always()`).

No Render step remains.

## Image references

The image is `ghcr.io/<lowercased repository>` (`ghcr.io/arezzon/library-django`).

| Run | Tags written | `latest` |
|---|---|---|
| `main` push, still the head of `main` | `main`, `sha-<short>` | never |
| `main` push, `main` has since advanced | `sha-<short>` only; `deploy` is skipped with a notice | never |
| `v1.2.3` tag | `1.2.3`, `sha-<short>` | never |

Every tag resolves to a manifest list with `linux/amd64` and `linux/arm64`.

## `deploy` behavior

| Condition | Result | Log text (no URL, no host) |
|---|---|---|
| `PORTAINER_WEBHOOK_URL` is empty | Job succeeds | `::warning::` "Images <tags> published; server deployment skipped because PORTAINER_WEBHOOK_URL is not configured." |
| `merge` reported that `main` advanced | Job succeeds | `::notice::` "A newer commit is on main; it will deploy itself." |
| POST returns 2xx | Job succeeds | "Redeploy triggered for <tags> (HTTP <code>)." |
| Non-2xx, timeout (300 s), DNS failure or TLS failure | **Job fails** | `::error::` "Images <tags> were published, but the server was not redeployed (HTTP <code> / curl exit <n>)." |

**Call details**:
- The request is `curl --silent --output /dev/null --write-out '%{http_code}' --max-time 300
  --request POST "$PORTAINER_WEBHOOK_URL" 2>/dev/null`.
- TLS verification is always on; `-k` is never used (FR-020).
- The secret is passed through `env:` only, never as a command-line argument or in workflow
  text.

## Required repository settings

These are done by an admin and documented in the guide:
- Actions secret `PORTAINER_WEBHOOK_URL`.
- Workflow permissions: `packages: write` for `publish` and `merge`, which already exists.
- GHCR package visibility: public, as it is today.
