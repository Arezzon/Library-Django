---

description: "Task list for automatic deployment to a self-hosted Raspberry Pi"
---

# Tasks: Automatic Deployment to a Self-Hosted Raspberry Pi

**Input**: Design documents from `specs/001-rpi-portainer-deploy/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included. Constitution Principle III (non-negotiable) requires every behavior change
to ship with Django tests that fail without it. Write each test task first, and confirm it fails
before the implementation task that follows it.

**Organization**: Tasks are grouped by user story. The portable embedding model sits in
Phase 2, Foundational, because User Story 1's ARM64 images and the arm64 smoke test need it
(see Dependencies).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US5, as in spec.md)
- Paths are relative to the repository root. Django commands run from `library/`.

---

## Phase 1: Setup (Compose split)

**Purpose**: Rename the development stack so `docker-compose.yml` is free for the server, while
keeping local development and CI working.

- [x] T001 Rename `docker-compose.yml` to `docker-compose-dev.yml` with `git mv`. In `docker-compose-dev.yml`:
  - add `image: library-django:dev` to the `web` and `worker` services, keeping their `build:` blocks;
  - change the usage comments at the top to `docker compose -f docker-compose-dev.yml …`.
- [x] T002 In `.github/workflows/docker-build.yml`:
  - add `-f docker-compose-dev.yml` to every `docker compose` command in the `smoke-test` job (build, up, ps, exec, stop, down);
  - pass `--compose-file docker-compose-dev.yml` to `scripts/smoke_tracking_recovery.py` and `scripts/smoke_render_free.py`, which both already accept it;
  - remove `master` from the `push.branches` and `pull_request.branches` filters, leaving `main` and `tags: ["v*"]` (FR-004).
- [x] T003 [P] Edit two files:
  - `.env.example`: add a commented line `# COMPOSE_FILE=docker-compose-dev.yml`, with a one-line explanation that it lets plain `docker compose` use the local development stack;
  - `AGENTS.md`: change the CI description to say that the tests run inside the `web` service of `docker-compose-dev.yml`.
- [x] T004 [P] Update `README.md`:
  - change every `docker compose …` command to `docker compose -f docker-compose-dev.yml …`, in the TL;DR, Quick start with Docker, Book embeddings, Activity Analytics, Troubleshooting and Tests and checks sections;
  - in Project layout, change the `docker-compose.yml` line to `docker-compose-dev.yml   # local development: web, PostgreSQL, Redis and Celery`.

**Checkpoint**: `docker compose -f docker-compose-dev.yml up --build -d --wait` works locally, and the CI `smoke-test` job passes unchanged apart from the file name.

---

## Phase 2: Foundational (portable embedding model and version endpoint)

**Purpose**: Covers the single model setting, the `bge-m3` int8 switch, untyped vector storage,
startup re-encoding, the image-mismatch check and the `/api/v1/version/` endpoint. Every user
story depends on this phase.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Tests (write first; they must fail)

- [ ] T005 [P] Create `library/book/test_embedding_config.py`, covering [contracts/embedding-model-setting.md](contracts/embedding-model-setting.md) and [data-model.md](data-model.md) §2–3:
  - **Defaults**: `resolve()` returns repository `Xenova/bge-m3`, revision `4de13258303883538bd53b696b452bf8099f0858`, model_file `onnx/model_int8.onnx`, tokenizer_file `sentencepiece.bpe.model`, dimensions `1024`, pooling `cls`, empty query and document prefixes, and max_tokens `512`.
  - **Overrides**: each `BOOK_EMBEDDING_*` override applies. An empty value falls back to the default.
  - **Validation**: errors name the variable for each of these:
    - a revision that isn't 40 hex characters;
    - pooling not in `cls`/`mean`;
    - dimensions ≤ 0;
    - max_tokens outside 8–8192;
    - a model_file containing `avx2`, `avx512` or `vnni`.
  - **Tag**: `.tag` is 40-hex and changes when any spec field changes, but not when `BOOK_EMBEDDING_THREADS` changes.
  - **Manifest**: `read_manifest()` returns `None` for a missing file, and the parsed dict otherwise.
  - **System checks** (temporary `BOOK_EMBEDDING_CACHE_DIR` via `override_settings`):
    - `book.E001` (Error) when the manifest tag differs, and the message names both `<repository>@<revision>`;
    - `book.W001` (Warning) when there is no manifest, naming the cache dir and `python scripts/fetch_embedding_model.py`;
    - no message when the tags match.
- [ ] T006 [P] Update the mocked-encoder tests in `library/book/test_search.py`:
  - import `resolve` from `book.embedding_config` instead of `DIMENSIONS`;
  - build fake vectors with `resolve().dimensions`;
  - expect the encoder to be called with `[resolve().query_prefix + "concept"]` instead of `["query: concept"]`;
  - create fixture embeddings with `model=resolve().repository, model_revision=resolve().tag`.
- [ ] T007 Update `library/book/tests.py`. First, make it model-agnostic:
  - replace `DIMENSIONS`, `MODEL_REVISION` and the hard-coded `"passage: "` with `resolve().dimensions`, `resolve().tag` and `resolve().document_prefix`;
  - assert that stored embeddings have `model == resolve().repository` and `model_revision == resolve().tag`;
  - change the column-type assertion that expects `("vector", DIMENSIONS)` to expect an untyped `vector` column with no dimension (`atttypmod = -1`);
  - keep the XLM-R golden token-ID test unchanged, since `bge-m3` uses the same vocabulary.

  Then add failing startup re-encode tests, using a mocked encoder and `call_command("generate_book_embeddings", offline=True, threads=2)`:
  - books with a stale `model_revision`, no embedding, or changed text are re-encoded;
  - matching books are skipped, and a second run prints `Generated: 0`;
  - when the encoder raises on the second book, the first book keeps its new vector and the command raises `CommandError`.
