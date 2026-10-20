# Research: Automatic Deployment to a Self-Hosted Raspberry Pi

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Date**: 2026-10-20

The spec's Clarifications settled every open product question. This document records the
technical decisions behind the plan, with the measurements FR-028 asks for.

## R1. Embedding model: `bge-m3` int8 against the current model (FR-027, FR-028, SC-013)

**Decision**: Use `BAAI/bge-m3` dense embeddings from `Xenova/bge-m3`, file
`onnx/model_int8.onnx`, at revision `4de13258303883538bd53b696b452bf8099f0858`.
- Pooling: CLS (first token), then L2 normalization.
- Prefixes: none for queries or documents.
- Input is truncated to 512 tokens.
- Vectors have 1024 dimensions.

**Measurements** were taken on 2026-10-20 on the developer workstation: x86-64, 32 logical
CPUs, ONNX Runtime 1.30.0, SentencePiece 0.2.1. Both models ran through the same code path the
app uses (XLM-R SentencePiece IDs, one text per call).
- The "seed" set is the 9-book seed catalog with 18 queries: 9 English, and 9 Ukrainian queries
  against English descriptions.
- The "hard" set adds 15 near-duplicate distractor books, including Ukrainian-language ones,
  and 18 harder paraphrased queries.

| Model (int8) | Set | Top-1 | Top-3 | MRR | Median margin (worst) |
|---|---|---|---|---|---|
| `multilingual-e5-small` (current) | seed, 9 books / 18 queries | 18 | 18 | 1.000 | 0.045 (0.002) |
| `bge-m3` | seed, 9 books / 18 queries | 18 | 18 | 1.000 | 0.141 (0.057) |
| `multilingual-e5-small` (current) | hard, 24 books / 36 queries | 24 | 32 | 0.789 | 0.023 (−0.049) |
| `bge-m3` | hard, 24 books / 36 queries | 26 | 34 | 0.843 | 0.053 (−0.069) |

Margin is the cosine score of the expected book minus the best other book.
- On the hard set, e5's worst misses ranked the expected book 9th and 21st (*"Big Brother is
  watching you"* and the same query in Ukrainian).
- `bge-m3`'s worst miss was 4th. Several of its misses are genuinely ambiguous, such as
  *Philosopher's Stone* against *Chamber of Secrets*.

| Model (int8) | Threads | Graph optimization | Memory after load | Query median / p95 | Document median |
|---|---|---|---|---|---|
| e5-small | 1 | off | 171 MB | 3.7 / 4.9 ms | 7.5 ms |
| `bge-m3` | 1 | off | 608 MB | 25.1 / 30.0 ms | 53.7 ms |
| `bge-m3` | 1 | all | 609 MB | 24.4 / 32.7 ms | 59.4 ms |
| `bge-m3` | 2 | all | 609 MB | 16.5 / 20.7 ms | 34.6 ms |
| `bge-m3` | 4 | all | 610 MB | 12.7 / 15.7 ms | 25.1 ms |

**Raspberry Pi 5 estimate (not measured)**: int8 matrix work on a Cortex-A76 at 2.4 GHz is
roughly 6–10× slower than on this workstation. That puts a query at about 100–250 ms with
2 threads, against the 500 ms target in SC-010. A book save would take about 0.25–0.6 s, against
the 2 s target in SC-011. The GitHub ARM64 runners are Neoverse server cores, not Pi-class
hardware, so they can't confirm these numbers. They are confirmed on the Pi with the budget
check during the first deployment (R8, [quickstart.md](quickstart.md) §5), and the measured
values are added to this section. If they miss, R14 applies.

**Rationale**:
- `bge-m3` matches the current model on the seed set and widens the separation 3×.
- It degrades much more gracefully as the catalog grows.
- It's MIT-licensed, so it can be redistributed in public images (FR-029).
- It uses the same XLM-R SentencePiece vocabulary, so the tokenizer code and its golden-ID test
  stay valid, and no new dependency is needed.
- The int8 file is quantized with `per_channel=true`, `reduce_range=true` and `QInt8` weights.
  That is the portable setting, unlike `*_avx2` or `*_avx512_vnni` files (FR-026).

**Alternatives considered**:
- `ibm-granite/granite-embedding-311m-multilingual-r2`: the earlier pick, replaced by the user's
  choice.