- [ ] T008 [P] Add version endpoint tests to `library/authentication/tests.py`, per [contracts/version-endpoint.md](contracts/version-endpoint.md):
  - an anonymous `GET /api/v1/version/` returns 200 with exactly one key, `commit`;
  - it returns the `APP_COMMIT` value when set, and `"unknown"` when unset or empty;
  - `POST` returns 405;
  - the response has `Cache-Control: no-store`;
  - the path `/api/v1/version/` appears in the `/api/schema/` output.

### Implementation

- [ ] T009 Create `library/book/embedding_config.py`. It may use only the standard library, and it is the only code file that may name the model.
  - Define a frozen dataclass `EmbeddingSpec` with fields `repository`, `revision`, `model_file`, `tokenizer_file`, `dimensions`, `pooling`, `query_prefix`, `document_prefix` and `max_tokens`.
  - Define `resolve()`, which reads `BOOK_EMBEDDING_MODEL`, `BOOK_EMBEDDING_MODEL_REVISION`, `BOOK_EMBEDDING_MODEL_FILE`, `BOOK_EMBEDDING_TOKENIZER_FILE`, `BOOK_EMBEDDING_DIMENSIONS`, `BOOK_EMBEDDING_POOLING`, `BOOK_EMBEDDING_QUERY_PREFIX`, `BOOK_EMBEDDING_DOCUMENT_PREFIX` and `BOOK_EMBEDDING_MAX_TOKENS` on every call. Empty values mean the default from T005.
  - Validate as in data-model.md §2: `revision` is a "40-hex commit (pinned; no branches or tags)"; `model_file` "MUST NOT name an instruction set (`avx2`, `avx512`, `vnni`)"; `pooling` is "`cls` or `mean`"; `dimensions` is an "Integer > 0"; `max_tokens` is an "Integer from 8 to 8192". Raise `ValueError` naming the variable.
  - Define `.tag` = `hashlib.sha1(json.dumps(dataclasses.asdict(spec), sort_keys=True).encode()).hexdigest()`.
  - Define `threads()`, reading `BOOK_EMBEDDING_THREADS` (default 2, minimum 1).
  - Define `read_manifest(cache_dir)`, reading `<cache_dir>/manifest.json`.
- [ ] T010 [P] Create `scripts/fetch_embedding_model.py`, per contracts/embedding-model-setting.md:
  - Load the config module from `Path(__file__).resolve().parents[1] / "library" / "book" / "embedding_config.py"` with `importlib.util`.
  - Accept `--cache-dir`, defaulting to `$BOOK_EMBEDDING_CACHE_DIR` or `<repo>/.cache/book-embeddings`, and `--print`, which outputs the spec JSON and tag without downloading.
  - Download with `huggingface_hub.snapshot_download(repo_id, revision, cache_dir, allow_patterns=[model_file, tokenizer_file])`.
  - Write `manifest.json` = `{"spec": …, "tag": …, "snapshot_path": …}`.
  - Exit 0 on success, 2 on an invalid setting, and 3 on a failed download. Name no model in this file.
- [ ] T011 Update `Dockerfile`:
  - remove the inline `RUN … snapshot_download(…)` line;
  - after `pip install`, declare `ARG BOOK_EMBEDDING_MODEL BOOK_EMBEDDING_MODEL_REVISION BOOK_EMBEDDING_MODEL_FILE BOOK_EMBEDDING_TOKENIZER_FILE BOOK_EMBEDDING_DIMENSIONS BOOK_EMBEDDING_POOLING BOOK_EMBEDDING_QUERY_PREFIX BOOK_EMBEDDING_DOCUMENT_PREFIX BOOK_EMBEDDING_MAX_TOKENS` with no values, and mirror each into `ENV <name>=${<name>}`;
  - `COPY library/book/embedding_config.py /app/library/book/embedding_config.py` and `COPY scripts/fetch_embedding_model.py /app/scripts/fetch_embedding_model.py`;
  - `RUN HF_HUB_OFFLINE=0 python /app/scripts/fetch_embedding_model.py --cache-dir /app/.cache/book-embeddings`, before `COPY . /app`;
  - keep `BOOK_EMBEDDING_CACHE_DIR=/app/.cache/book-embeddings`, `HF_HUB_OFFLINE=1` and `TOKENIZERS_PARALLELISM=false`.

  The Dockerfile must contain no model name.
- [ ] T012 Rewrite `library/book/embeddings.py` around `resolve()`:
  - **Remove** the `MODEL_NAME`, `SOURCE_REVISION`, `MODEL_REVISION`, `MODEL_FILE` and `DIMENSIONS` constants.
  - **`document_text()`** uses `spec.document_prefix`.
  - **`normalized_vector()`** checks `spec.dimensions`.
  - **The encoder** (rename `SmallE5Encoder` to `OnnxEncoder`):
    - truncates to `spec.max_tokens - 2` SentencePiece pieces, keeping the XLM-R ID offsets;
    - pools with `cls` (`hidden[0, 0]`) or `mean` (the masked mean);
    - uses `intra_op_num_threads=threads()` and `GraphOptimizationLevel.ORT_ENABLE_ALL`.
  - **`load_embedding_model(offline=True)`** always loads `model_file` and `tokenizer_file` from the manifest's `snapshot_path`, with no hub call (FR-033). Keep the `offline` argument for callers, but it has no effect. Raise a clear error naming `scripts/fetch_embedding_model.py` when the manifest is missing.
  - **`regenerate_book_embedding()`** stores `model=spec.repository` and `model_revision=spec.tag`.