- Full-precision `bge-m3` (2.27 GB): about 4× the memory, so 3 web workers wouldn't fit the
  4 GB budget.
- `Xenova/bge-m3` `model_uint8.onnx` / `model_quantized.onnx`: same size, but unsigned weights.
  `model_int8.onnx` is the file the user named.

## R2. One definition of the model (FR-030, FR-031, FR-033)

**Decision**:
- A stdlib-only module, `library/book/embedding_config.py`, is the single source. It holds one
  defaults dict and reads `BOOK_EMBEDDING_*` environment overrides for:
  - model (repository), revision, file and tokenizer file;
  - dimensions, pooling, query prefix, document prefix and maximum tokens.
- It returns a frozen spec plus a derived **tag**: the SHA-1 of the canonical JSON spec, 40
  hex characters.
- `scripts/fetch_embedding_model.py` imports that module and is used both by the Dockerfile and
  locally. It downloads exactly the pinned files and writes `manifest.json`, holding the spec and
  tag, into `BOOK_EMBEDDING_CACHE_DIR`.
- The Dockerfile declares the `BOOK_EMBEDDING_*` names as build `ARG`s mirrored into `ENV`. No
  values are set, so empty means "use the default". It runs the script before `COPY . /app`,
  after copying only the config module and the script, so the model layer stays cached across
  code changes.
- At runtime, the encoder loads files from the manifest's local path only, with no hub call.

**Rationale**:
- Every other place imports the spec: runtime loading, the stored vector tag, search filters,
  the backfill command, tests and the fetch script. Nothing else names the model.
- A rebuild with a different `--build-arg` changes the default image without code edits (FR-033).

**Alternatives considered**:
- A JSON blob in one variable: hard to edit, and error-prone in Portainer and CI.
- Django settings as the source: the fetch script runs during the image build, before Django
  settings can be imported (`SECRET_KEY` is required).
- A registry of several models: rejected in clarification, which settled on one model at a time.

## R3. Runtime setting that differs from the image (edge case)

**Decision**: a Django system check in the `book` app, `book.E001`. It compares the resolved
spec's tag with the image's `manifest.json` and fails with an error naming both models.
- `migrate` runs system checks, so the entrypoint fails before serving any traffic.
- If no manifest exists, which happens in a local `venv` before fetching, the check emits a
  warning, `book.W001`, with the fetch command.

**Rationale**: the check is deterministic, runs on every startup, and needs no inference, which
keeps default test runs free of the model as Principle III requires.

**Alternatives considered**:
- Checking inside `load_embedding_model`: the model loads lazily, so the check would only fire on
  the first search.
- Silently downloading the requested model: forbidden by FR-033.

## R4. Vector storage that follows the model (FR-034, Principle V)

**Decision**: migration `book/0004` changes `BookEmbedding.vector` from `VectorField(dimensions=384)`
to `VectorField()`, an untyped pgvector `vector` column.
- pgvector-python 0.5.0 supports `dimensions=None` and maps it to `vector`.
- Existing rows are kept, but their tag no longer matches, so search excludes them until they
  are re-encoded.
- Vector length is validated in code against `spec.dimensions` (`normalized_vector`).

**Rationale**:
- Model changes need no further migrations, so "storage adapts to the vector size" holds for any
  future model.
- Retrieval is already an exact scan of up to about 1,000 books. A fixed-dimension HNSW or
  IVFFlat index isn't needed.

**Alternatives considered**:
- `vector(1024)` with a data-dropping migration: every future model change would need another
  migration, which conflicts with FR-030.
- A dimension read from settings inside the migration: migrations must be static and
  reproducible.

## R5. Re-encoding on startup (FR-034, SC-014)

**Decision**: `entrypoint.sh` (web only, since the worker overrides the entrypoint with `celery`)
runs these steps, and any failure stops startup (`set -e`):
1. Wait for the database.
2. `migrate`, which also runs the system checks from R3.
3. Seed, if `DJANGO_SEED=true`.
4. `generate_book_embeddings --offline --threads <cores, max 4>`.

The existing command already skips books whose vector matches the current model and text, and
commits each book separately.
- A startup without a model change embeds nothing.
- A failed startup keeps its progress, and the next start resumes.

**Rationale**:
- This reuses the single implementation of "embedding refresh" (Principle I).
- 1,000 books at about 0.3–0.6 s each on the Pi takes 5–10 minutes. Using all cores before
  traffic starts keeps that within SC-014.

**Alternatives considered**:
- Re-encoding in the background in the worker: rejected in clarification, because search would
  return a partial catalog.
- A separate one-off container: Portainer stacks don't order one-shot jobs reliably.

## R6. Web process layout, threads and memory (SC-010 – SC-012)

**Decision**:
- Gunicorn reads `library/gunicorn.conf.py`:
  - sync workers, from `WEB_CONCURRENCY` (default 3);
  - `timeout 60`;
  - a `post_worker_init` hook that loads the model, so each worker is ready before it takes
    requests and its memory is stable.
- ONNX Runtime uses `BOOK_EMBEDDING_THREADS` intra-op threads (default 2) with full graph
  optimization; the measurements show no memory cost for it.
- Estimated stack memory:

  | Part | Estimate |
  |---|---|
  | Web: 3 × (610 MB model + about 100 MB Django) | ≈ 2.1 GB |
  | Gunicorn master | ≈ 0.06 GB |
  | Celery worker (no model) | ≈ 0.25 GB |
  | PostgreSQL | ≈ 0.2 GB |
  | Redis | ≈ 0.03 GB |
  | **Total** | **≈ 2.7 GB of the 4 GB budget** |

**Rationale**: three workers keep today's concurrency, and the budget still has about 1.3 GB of
headroom. Both values can be tuned per server through Portainer variables, without a rebuild.

**Alternatives considered**:
- `--preload`, sharing one model copy through copy-on-write: ONNX Runtime sessions and their
  thread pools aren't safe to use across `fork`.
- `gthread` with one process: one model copy, but a single process failure takes down the whole
  site. It remains available through configuration if memory gets tight.

## R7. CI pipeline (FR-001 – FR-004, FR-015 – FR-020, FR-025, FR-036)

**Decision**: rework `.github/workflows/docker-build.yml`.
- **Triggers**: `push` to `main`, `push` of `v*` tags, and `pull_request` to `main`. `master` is
  dropped.
- **`lint`**: unchanged.
- **`smoke-test`** runs as a matrix on `ubuntu-24.04` and `ubuntu-24.04-arm`, natively.
  1. Tracking JavaScript tests.
  2. `docker compose -f docker-compose.yml config` with placeholder variables, to check the
     server file is valid.
  3. Build the app image with `docker/build-push-action` (`load: true`, GHA cache scoped per
     architecture) under the local tag that `docker-compose-dev.yml` names.
  4. `up --wait --no-build`.
  5. Check that the image refuses to start without a `SECRET_KEY`.
  6. Django tests with real-model tests and the evaluation set (R9).
  7. Endpoint checks.
  8. `smoke_test_tracking`.
  9. `smoke_tracking_recovery.py --compose-file docker-compose-dev.yml`.
  10. `smoke_stack_budget.py`, which checks memory (R8).
  11. Teardown.

  All Render steps are removed.
- **`publish`** runs only for `push` events, `needs: [lint, smoke-test]`, as a matrix on the
  same two native runners. It runs `docker/build-push-action` with the per-architecture GHA cache,
  which makes it close to a no-op rebuild. It pushes by digest and uploads the digests as
  artifacts.
- **`merge`** (`needs: publish`):
  - It creates the multi-architecture manifest with `docker buildx imagetools create`.
  - Tags come from `docker/metadata-action`, with `flavor: latest=false`:
    - on `main`: `type=raw,value=main` and `type=sha,prefix=sha-`;
    - on `v*` tags: `type=semver,pattern={{version}}` and `type=sha,prefix=sha-`.
  - **Forward-only `main` (FR-002, FR-019)**: on `main` pushes, `merge` reads the
    `org.opencontainers.image.revision` label of the image currently tagged `main`, using
    `docker buildx imagetools inspect`. It checks out full history (`fetch-depth: 0`). It moves
    `main` only when there is no current `main` yet, or when
    `git merge-base --is-ancestor <current> "$GITHUB_SHA"` succeeds; a re-run of the same commit
    also passes. Otherwise it pushes only the `sha-` tag and sets the output `deploy=false`.
    - An older run that finishes late can never move `main` back.
    - A newer commit whose pipeline failed never blocks the last good build, because a failed
      run never publishes.