- [ ] T013 [P] Update `library/book/search.py` to:
  - encode `spec.query_prefix + query`;
  - filter `embedding__model=spec.repository, embedding__model_revision=spec.tag`;
  - update the module docstring so it names no model.
- [ ] T014 [P] Update `library/book/models.py`:
  - change `BookEmbedding.vector` to `VectorField()`, with no `dimensions`;
  - in `Book.save()`, compare against `resolve().repository` and `resolve().tag` instead of `MODEL_NAME` and `MODEL_REVISION`.

  Then run `python manage.py makemigrations book` from `library/` to create `library/book/migrations/0004_*.py`. It must be an `AlterField` only, with no data deletion.
- [ ] T015 [P] Update `library/book/management/commands/generate_book_embeddings.py`:
  - take the identity from `resolve()`, replacing the imports of `MODEL_NAME` and `MODEL_REVISION`;
  - add `--threads` (an int, default `threads()`) and pass it to the encoder;
  - keep `--offline` as an accepted option with no effect;
  - change the help text to "Generate book embeddings with the configured model and store them in pgvector."
- [ ] T016 [P] Create `library/book/checks.py`, registering `book.E001` and `book.W001` with `django.core.checks.register`, per contracts/embedding-model-setting.md. Add `ready()` to `BookConfig` in `library/book/apps.py` to import `book.checks`.
- [ ] T017 Update `entrypoint.sh`. After `migrate` (which runs the system checks) and the optional seed, add:

  ```sh
  echo "Re-encoding stale book embeddings..."
  python manage.py generate_book_embeddings --offline --threads "$(python -c 'import os; print(min(os.cpu_count() or 1, 4))')"
  ```

  Keep `set -e`, so a failure stops startup (FR-034).
- [ ] T018 Remove the Render memory check, which the new model cannot fit (one `bge-m3` copy is about 610 MB):
  - delete the step "Verify seeded Render service under 512 MiB" from `.github/workflows/docker-build.yml`;
  - delete `scripts/smoke_render_free.py` with `git rm`.
- [ ] T019 [P] Create `library/library/api_views.py` with `VersionView(APIView)`, per [contracts/version-endpoint.md](contracts/version-endpoint.md):
  - `permission_classes = [AllowAny]`, `authentication_classes = []`;
  - `get()` returns `Response({"commit": os.getenv("APP_COMMIT") or "unknown"})` with `Cache-Control: no-store`;
  - decorate it with `@extend_schema` describing the 200 response.

  Then add `path("version/", VersionView.as_view(), name="version")` to `library/library/api_urls.py`.
- [ ] T020 Add the version build argument and a healthcheck:
  - In `Dockerfile`, add `ARG APP_COMMIT=unknown` and `ENV APP_COMMIT=${APP_COMMIT}` as the last instructions before `ENTRYPOINT`, after `T011`.
  - In `docker-compose-dev.yml`, add `args: { APP_COMMIT: "${APP_COMMIT:-unknown}" }` to both `build:` blocks.
  - In `docker-compose-dev.yml`, give `web` a healthcheck:

    ```yaml
    test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/version/', timeout=5)"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 15m
    start_interval: 5s
    ```

**Checkpoint**: with `docker compose -f docker-compose-dev.yml up --build -d --wait`, run `docker compose -f docker-compose-dev.yml exec -T -e RUN_BOOK_EMBEDDING_MODEL_TESTS=1 -e CELERY_TASK_ALWAYS_EAGER=True web python manage.py test authentication author book order events`. It must pass, and quickstart §1–§3 must hold.

---

## Phase 3: User Story 1 - Run the site on the Raspberry Pi from pre-built images (Priority: P1) 🎯 MVP

**Goal**: A self-contained `docker-compose.yml` that Portainer BE deploys from Git, using
multi-architecture images published to GHCR, with the operator's secrets and data that survives
restarts.

**Independent Test**: Follow the guide's US1 sections on a Pi 5 with Portainer BE, and deploy the
stack once by hand. All four containers run, `web` is healthy, the image architecture is
`arm64`, and the data survives a redeploy and a reboot (quickstart §5, §8).

### Tests for User Story 1

- [ ] T021 [P] [US1] Add tests to `library/authentication/tests.py`, using the existing `import_settings()` helper and adding `TRUST_X_FORWARDED_PROTO` and `CSRF_TRUSTED_ORIGINS` to `SETTINGS_ENV`. Keep `RenderSettingsTests` until US4.
  - `TRUST_X_FORWARDED_PROTO=True` yields `SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")`.
  - When it is unset or `False`, the attribute is absent or `None`.
  - `CSRF_TRUSTED_ORIGINS=" https://a.example ,https://b.example,"` yields `["https://a.example", "https://b.example"]`, and the default is `[]`.

### Implementation for User Story 1

- [ ] T022 [US1] In `library/library/settings.py`:
  - add `TRUST_X_FORWARDED_PROTO = os.getenv("TRUST_X_FORWARDED_PROTO", "False") == "True"`;
  - set `SECURE_PROXY_SSL_HEADER` when it, or the legacy `RENDER == "true"` (removed in US4), is true;
  - add `CSRF_TRUSTED_ORIGINS`, parsed from the comma list with whitespace and empty entries dropped (FR-014).
- [ ] T023 [P] [US1] Create the server stack `docker-compose.yml`, exactly per [contracts/server-stack.md](contracts/server-stack.md):
  - **Services** `db`, `redis`, `web` and `worker`:
    - `web` and `worker` use the image `${IMAGE_REPOSITORY:-ghcr.io/arezzon/library-django}:${IMAGE_TAG:-main}`;
    - `worker` has `entrypoint: ["celery"]` and `command: ["-A", "library", "worker", "--loglevel=INFO", "--concurrency=2", "--queues=events"]`.
  - **No `build:` and no bind mounts.**
  - **Data**: named volumes `pgdata` and `redisdata`.
  - **Restarts and dependencies**: `restart: unless-stopped` everywhere, and `depends_on` with `condition: service_healthy`.
  - **Variables**:
    - `SECRET_KEY: ${SECRET_KEY:?Set SECRET_KEY in the Portainer stack environment}`;
    - `DB_PASSWORD` likewise;
    - `DJANGO_SEED: ${DJANGO_SEED:-false}`;
    - `DEBUG: ${DEBUG:-False}`;
    - `ALLOWED_HOSTS: ${ALLOWED_HOSTS:-localhost,127.0.0.1}`;
    - `CSRF_TRUSTED_ORIGINS`, `TRUST_X_FORWARDED_PROTO`, `WEB_CONCURRENCY`, `BOOK_EMBEDDING_THREADS`, `DB_NAME` and `DB_USER`, with the defaults from the contract;
    - no `BOOK_EMBEDDING_MODEL*` variables.
  - **Ports**: `"${WEB_PORT:-8000}:8000"`.
  - **Healthcheck**: the `web` healthcheck from T020.

  Check it with `SECRET_KEY=x DB_PASSWORD=y docker compose -f docker-compose.yml config --quiet`.
- [ ] T024 [US1] Rewrite the `smoke-test` job in `.github/workflows/docker-build.yml`, per [contracts/ci-pipeline.md](contracts/ci-pipeline.md) "smoke-test steps":
  - Run it on `strategy.matrix.runner: [ubuntu-24.04, ubuntu-24.04-arm]`, with `runs-on: ${{ matrix.runner }}`.
  - Step 2: `docker compose -f docker-compose.yml config --quiet` with placeholder secrets.
  - Use `docker/setup-buildx-action@v3`, then `docker/build-push-action@v6` with `load: true`, `tags: library-django:dev`, `build-args: APP_COMMIT=${{ github.sha }}`, `cache-from: type=gha,scope=${{ matrix.runner }}` and `cache-to: type=gha,mode=max,scope=${{ matrix.runner }}`.
  - Start with `docker compose -f docker-compose-dev.yml up -d --wait --no-build`.
  - Extend the endpoint checks with `curl -fsS http://localhost:8000/api/v1/version/ | grep ${{ github.sha }}`.
  - Keep the tracking, recovery and test steps.
  - Keep the "Validate Render free deployment" step until US4.
- [ ] T025 [US1] Replace the `build` job in `.github/workflows/docker-build.yml` with two jobs.
  - **`publish`**:
    - `needs: [lint, smoke-test]`, `if: github.event_name == 'push'`;
    - matrix on the same two runners, with `permissions: { contents: read, packages: write }`;
    - `docker/login-action@v3` to GHCR;
    - `docker/metadata-action@v5` with `images: ghcr.io/${{ github.repository }}`, for its labels;
    - `docker/build-push-action@v6` with `build-args: APP_COMMIT=${{ github.sha }}`, the per-runner GHA cache, the metadata labels, and `outputs: type=image,name=ghcr.io/${{ github.repository }},push-by-digest=true,name-canonical=true,push=true`;
    - upload each digest with `actions/upload-artifact`.
  - **`merge`**:
    - `needs: publish`;
    - download the digests;
    - run `docker/metadata-action@v5` with `flavor: latest=false` and these tags: `type=raw,value=main,enable=${{ github.ref == 'refs/heads/main' }}`, `type=sha,prefix=sha-` and `type=semver,pattern={{version}}`;
    - create the manifest with `docker buildx imagetools create`, one `-t` per tag, over all digests;
    - check that both `linux/amd64` and `linux/arm64` are present with `docker buildx imagetools inspect`.
  - Put `publish` and `merge` in `concurrency: { group: publish-${{ github.ref }}, cancel-in-progress: false }`.