- **`deploy`** (`needs: merge`, `if: needs.merge.outputs.deploy == 'true'`;
  `environment: production`):
  - It runs on the same events as `publish`.
  - The `production` GitHub Environment allows deployments only from the `main` branch and `v*`
    tags. The webhook URL is that environment's secret `PORTAINER_WEBHOOK_URL`, so
    pull-request runs never receive it (FR-016). The environment also records each deployment in
    GitHub's Deployments view.
  - If the secret is empty, it emits `::warning::` and exits 0 (FR-017).
  - Otherwise it calls `curl --silent --output /dev/null --write-out '%{http_code}' --max-time 300
    --request POST "$PORTAINER_WEBHOOK_URL" 2>/dev/null`. TLS is verified because there is no
    `-k`, and stderr is suppressed so the host never appears in logs.
  - Any status other than 2xx, or any curl exit code other than 0, fails the job with: *"Images
    `<tags>` were published, but the server was not redeployed (HTTP `<code>` / curl exit
    `<n>`)."* (FR-018, FR-020)
  - When `merge` sets `deploy=false`, the job is skipped and `merge` emits `::notice::` "A newer
    commit already moved `main`; this build was published as `sha-<short>` only."
- **Confirming the redeploy (FR-036)**: a final step in `deploy` runs after a 2xx response.
  - If the environment variable `SITE_URL` is empty, it emits `::notice::` and exits 0.
  - Otherwise it polls `GET $SITE_URL/api/v1/version/` every 15 s for up to 15 minutes, with TLS
    verified (R13). It passes when the reported commit equals `$GITHUB_SHA`, or descends from it
    (`git merge-base --is-ancestor "$GITHUB_SHA" <reported>`). This handles a tag run on an older
    commit while the Pi follows a newer `main`.
  - On timeout it fails with: *"Redeploy for `<tags>` was triggered but not confirmed: the site
    reports `<commit or 'no response'>`. The stack may be pinned, unhealthy or still starting."*
- **Concurrency**: `publish`, `merge` and `deploy` share
  `concurrency: { group: publish-${{ github.ref }}, cancel-in-progress: false }`.

**Rationale**:
- This is Docker's documented "distribute build across multiple runners" pattern, so there's no
  QEMU and every architecture is built on its own hardware.
- The GHA cache means the publishing build reuses the layers the smoke test already built.
  Estimated time from merge to deploy is about 20–25 minutes, against the 30 minutes in SC-001.

**Alternatives considered**:
- One multi-platform build with QEMU: rejected in clarification, and far slower for the model
  layer.
- Pushing the images the smoke test built: the user asked that publishing happen only after both
  gates pass.
- The `latest` tag as the moving reference: metadata-action moves `latest` on semver tags, which
  conflicts with FR-002.

## R8. Memory and latency budget check, replacing `smoke_render_free.py`

**Decision**: add `scripts/smoke_stack_budget.py`, which needs only the standard library and the
Docker CLI.
- It finds the stack's containers by Compose project label.
- It warms up, then runs concurrent searches from N parallel clients (default
  `WEB_CONCURRENCY`) and a few book saves through `docker exec … manage.py shell`. The test
  books are deleted afterwards.
- While it runs, it samples `docker stats --no-stream` for the summed memory of every container
  in the project.
- It reports:
  - peak memory, asserted against `--max-memory-gib` (default 4);
  - search p50 and p95, and book-save p50 and p95, asserted only when `--max-search-p95-ms` or
    `--max-save-ms` is passed.
- It also asserts that every book's vector carries the current model tag.
- CI runs it on both architectures, enforcing memory only. The operator runs it on the Pi with
  the latency limits, and the results go into R1.

**Rationale**: the constitution (v2.0.0, Principle VI) requires measured memory and latency for
changes that add a model, dependency or background process. Memory doesn't depend on the CPU, so
the CI check guards it; latency is only meaningful on the Pi.

**Alternatives considered**:
- Keeping the 512 MiB Render check: the platform is retired.
- `psutil` inside the container: it misses the database, broker and worker containers.

## R9. Evaluation set in CI (FR-032, SC-013)

**Decision**:
- Store the 18 seed-catalog queries from R1 as data in
  `library/book/search_evaluation.json`: English, and Ukrainian against English text.
- A real-model test, gated by `RUN_BOOK_EMBEDDING_MODEL_TESTS=1`, seeds the catalog, runs every
  query through `/api/v1/books/search/` and asserts that the expected book ranks first, 18/18.
  That is what both models scored, which is SC-013's bar.