- [ ] T026 [P] [US1] Create the operator guide `docs/deployment/raspberry-pi-portainer.md`, with an opening table that separates "Already done in this repository" from "You do this: on the Pi / in Portainer / in GitHub / in Render" (FR-022). Write these US1 sections:
  - **Prerequisites**: Raspberry Pi 5, 8 GB, 64-bit OS, Docker Engine, Portainer BE managing its local environment with no Edge agent.
  - **Create the stack**: Portainer → Stacks → Add stack → Repository, with the URL `https://github.com/Arezzon/Library-Django`, reference `refs/heads/main` and compose path `docker-compose.yml`. Relative path volumes are not needed.
  - **Environment variables**: the full table from contracts/server-stack.md, including `python -c "import secrets; print(secrets.token_urlsafe(50))"` for `SECRET_KEY`. Warn that `DB_PASSWORD` is fixed when the volume is first created, and that `DJANGO_SEED=true` publishes demo accounts whose passwords are public.
  - **First deployment checklist**: four containers running, `web` healthy, `docker image inspect … --format '{{.Architecture}}'` shows `arm64`, and the home page, `/api/docs/` and a search all answer.
  - **Viewing logs**: in Portainer, and with `docker logs`.
  - **Backup and restore**: `docker exec <db> pg_dump -U postgres library_db > backup.sql`, and restore with `psql`.
- [ ] T027 [P] [US1] Document the new settings in two files:
  - `README.md`:
    - in Configuration, add rows for `TRUST_X_FORWARDED_PROTO` (default `False`; set `True` only behind your HTTPS proxy) and `CSRF_TRUSTED_ORIGINS` (comma list, default empty);
    - at the top of the Deployment section, add a "Raspberry Pi (Portainer)" paragraph linking `docs/deployment/raspberry-pi-portainer.md`;
  - `.env.example`: add commented entries for both settings.

**Checkpoint**: after a push to the branch's pull request, both smoke-test legs pass. After merging, `docker buildx imagetools inspect ghcr.io/arezzon/library-django:main` lists amd64 and arm64, and the operator can deploy US1 by hand.

---

## Phase 4: User Story 2 - Merges to main go live automatically (Priority: P2)

**Goal**: after both architectures are published, CI calls the Portainer webhook from the
`production` environment. The `main` tag only moves forward.

**Independent Test**: with US1 deployed, the `production` environment and the
`PORTAINER_WEBHOOK_URL` secret in place, merge a text change. The Pi shows it within 30 minutes
without manual action. A re-run of an older `merge` job skips moving `main` (quickstart §4, §6).

### Implementation for User Story 2

- [ ] T028 [US2] Make the `merge` job in `.github/workflows/docker-build.yml` move `main` only forward (FR-002, FR-019):
  - check out with `actions/checkout@v4` and `fetch-depth: 0`;
  - on `refs/heads/main`, read the current revision:

    ```sh
    current=$(docker buildx imagetools inspect "ghcr.io/${REPO,,}:main" --format '{{json .Image}}' 2>/dev/null \
      | jq -r '."linux/amd64".config.Labels["org.opencontainers.image.revision"] // empty')
    ```

  - if `current` is empty, or `git merge-base --is-ancestor "$current" "$GITHUB_SHA"` succeeds, include the `main` tag and set the output `deploy=true`;
  - otherwise drop `main` from the tag list, emit `::notice::A newer commit already moved main; this build was published as sha-<short> only.` and set `deploy=false`;
  - on `v*` tags, always set `deploy=true` and never write `main`.
- [ ] T029 [US2] Add a `deploy` job to `.github/workflows/docker-build.yml`, per contracts/ci-pipeline.md "deploy behavior":
  - `needs: merge`, `if: needs.merge.outputs.deploy == 'true'`, `environment: production`, `runs-on: ubuntu-latest`, `permissions: { contents: read }`, in the same concurrency group as T025;
  - pass `env: PORTAINER_WEBHOOK_URL: ${{ secrets.PORTAINER_WEBHOOK_URL }}`;
  - if it is empty, emit `::warning::Images <tags> published; server deployment skipped because PORTAINER_WEBHOOK_URL is not configured.` and exit 0;
  - otherwise run `code=$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 300 --request POST "$PORTAINER_WEBHOOK_URL" 2>/dev/null)`, capturing curl's exit status;
  - on a 2xx status, print `Redeploy triggered for <tags> (HTTP <code>).`;
  - on anything else, emit `::error::Images <tags> were published, but the server was not redeployed (HTTP <code> / curl exit <n>).` and exit 1.

  Never use `-k`, and never echo the variable.
- [ ] T030 [P] [US2] Add these sections to `docs/deployment/raspberry-pi-portainer.md`:
  - **Turn on automatic updates**: open the stack in Portainer, then GitOps updates on → Mechanism **Webhook**, **Re-pull image** on, **Force redeployment** on, and copy the webhook URL.
  - **Make the webhook reachable**:
    - expose only `/api/stacks/webhooks/` through your HTTPS reverse proxy, with a publicly trusted certificate, and keep the Portainer login page off the internet;
    - test from outside your network with `curl -sS -o /dev/null -w '%{http_code}' -X POST <url>`.
  - **Create the `production` GitHub environment** (needs repository admin rights): Settings → Environments → New environment `production` → Deployment branches and tags → Selected: the branch `main` and the tag pattern `v*`. Then add the environment secret `PORTAINER_WEBHOOK_URL`. Note that the first workflow run creates the environment without rules if it doesn't exist yet.
  - **Rotate the webhook**: regenerate it in Portainer, then replace the secret.

**Checkpoint**: quickstart §4 (forward-only `main`, secret scope, webhook visibility) and §6 pass.

---

## Phase 5: User Story 5 - Better search from a portable, configurable model (Priority: P2)

**Goal**: show that `bge-m3` gives good English and Ukrainian search within the Pi budget,
enforce that the model is defined in one place, and warm the model before traffic arrives.

**Independent Test**: the 18-query evaluation set ranks all 18 expected books first on amd64
and on arm64. `smoke_stack_budget.py` passes in CI at 4 GiB. The hard-coding check finds the
model only in `library/book/embedding_config.py` (quickstart §2, §5).

### Tests for User Story 5

- [ ] T031 [P] [US5] Create `library/book/search_evaluation.json`: a list of 18 `{"query", "expected"}` objects with exactly the 9 English and 9 Ukrainian queries and expected seed titles from [research.md](research.md) §R1. In `library/book/test_search.py`, replace `SeededSemanticSearchTests` with a test gated by `RUN_BOOK_EMBEDDING_MODEL_TESTS=1`. It seeds the catalog with `seed_data()`, runs every query through `GET /api/v1/books/search/`, and asserts in a `subTest` per query that `response.json()[0]["name"] == expected`, so 18/18 pass (FR-032, SC-013).

### Implementation for User Story 5

- [ ] T032 [P] [US5] Create `scripts/smoke_stack_budget.py`, using only the standard library and the Docker CLI, per [research.md](research.md) §R8.
  - **Arguments**: `--compose-file`, `--project-name`, `--base-url` (default `http://localhost:8000`), `--max-memory-gib` (default 4), `--max-search-p95-ms`, `--max-save-ms`, `--clients` (default `$WEB_CONCURRENCY` or 3) and `--searches` (default 60).
  - **Project name**: if `--project-name` isn't given, read the `name` from `docker compose -f <file> config --format json`.
  - **Containers**: find them with `docker ps --filter label=com.docker.compose.project=<name>`.
  - **Memory**: sample `docker stats --no-stream --format '{{json .}}'` in a background thread, every 1 s, and sum `MemUsage` across containers.
  - **Load**: after one warm-up search per client, run concurrent searches with queries from `library/book/search_evaluation.json`. Then run 5 book saves with `docker exec <web> python manage.py shell -c …`, creating and then deleting books named `budget-check-<uuid>` and timing each save.
  - **Vectors**: assert that every book's embedding has `model_revision == resolve().tag`.
  - **Output**: print a JSON summary with peak GiB, search p50/p95, and save p50/p95. Exit 1 on any exceeded limit.
- [ ] T033 [P] [US5] Create `library/gunicorn.conf.py`:
  - `workers = int(os.getenv("WEB_CONCURRENCY", "3"))` and `timeout = 60`;
  - `post_worker_init(worker)` imports `book.embeddings` and calls `load_embedding_model()`, so each worker holds its model before taking requests (research R6).

  Change the `Dockerfile` `CMD` to `["gunicorn", "library.wsgi:application"]`. Gunicorn auto-loads `gunicorn.conf.py` from `/app/library`, and the entrypoint's `--bind` logic stays.
- [ ] T034 [US5] Update `.github/workflows/docker-build.yml` in two places:
  - **`smoke-test`**: add `python scripts/smoke_stack_budget.py --compose-file docker-compose-dev.yml --max-memory-gib 4` after the recovery step (step 12).
  - **`lint`**: add a step "Embedding model is defined in one place" that fails on any match:

    ```sh
    git grep -n -I -E 'bge-m3|model_int8|4de13258|multilingual-e5|614241f6' -- . \
      ':!library/book/embedding_config.py' ':!*.md' ':!specs/**'
    ```

    (FR-030)
- [ ] T035 [P] [US5] Rewrite `docs/ba/semantic-search.md` for the new model:
  - `BAAI/bge-m3` dense, from the int8 file in `Xenova/bge-m3`, with CLS pooling, no prefixes and 1024 dimensions;
  - the single `BOOK_EMBEDDING_*` setting, and rebuilding images to change the model;
  - the untyped vector column, and re-encoding on startup;
  - the 18-query evaluation set;
  - the Pi budget check in place of Render Free and the 512 MiB check.
- [ ] T036 [P] [US5] Document the model setting in two files:
  - `README.md` "Book embeddings": the model, `python scripts/fetch_embedding_model.py` for a local `venv`, the build-time `BOOK_EMBEDDING_*` overrides and `docker build --build-arg`, re-encoding on startup, and `WEB_CONCURRENCY` / `BOOK_EMBEDDING_THREADS` tuning;
  - `.env.example`: commented `BOOK_EMBEDDING_*` names, marked "build-time; leave empty for the defaults in library/book/embedding_config.py", plus `BOOK_EMBEDDING_THREADS=2`.
- [ ] T037 [P] [US5] Add a "Measure the stack on the Pi" section to `docs/deployment/raspberry-pi-portainer.md`, per [research.md](research.md) §R14:
  - clone the repository on the Pi;
  - run `python3 scripts/smoke_stack_budget.py --project-name <stack> --max-memory-gib 4 --max-search-p95-ms 500 --max-save-ms 2000`;
  - if it fails, lower `WEB_CONCURRENCY`, then raise `BOOK_EMBEDDING_THREADS`;
  - report the results, so they are recorded in `specs/001-rpi-portainer-deploy/research.md` §R1 (the FR-028 completion gate).

**Checkpoint**: CI passes the evaluation test and the budget step on both runners, and the lint job's hard-coding check passes.

---

## Phase 6: User Story 3 - See deployment failures and recover (Priority: P3)

**Goal**: CI confirms that the Pi actually runs the new commit, and the guide covers pinning,
rollback and resuming.