- It replaces the existing three-query `SeededSemanticSearchTests` case.

**Rationale**: a single data file serves the test, the documentation and future model changes.
The minimum `bge-m3` margin of 0.057 leaves room for small int8 differences between x86-64 and
ARM64.

**Alternatives considered**: putting the hard distractor set in CI. It adds books that aren't
in the seed and would test the evaluation fixture rather than the product. It stays in this
research note instead.

## R10. Server stack, the Compose split and Portainer BE (FR-006 – FR-013, FR-021)

**Decision**:
- The current `docker-compose.yml` becomes `docker-compose-dev.yml`. It keeps `build:` and the
  source bind mounts, and adds `image: library-django:dev`, so CI can preload the image it built.
- The new `docker-compose.yml` defines four services, `db`, `redis`, `web` and `worker`:
  - The images are `pgvector/pgvector:0.8.2-pg15`, `redis:7.4-alpine` with AOF, and
    `${IMAGE_REPOSITORY:-ghcr.io/arezzon/library-django}:${IMAGE_TAG:-main}`.
  - Every service has `restart: unless-stopped`, and data lives in named volumes `pgdata` and
    `redisdata`.
  - Secrets use `${VAR:?…}`.
  - Seeding defaults to `false`.
  - `web` has a healthcheck: Python `urllib` against `/api/v1/version/` on 127.0.0.1 (R13),
    with `start_period: 15m` to cover startup re-encoding (R5). That endpoint is cheaper than
    generating `/api/schema/` every 30 s.
  - Ports are `${WEB_PORT:-8000}:8000`.
- Relative path volumes aren't needed. The file is self-contained, which keeps it portable to
  Portainer CE or plain `docker compose`.
- Portainer settings for the Git stack:
  - repository URL, `refs/heads/main`, compose path `docker-compose.yml`;
  - GitOps updates → Webhook, with Re-pull image on and Force redeployment on;
  - the webhook is called with `POST https://<portainer>/api/stacks/webhooks/<id>`.

**Rationale**:
- Force redeployment makes every webhook call redeploy, even a version-tag run where the Git
  commit hasn't changed.
- Re-pull image fetches the moved `main` tag.

**Alternatives considered**:
- One Compose file with profiles or overrides: rejected in clarification in favor of two files.
- Relative path volumes for configuration: unnecessary, and they would tie the stack to BE.

## R11. Hosts and HTTPS proxy without Render (FR-014, FR-023)

**Decision**: in `settings.py`:
- Drop the automatic `.onrender.com` host and the `RENDER` switch.
- `ALLOWED_HOSTS` comes from the environment, plus `localhost` and `127.0.0.1`, which the
  healthcheck needs.
- A new `TRUST_X_FORWARDED_PROTO` (default `False`, fail-closed) sets `SECURE_PROXY_SSL_HEADER`
  when `True`.
- A new `CSRF_TRUSTED_ORIGINS` is a comma list, empty by default.
- `RenderSettingsTests` becomes platform-neutral proxy and host tests in
  `library/authentication/tests.py`.

**Rationale**:
- The site works directly over HTTP on the local network with nothing set.
- Behind the operator's HTTPS proxy, one boolean makes Django see requests as secure, so CSRF
  checks on same-origin forms pass.
- The trusted-origins list covers proxies that rewrite the host.

**Alternatives considered**: always trusting `X-Forwarded-Proto`. It lets a direct client spoof
HTTPS, which isn't a safe default (Principle IV).

## R12. Removing Render and updating documents (FR-023, FR-024, US4)

**Decision**:
- Delete `render.yaml`, `scripts/render_start.py`, `scripts/test_render_start.py`,
  `scripts/check_render_config.py` and `scripts/smoke_render_free.py`.
- In `entrypoint.sh`, drop the Render comments and the `LIBRARY_BOOTSTRAPPED` export, which
  only `render_start.py` read. Keep the generic `$PORT` handling.
- Update the README (Quick start, Book embeddings, Tests and checks, Project layout,
  Deployment), `AGENTS.md`, `docs/ba/semantic-search.md` and `.env.example`, and add one
  changelog entry.
- Add the operator guide, `docs/deployment/raspberry-pi-portainer.md` (FR-021, FR-022).
- Remove the Sync Impact Report from the constitution (v2.0.0) before committing.