**Independent Test**:
- With `SITE_URL` set, a merge ends with "Redeploy confirmed".
- While the stack is pinned with `IMAGE_TAG=sha-…`, the confirmation fails with "may be pinned".
- Unpinning returns the site to the newest build (quickstart §7).

### Implementation for User Story 3

- [ ] T038 [US3] Add a confirmation step to the `deploy` job in `.github/workflows/docker-build.yml` (FR-036), running only after a 2xx trigger:
  - check out with `fetch-depth: 0`;
  - read `SITE_URL: ${{ vars.SITE_URL }}`; if it is empty, emit `::notice::Redeploy not confirmed: SITE_URL is not configured for the production environment.` and exit 0;
  - otherwise poll `curl --silent --max-time 10 "$SITE_URL/api/v1/version/"` every 15 s for up to 15 min, parsing `commit` with `jq`;
  - pass when it equals `$GITHUB_SHA`, or `git merge-base --is-ancestor "$GITHUB_SHA" "$reported"` succeeds, printing `Redeploy confirmed: the site runs <commit>.`;
  - on timeout, emit `::error::Redeploy for <tags> was triggered but not confirmed: the site reports <commit or 'no response'>. The stack may be pinned, unhealthy or still starting.` and exit 1.
- [ ] T039 [P] [US3] Add these sections to `docs/deployment/raspberry-pi-portainer.md`:
  - **Confirm deployments**: add the `production` environment variable `SITE_URL`.
  - **What the pipeline messages mean**: a table of every `deploy` warning, notice and error from contracts/ci-pipeline.md.
  - **Pin, roll back and unpin**: set `IMAGE_TAG=sha-<short>` or `<version>` and redeploy; remove it to follow `main` again. Note that while the stack is pinned, the confirmation fails on purpose, and that migrations already applied are not reverted.
  - **Rolling back past this feature**: this is possible only on x86-64 hosts, because older images have no arm64 variant. After pinning, run `docker exec <web container> python manage.py generate_book_embeddings` (research R15).

**Checkpoint**: quickstart §7 passes.

---

## Phase 7: User Story 4 - Retire the Render deployment (Priority: P3)

**Goal**: remove every Render file, check and setting, and document how to shut Render down
after the Pi is verified.

**Independent Test**: the `git grep` from quickstart §8 finds nothing, CI passes without Render
steps, and the guide's Render shutdown section exists.

### Tests for User Story 4

- [ ] T040 [P] [US4] In `library/authentication/tests.py`, replace `RenderSettingsTests` with platform-neutral tests:
  - `ALLOWED_HOSTS` with `ALLOWED_HOSTS="library.example.com, other.example"` equals `["library.example.com", "other.example", "localhost", "127.0.0.1"]`, and contains no `.onrender.com`;
  - `RENDER=true` no longer sets `SECURE_PROXY_SSL_HEADER`.

  Update the module docstring to describe proxy and host settings.

### Implementation for User Story 4

- [ ] T041 [US4] In `library/library/settings.py`:
  - remove `".onrender.com"` from the `ALLOWED_HOSTS` extension, keeping `localhost` and `127.0.0.1` for the healthcheck;
  - remove the `RENDER` condition and the Render comments, so `SECURE_PROXY_SSL_HEADER` depends only on `TRUST_X_FORWARDED_PROTO`.
- [ ] T042 [US4] Delete the Render files and their CI step together:
  - `git rm render.yaml scripts/render_start.py scripts/test_render_start.py scripts/check_render_config.py`;
  - in the same change, delete the "Validate Render free deployment" step from the `smoke-test` job in `.github/workflows/docker-build.yml`.
- [ ] T043 [P] [US4] In `entrypoint.sh`:
  - remove the Render comments, and `export LIBRARY_BOOTSTRAPPED=1` and its comment;
  - keep the generic `$PORT` `--bind` handling, and reword its comment as "platforms that inject PORT".
- [ ] T044 [P] [US4] Remove Render from `README.md`:
  - the Deployment-row mention in the Features table, and the Architecture section;
  - the `render.yaml` line and the Render wording for `scripts/` in Project layout;
  - in the Deployment section, the Render Blueprint paragraphs, leaving the Raspberry Pi section and the production checklist.
- [ ] T045 [P] [US4] Add a "Shut down Render (after the Pi is verified)" section to `docs/deployment/raspberry-pi-portainer.md`:
  - in the Render dashboard, turn off auto-deploy for or delete the `library-django` web service;
  - delete the `library-queue` key-value store and the `library-db` database;
  - remove the Blueprint, so Render stops deploying from `main`.
- [ ] T046 [US4] Run `git grep -n -i -E "onrender|render\.yaml|render_start|smoke_render_free|check_render_config|RENDER\b" -- . ':!specs/**' ':!docs/shared/changelog.md'`. Fix every remaining Render reference until it returns nothing (FR-023).

**Checkpoint**: quickstart §8 (Render retirement) passes, and CI is green.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T047 [P] Delete the `<!-- Sync Impact Report … -->` comment block from the top of `.specify/memory/constitution.md`.
- [ ] T048 [P] Add one entry at the top of `docs/shared/changelog.md`, in the existing format (date line, title line, one paragraph). Date it 2026-10-20 and title it "Raspberry Pi deployment and portable embeddings". It summarizes:
  - the Pi stack deployed from Portainer BE with multi-architecture GHCR images;
  - CI on amd64 and arm64, the forward-only `main` tag, and the deploy and confirmation steps;
  - `bge-m3` int8 with the single model setting and startup re-encoding;
  - Render removed, and constitution v2.0.0.
- [ ] T049 From the repository root, run `ruff check .` and `black --check .` with the versions pinned in `requirements-dev.txt`, and fix every finding.
- [ ] T050 Run the full suite in the dev stack: `docker compose -f docker-compose-dev.yml exec -T -e RUN_BOOK_EMBEDDING_MODEL_TESTS=1 -e CELERY_TASK_ALWAYS_EAGER=True web python manage.py test authentication author book order events --verbosity 2`. Also run `node --test scripts/test_tracking_js.cjs` and `python scripts/smoke_tracking_recovery.py --compose-file docker-compose-dev.yml`.
- [ ] T051 Run [quickstart.md](quickstart.md) §1–§4 and fix any deviation.
- [ ] T052 Operator rollout, outside the repository: follow [quickstart.md](quickstart.md) §5–§8 on the Pi, and record the `smoke_stack_budget.py` results, `WEB_CONCURRENCY` and `BOOK_EMBEDDING_THREADS` in `specs/001-rpi-portainer-deploy/research.md` §R1. This is the FR-028 completion gate. If the latency targets are relaxed under FR-027, update SC-010 and SC-011 in `spec.md`, with the user's sign-off.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup, and blocks every user story. It holds the portable model, because:
  - US1's arm64 images and the arm64 smoke test must not carry the x86-tuned model (FR-026). The current model's worst-case score margin was 0.002 in research R1, so its real-model tests could flip on ARM.
  - The Render 512 MiB check can't pass once `bge-m3` lands (T018).
- **US1 (Phase 3)**: depends on Foundational.
- **US2 (Phase 4)**: depends on US1's `publish` and `merge` jobs (T025) and server stack (T023).
- **US5 (Phase 5)**: depends on Foundational. It is independent of US1 and US2, except that T034 edits the workflow and T037 edits the guide.
- **US3 (Phase 6)**: depends on US2's `deploy` job (T029) and the version endpoint (T019).
- **US4 (Phase 7)**: depends on Foundational. Do it last, because Render stays the fallback until the Pi is verified (spec US4).
- **Polish (Phase 8)**: after all stories. T052 happens on the Pi, after the PR merges.

### Within each phase

- Test tasks (T005–T008, T021, T031, T040) come before their implementation, and must fail first.
- T009 comes before T010, T012 and T016. T012 comes before T013, T014 and T015. T011 comes before T020, which is in the same file.
- Workflow edits are sequential, since they touch the same file: T002 → T018 → T024 → T025 → T028 → T029 → T034 → T038 → T042.
- Guide edits are sequential across phases: T026 → T030 → T037 → T039 → T045.
- `library/authentication/tests.py` edits: T008 → T021 → T040. `library/library/settings.py` edits: T022 → T041.

### Parallel Opportunities

- **Phase 1**: T003 and T004.
- **Phase 2 tests**: T005, T006 and T008, then T007.
- **Phase 2 implementation**:
  - after T009: T010 and T016;
  - after T012: T013, T014 and T015;
  - T019 at any time.
- **US1**: T021, T023, T026 and T027 together; T024 → T025 sequentially.
- **US5**: T031, T032, T033, T035, T036 and T037 together; then T034.
- **US4**: T040, T043, T044 and T045 together.

---

## Parallel Example: Phase 2 (Foundational)

```text
# Tests first, in parallel:
Task: "T005 Create library/book/test_embedding_config.py (spec, tag, validation, manifest, checks)"
Task: "T006 Update library/book/test_search.py to use resolve()"
Task: "T008 Version endpoint tests in library/authentication/tests.py"

# After T012 (embeddings.py), in parallel:
Task: "T013 search.py: query prefix and tag filter"
Task: "T014 models.py: VectorField() + makemigrations book"
Task: "T015 generate_book_embeddings.py: --threads, spec identity"
```

## Parallel Example: User Story 5

```text
Task: "T031 search_evaluation.json + 18-query real-model test"
Task: "T032 scripts/smoke_stack_budget.py"
Task: "T033 library/gunicorn.conf.py + Dockerfile CMD"
Task: "T035 docs/ba/semantic-search.md"
Task: "T036 README Book embeddings + .env.example"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1, Setup: rename the Compose file.
2. Phase 2, Foundational: the portable model and the version endpoint. Run the checkpoint suite.
3. Phase 3, US1: the server stack, the dual-architecture smoke test, the multi-architecture publishing, and the guide's setup sections.
4. **Stop and validate**: deploy by hand on the Pi (quickstart §5). Render keeps running.

### Incremental Delivery

1. Add **US2**: deploy runs automatically on merge.
2. Add **US5**: the evaluation set, the budget check, warm-up, and the check that the model is named in one place.
3. Add **US3**: confirmation, and the rollback guide.
4. Add **US4**: retire Render.
5. **Polish**: then the operator rollout, which is the T052 gate.

The constitution v2.0.0 amendment ships in the same pull request, so intermediate phases never
reach `main` on their own.

---

## Notes

- [P] tasks touch different files and have no unfinished dependencies.
- Commit after each task or logical group, following `.agents/skills/preview-commit/SKILL.md` when a commit is requested.
- Keep `library/requirements.txt` identical to `requirements.txt`. This plan adds no dependency.
- No file other than `library/book/embedding_config.py` may name the model, and the T034 lint step enforces this.