**Rationale**: the spec and constitution v2.0.0 require one pull request that leaves no
references to Render as a target. The guide's Render shutdown section runs only after the Pi is
verified.

**Alternatives considered**: keeping Render as a warm standby. It would need the 512 MiB
single-container mode and the e5 model, which conflicts with FR-027.

## R13. Reporting the running version (FR-035)

**Decision**:
- The Dockerfile declares `ARG APP_COMMIT=unknown` and mirrors it into `ENV APP_COMMIT`.
  - The declaration sits last in the file, so it never invalidates the dependency or model
    layers.
  - CI passes `APP_COMMIT=${{ github.sha }}` to both the smoke-test build and the publishing
    build.
- `GET /api/v1/version/` returns `{"commit": "<APP_COMMIT>"}`:
  - It is implemented as `VersionView` in a new `library/library/api_views.py` and routed in
    `library/library/api_urls.py`.
  - It sets `permission_classes = [AllowAny]` and `authentication_classes = []`, and is
    described with `extend_schema`.
- Its tests sit in `library/authentication/tests.py`, next to the existing project-wide settings
  tests, because CI only runs the `authentication author book order events` labels. The tests
  cover:
  - anonymous access returning 200;
  - the response containing only `commit`;
  - `unknown` being returned when the variable is unset.

**Rationale**:
- The repository is public, so the commit identifier isn't sensitive.
- An anonymous endpoint that needs no database is the cheapest way for CI to confirm the
  redeploy (FR-036) and for the healthcheck to probe the app (R10).
- Under `/api/v1/` with a declared audience and a schema entry, it complies with Principles I
  and II.

**Alternatives considered**:
- A response header on every page: harder to poll, and it leaks into every response.
- Reading the image label through the Docker API from CI: the Pi's Docker isn't reachable from
  GitHub.

## R14. Pi measurement gate and what happens on a miss (FR-027, FR-028)

**Decision**:
- The plan records the workstation measurements from R1.
- The first deployment runs `smoke_stack_budget.py` on the Pi with `--max-memory-gib 4
  --max-search-p95-ms 500 --max-save-ms 2000`, as in [quickstart.md](quickstart.md) §5. The
  results, threads and workers go into R1.
- The feature is complete only when those pass, or when targets have been relaxed. If they
  fail:
  1. Memory: lower `WEB_CONCURRENCY` (3 → 2) and re-run.
  2. Latency: raise `BOOK_EMBEDDING_THREADS` (2 → 3 → 4), or lower `WEB_CONCURRENCY` to free
     cores, and re-run. Both are Portainer variables, so no rebuild is needed.
  3. If latency still misses, keep `bge-m3`. Record the measured p95 values, and relax SC-010
     or SC-011 to them with the user's sign-off, as a spec edit in the same PR or a follow-up.

**Rationale**: the user chose `bge-m3` for quality, and the targets can only be measured on the
real hardware.

## R15. Rolling back across the model change (edge case)

**Decision**: the guide's rollback section adds a step for pinning an image built before this
feature.
- Those images are `linux/amd64` only: the GHCR manifest for `main` had no arm64 variant on
  2026-10-19. On the Pi, the oldest possible rollback target is therefore the first image of
  this feature. The step applies when the stack runs on an x86-64 host.
- After the pinned stack is healthy, run
  `docker exec <web container> python manage.py generate_book_embeddings` from the Portainer
  console. That image's own command re-encodes with its own model.
- Search then works again.
- Rolling forward re-encodes automatically (R5).
- The untyped `vector` column accepts the older model's 384-value vectors, so no schema step is
  needed.

**Rationale**: older images already contain the backfill command, so recovery is one documented
command.

## Dependency and platform checks

- **Wheels**: every pinned runtime dependency has a `manylinux` aarch64 wheel or is pure Python:
  `onnxruntime` 1.30.0, `sentencepiece` 0.2.1, `psycopg2-binary` 2.9.9, `rpds-py`, `PyYAML`,
  `numpy` (via onnxruntime), Celery and Redis. The arm64 smoke-test job confirms this on every
  run.
- **Base images**: `python:3.12-slim`, `pgvector/pgvector:0.8.2-pg15` and `redis:7.4-alpine`
  are all published for `linux/amd64` and `linux/arm64`.
- **No new runtime Python dependency.** The budget script uses only the standard library.
