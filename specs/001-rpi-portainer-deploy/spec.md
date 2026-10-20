# Feature Specification: Automatic Deployment to a Self-Hosted Raspberry Pi

**Feature Branch**: `feat/move-from-render-to-dedicated-rpi-host`

**Created**: 2026-10-19

**Status**: Draft

**Input**: User description: "Move from render deployment to automatic deployment on Raspberry Pi 5 with docker and portainer (no edge, deployment as stack in local enviropment with pulling from github repo), on push to main -> CI builds docker images (for x64 and arm) -> pushes this images to github packages (so they can be used in docker compose to avoid building on dployment server) -> then triggers portainer webhook to pull and redeploy stack. As you dont have access to deployment server and portainer write what i need to do in them so i can finish setup myself"

## Clarifications

### Session 2026-10-19

- Q: How should GitHub reach the Portainer webhook on a Pi in a local network? → A: Portainer is
  already reachable from the internet over HTTPS (a domain, port forwarding or a reverse proxy),
  and the pipeline calls the webhook directly.

### Session 2026-10-20

- Q: Which Portainer edition runs the stack? → A: Portainer Business Edition. Relative path
  volumes are available, so the stack may use other repository files by relative path.
- Q: Which CPU architectures must CI verify? → A: Both x86-64 and ARM64 run the full smoke test
  and the image build, and everything must be portable across the two.
- Q: Should the current int8 embedding model stay? → A: No. It was chosen only to fit Render's
  free tier. Replace it with the model that gives the best results for this project, runs on
  x86-64 and ARM64, and fits the Raspberry Pi 5 with good latency and performance.
- Q: Where is the embedding model defined? → A: In one place, a setting read from an
  environment variable with a default fallback, which every other part uses. The image build
  fetches the model through a separate script instead of inline commands.
- Q: How much memory can this site use in total on the Raspberry Pi 5? → A: Up to about 4 GB.
  The Pi has 8 GB of RAM, shared with a few other stacks.
- Q: When someone changes the model setting, which models should it accept? → A: One model at a
  time. The setting keeps the model's name in one place, and a change takes effect only when the
  images are rebuilt with the new value.
- Q: After a redeploy with a different embedding model, what should happen to the book vectors
  already stored? → A: They are rebuilt automatically on startup, before the site serves traffic.
  Storage adapts to the new vector size, and every book whose vector is missing or from another
  model is re-encoded.
- Q: Which embedding model should replace the current one? → A: `BAAI/bge-m3` (MIT license),
  dense vectors only, run from its int8 ONNX export: file `onnx/model_int8.onnx` in `Xenova/bge-m3`
  at revision `4de13258303883538bd53b696b452bf8099f0858`. Its weights are quantized per channel to
  signed int8 with reduced range, which works on any CPU family. The user chose this model,
  replacing an earlier pick of `ibm-granite/granite-embedding-311m-multilingual-r2`.
- Q: How does CI run the ARM64 build and smoke test? → A: On native ARM64 runners, without CPU
  emulation.
- Q: How are the Compose files laid out? → A: `docker-compose.yml` is the server stack that
  Portainer deploys, and `docker-compose-dev.yml` is for local development.
- Q: Which Compose file should the CI smoke test start on each architecture? → A:
  `docker-compose-dev.yml`, as today, and `docker-compose.yml` gets only a validity check. Lint
  and the smoke test run on pushes to `main`, version tags and pull requests to `main`. The image
  build, push and deployment run only after both pass, and only on pushes to `main` and version
  tags.
- Q: When several merges into `main` overlap, how should CI decide whether a finished build may
  move the `main` image tag that the Pi follows? → A: Only forward in history. A build moves the
  tag only if the commit currently under the tag is an ancestor of the build's commit. A newer
  commit whose pipeline fails doesn't block the last good build, and an older build that finishes
  late is skipped.
- Q: Which CI runs should be able to read the Portainer webhook URL? → A: Only the deploy job.
  The URL is a secret of a GitHub Environment (`production`) whose deployment rules allow only the
  `main` branch and `v*` tags, so pull-request runs can't read it.
- Q: Should the Pi be able to roll back to an image built before this feature, and how does
  search recover? → A: Yes, with one manual step. After pinning the older image, the operator
  runs the backfill command in the web container to re-encode the vectors with the old model.
  Rolling forward again re-encodes automatically on startup.
- Q: After CI calls the webhook, should the pipeline also check that the Pi actually started
  serving the new version? → A: Yes, when a public site address is configured. CI waits up to
  15 minutes for the site to report the new commit, or a newer one, and fails the run if it
  doesn't. Without an address, the check is skipped with a notice.
- Q: If measurements on the Pi show that `bge-m3` misses the speed or memory targets even after
  tuning, what should happen? → A: Keep `bge-m3`. First reduce web workers or threads within the
  4 GB budget. If latency still misses, record the measured values and relax SC-010 or SC-011 to
  them, with the user's sign-off.

## User Scenarios & Testing *(mandatory)*

**Actors**

- **Maintainer**: merges changes into `main` and watches the pipeline result.
- **Operator**: owns the Raspberry Pi 5 and its Portainer instance, does the one-time setup and
  any rollback. The delivery team has no access to the server, Portainer or the GitHub repository
  settings, so every step there is done by the operator from a written guide.
- **Visitor / librarian**: uses the deployed library site.

### User Story 1 - Run the site on the Raspberry Pi from pre-built images (Priority: P1)

The operator follows a guide in the repository to create a Portainer stack on the Raspberry Pi
that reads its stack definition from this GitHub repository. The stack pulls ready-made
application images for 64-bit ARM from the GitHub container registry, so nothing is built on
the Pi. With the operator's own secrets entered in Portainer, the full site (web, background
worker, database, message broker) runs on the Pi and survives restarts.

**Why this priority**: This is the minimum that replaces Render as the hosting target. Without a
working stack on the Pi, automatic redeploys have nothing to update.

**Independent Test**: Starting from a Pi that has Docker and Portainer Business Edition, follow
the guide to create the stack and deploy it once by hand from Portainer. Confirm that the site
answers, that images were pulled rather than built, and that data survives a stack restart and
a host reboot.

**Acceptance Scenarios**:

1. **Given** a Raspberry Pi 5 with a 64-bit OS, Docker and Portainer BE, **When** the operator
   creates the stack from the GitHub repository as the guide describes and deploys it, **Then**
   all services start from published images, with no image built on the Pi, and the site answers
   on the configured port.
2. **Given** the stack definition from the repository, **When** the operator deploys it without
   entering the required secrets, **Then** the deployment refuses to start and names the missing
   values.
3. **Given** a running stack with library data, **When** the stack is redeployed or the Pi
   reboots, **Then** all services come back on their own and the data, including queued activity
   events, is still there.
4. **Given** the same published image reference, **When** it is pulled on an x86-64 machine and
   on the Pi, **Then** each machine gets the variant for its own architecture.

---

### User Story 2 - Merges to main go live automatically (Priority: P2)

When a change is merged into `main` and passes the existing lint and test gates, the pipeline
publishes new images for x86-64 and ARM64. It then calls the Portainer stack webhook, and the Pi
pulls the new images and redeploys. Nobody logs into the server.

**Why this priority**: This is the automation the request asks for, and it replaces Render's
deploy-on-push. It builds on Story 1's stack.

**Independent Test**: With Story 1 in place and the webhook stored in the `production` environment,
merge a visible change, such as page text, into `main`. Without touching the Pi or Portainer,
confirm that the live site shows the change and that the pipeline run reports the redeploy as
triggered.

**Acceptance Scenarios**:

1. **Given** the stack is running and the webhook secret is configured, **When** a change merged
   into `main` passes all required checks, **Then** images for both architectures are published
   under the same references and the webhook is called only after both variants are available.
   The Pi then runs the new version.
2. **Given** a merge whose lint or tests fail on either architecture, **When** the pipeline runs,
   **Then** no image is
   published, no redeploy is triggered, and the Pi keeps the previous version.
3. **Given** a pull request to `main`, **When** its pipeline runs, **Then** lint and the smoke
   test run on both architectures, but no image is published and the Pi is not redeployed.
4. **Given** a version tag is pushed, **When** lint and the smoke test pass on both
   architectures, **Then** images are published under that version and the redeploy is triggered.
   The Pi keeps following the reference it is set to, the newest `main` build unless pinned.
5. **Given** a push to any branch other than `main`, without a pull request to `main`, **Then**
   no pipeline runs.
6. **Given** two merges into `main` close together, **When** both pipelines finish, **Then** the
   moving image reference and the running site both end up on the newer commit.

---

### User Story 3 - See deployment failures and recover (Priority: P3)

The maintainer can tell from the pipeline run whether the server was redeployed. If a new version
is broken on the Pi, the operator can pin the stack to an earlier published version in Portainer,
with no repository change, and later return it to following `main`.

**Why this priority**: Automatic deployment without visible failures or a way back turns one bad
merge into downtime that needs hands-on debugging.

**Independent Test**: Remove or corrupt the webhook secret and merge a change, then confirm that
the run shows the problem. Then follow the guide's rollback steps to pin an earlier version,
confirm that the site runs it, and unpin.

**Acceptance Scenarios**:

1. **Given** the webhook cannot be reached or rejects the call, **When** the pipeline tries to
   trigger it, **Then** the run is marked failed with a message saying the images were published
   but the server was not redeployed. The webhook address itself is not printed.
2. **Given** no webhook secret is configured, **When** a `main` pipeline runs, **Then** images are
   still published and the run shows a visible warning that deployment was skipped.
3. **Given** a broken new version, **When** the operator sets the stack's version to an earlier
   published build and redeploys, as the guide describes, **Then** the site runs that build until
   the operator returns the stack to the latest `main` version.
4. **Given** a redeploy whose new web service never becomes healthy, **When** the operator opens
   the stack in Portainer, **Then** the web service shows as unhealthy, not running.

---

### User Story 4 - Retire the Render deployment (Priority: P3)

Once the Pi deployment is confirmed, everything Render-specific is removed from the repository:
the Blueprint, the Render start-up launcher, Render-only CI checks and settings that trust Render
hosts. The project documentation and governing principles describe the Pi as the deployment
target. The guide tells the operator how to shut down the Render services safely.

**Why this priority**: The project should not carry rules and checks for a platform it no longer
uses. This comes last because Render stays as the fallback until the Pi is proven.

**Independent Test**: Search the repository for Render-specific deployment configuration and
checks and find none. The README and project principles describe the Pi deployment, and CI passes
without Render checks.

**Acceptance Scenarios**:

1. **Given** the feature is merged, **When** a reader looks for how the project is deployed,
   **Then** the README and guide describe the Raspberry Pi and Portainer setup, and nothing
   describes Render as a current target.
2. **Given** the feature is merged, **When** CI runs, **Then** no Render-only check remains, and
   the existing lint, test, endpoint, tracking and recovery checks still run.
3. **Given** the operator has verified the Pi deployment, **When** they follow the guide's Render
   decommissioning steps, **Then** the Render services stop deploying from `main`.

---

### User Story 5 - Better search from a portable, configurable model (Priority: P2)

Visitors who search in English or Ukrainian get more relevant results. The int8 model that was
picked to fit Render's free tier is replaced by a model chosen for this catalog, which runs on
both x86-64 and ARM64 and stays fast on the Pi. The model is named in one setting, and every part
of the system follows that setting.

**Why this priority**: Without Render's limits, search quality is the cheapest visible
improvement. The current model file is also tuned for x86 CPUs, which conflicts with running the
same images on the Pi.

**Independent Test**: Run the evaluation queries against the seed catalog with the current model
and with the new one, and confirm that SC-013 holds on both architectures. Measure search latency
and memory on the Pi. Then confirm that no build file or code outside the single setting names
the model.

**Acceptance Scenarios**:

1. **Given** the seed catalog, **When** the evaluation queries run in English and Ukrainian,
   including cross-language ones, **Then** the expected books rank as SC-013 requires on x86-64
   and on ARM64.
2. **Given** the model setting is not set, **When** the image is built and the site runs,
   **Then** the default model is used everywhere: at build time, at runtime, on stored vectors and
   in search.
3. **Given** the image recipe, **When** a reviewer reads it, **Then** it calls the model-fetch
   script and names no model.

---

### Edge Cases

- **Webhook unreachable or failing**, including a public address that is down or a TLS
  certificate that is expired or not trusted: images stay published, the Pi keeps the previous
  version, the run fails visibly, and the operator can redeploy by hand from Portainer.
- **Webhook secret missing** (before setup, or in a fork): publishing continues and deployment is
  skipped with a warning, not a failure.
- **Redeploy triggered but not confirmed**, for example because the image pull failed, the new
  version is unhealthy, or the stack is pinned to an older version: when the site address is
  configured, the run fails after 15 minutes (FR-036). During a long, deliberate pin the operator
  can remove the address to stop these failures.
- **Trigger before every architecture is published**: must not happen. The webhook is called only
  after the x86-64 and ARM64 variants are available under the same reference.
- **Overlapping merges**: an older pipeline that finishes after a newer one must not move the
  "latest `main`" reference back. A newer commit whose pipeline fails doesn't stop the last
  successful build from being published and deployed (FR-002, FR-019).
- **Version tag on an older commit**: the build publishes that version's reference only. The
  "latest `main`" reference does not move back, and the redeploy it triggers leaves the Pi on the
  reference it follows.
- **Server-file mistake that passes the validity check**, such as a broken health check: CI
  smoke-tests only `docker-compose-dev.yml`, so the mistake surfaces on the Pi. The web service
  shows as unhealthy, and the operator rolls back by pinning (User Story 3).
- **Architecture-specific defects**: the full smoke test runs on both x86-64 and ARM64, so a
  defect on either architecture blocks publishing and deployment. Model files or dependencies
  tuned for one CPU family must not be used.
- **Model download fails during the image build**: the build fails and nothing is published.
  Images never ship without their model.
- **Runtime model setting differs from the image's model**, for example an operator overrides it
  in Portainer: startup fails with a clear error that names both models, instead of downloading a
  model or serving mismatched vectors.
- **A rebuilt model whose output does not match its configured details**, such as the vector
  size: the smoke test fails and the images are not published.
- **First startup after a model change**, including this feature's own replacement of the
  current model on an existing database: vectors are re-encoded before traffic is served
  (FR-034), so search never returns a partial catalog.
- **Re-encoding fails part-way**: the web service fails to start and shows as unhealthy. Books
  already re-encoded keep their new vectors, and the next start re-encodes only the rest.
- **Rollback to an image built before this feature** (possible only on an x86-64 host, because
  those images have no ARM64 variant; on the Pi the oldest target is the first image of this
  feature): that image can't re-encode on startup,
  so its search would ignore every vector made by the new model. The guide's rollback steps have
  the operator run the backfill command in the web container to restore search. Rolling forward
  again re-encodes automatically (FR-034).
- **New version fails to start**, for example on a migration error: the web service reports
  unhealthy and the operator rolls back by pinning. Migrations that the failed version already
  applied are not reverted automatically, and the guide says so.
- **Registry unavailable during redeploy**: the image pull fails before containers are replaced,
  so the previous version keeps serving.
- **Pi power loss or reboot**: services restart on their own, and database and broker data
  persist.
- **Repeated seeding**: redeploys reuse the existing database, so demo seeding must not duplicate
  data. It already does nothing when users exist.
- **No new commit**: a Portainer webhook skips the redeploy unless forced redeployment is on, so
  the guide must have the operator enable it.

## Requirements *(mandatory)*

### Functional Requirements

**Image publishing**

- **FR-001**: On every push to `main` or version tag that passes the required checks (lint, and
  the smoke test on both architectures), the pipeline MUST publish the application image for x86-64 (`amd64`) and
  64-bit ARM (`arm64`) under one multi-architecture reference, so the same reference resolves to
  the right variant on each machine.
- **FR-002**: Each successful build MUST be available under an immutable reference derived from
  its commit, and a version-tag build also under its version. One moving reference MUST always
  point to the newest successful `main` build, and it MUST only move forward in `main`'s history.
  A build may move it only if the commit currently under it is an ancestor of the build's commit.
  A version-tag build MUST NOT move it.
- **FR-003**: The publishing image build, the push to the registry and the deployment trigger
  MUST run only after lint and the smoke test pass on both architectures, and only for pushes to
  `main` and version tags. Pull requests MUST NOT publish images or trigger deployment. The
  publishing build MUST also run on native runners for each architecture.
- **FR-004**: Lint and the full smoke test MUST run on pushes to `main`, on version tags and on
  pull requests to `main`. Pushes to other branches start no pipeline. The smoke test MUST run on
  native x86-64 and native ARM64 runners, without CPU emulation, using `docker-compose-dev.yml`.
  It covers the Compose build, the Django test suite with real-model tests, the endpoint checks,
  asynchronous tracking and broker and worker recovery.
- **FR-005**: Published images MUST NOT contain secrets or default secret values, as already
  required, and MUST still refuse to start without a secret key supplied at runtime.

**Server stack**

- **FR-006**: `docker-compose.yml` at the repository root MUST be the server stack definition. It
  runs the web app, background worker, database and message broker from published or upstream
  images only, with no build step and no source-code mounts. Local development moves to
  `docker-compose-dev.yml` (FR-025).
- **FR-007**: Portainer Business Edition MUST be able to deploy the stack definition as a Git
  repository stack on the Portainer host's local Docker environment (no Edge agent). The stack may
  reference other repository files by relative path, using Portainer BE's relative path volumes,
  but application code always comes from the published images.
- **FR-008**: All secrets and environment-specific settings MUST be supplied through the stack's
  environment variables in Portainer. These are the secret key, database password, allowed
  hostnames, published port, demo seeding and image version. They also include optional settings:
  trusting the proxy's HTTPS header, trusted origins, web worker count, inference threads, and
  the image repository for forks. The definition MUST refuse to start when a required secret is
  missing.
- **FR-009**: Database and message broker data MUST persist across redeploys, image updates and
  host reboots.
- **FR-010**: Every service MUST restart automatically after a crash or a host reboot.
- **FR-011**: The operator MUST be able to choose which published version runs. The default is
  the newest `main` build. Pinning and unpinning MUST need only Portainer configuration, with no
  repository change.
- **FR-012**: The web service MUST report itself healthy only once it serves requests, so a
  failed redeploy is visible in Portainer.
- **FR-013**: Demo seeding MUST be off by default on the server stack and enabled only by the
  operator, because the seeded accounts, including a librarian, have publicly documented
  passwords.
- **FR-014**: Through configuration alone, the site MUST work both when served directly on the
  local network over HTTP and behind an operator-provided HTTPS reverse proxy or tunnel. Behind
  a proxy it must treat forwarded HTTPS requests as secure and accept the configured hostnames.
  This replaces the current Render-only proxy handling.

**Deployment trigger**

- **FR-015**: After every architecture variant of a `main` or version-tag build is published
  (which happens only once FR-004 passes), the pipeline MUST call the Portainer stack webhook so
  that the server pulls the new images and redeploys.
- **FR-016**: The webhook address MUST be stored only as a secret of a GitHub Environment
  (`production`) whose deployment rules allow only the `main` branch and `v*` tags. Only the
  deploy job may use that environment, so pull-request runs can't read the address. It MUST NOT
  be committed or shown in logs, because anyone holding it can trigger a redeploy.
- **FR-017**: If the webhook secret is not configured, the pipeline MUST skip the trigger with a
  visible warning and MUST still publish the images.
- **FR-018**: If the webhook call fails because it is unreachable, times out or returns a
  non-success response, the run MUST be marked failed. The message MUST say that images were
  published but the server was not redeployed.
- **FR-019**: When `main` pipelines overlap, or a newer commit's pipeline fails, the moving
  reference and the server MUST end up on the newest commit whose pipeline succeeded. A build that
  is not allowed to move the reference (FR-002) MUST NOT trigger a redeploy; its run shows a
  notice instead.
- **FR-035**: The site MUST report the commit its image was built from through an anonymous,
  read-only response that contains nothing else sensitive.
- **FR-036**: If the `production` environment defines the site's public address, the pipeline
  MUST check after a successful webhook call that the redeploy happened. It waits up to 15
  minutes for the site to report this run's commit or a newer commit on `main`. If that doesn't
  happen, the run MUST fail with a message saying the redeploy was triggered but not confirmed,
  and that the server may be pinned or unhealthy. If no address is defined, the check MUST be
  skipped with a visible notice.
- **FR-020**: The pipeline MUST call the webhook directly at the operator's existing public HTTPS
  address for Portainer (a domain, port forwarding or a reverse proxy). The call MUST verify the
  server's TLS certificate and MUST NOT skip that check, so the public address needs a publicly
  trusted certificate. No tunnel or self-hosted runner is introduced.

**Operator guide**

- **FR-021**: The repository MUST include a step-by-step operator guide that covers:
  prerequisites (Raspberry Pi 5 with a 64-bit OS, Docker, Portainer BE); creating the Git
  repository stack (repository URL, branch, stack definition path `docker-compose.yml`, and
  relative path volumes with
  their local filesystem path, if the stack uses them); every required and optional
  environment value and how to generate the secrets; enabling GitOps updates with the webhook
  mechanism, "Re-pull image" and "Force redeployment"; creating the `production` GitHub
  Environment, restricted to `main` and `v*` tags, and saving the webhook URL as its secret and
  the optional public site address as its variable, including who needs which repository
  permission; checking from outside
  the local network that the webhook answers over HTTPS with a trusted certificate, and the
  recommendation to expose only the stack webhook path publicly while keeping the Portainer login
  page off the internet; a first-deployment verification checklist; pinning, rollback
  and unpinning, including the backfill step after rolling back to an image built before this
  feature; viewing logs; backing up and restoring the database; and decommissioning the
  Render services after the Pi is verified.
- **FR-022**: The guide MUST separate the steps the repository change already provides from the
  steps the operator performs on the Pi, in Portainer, in GitHub settings and in Render.

**Render retirement**

- **FR-023**: The Render Blueprint, the Render web/worker launcher, Render-only CI checks and their
  tests, and Render-specific application settings (always-allowed Render hostnames, the
  Render-only proxy header) MUST be removed or replaced with platform-neutral configuration.
- **FR-024**: In the same change, the README, the environment template, the changelog and the
  project's governing principles MUST be updated to describe the Raspberry Pi deployment in place
  of Render.
- **FR-025**: Local development MUST use `docker-compose-dev.yml` and keep working as today on
  x86-64 and ARM64 machines, with local builds and source mounts for live reload. The README and
  other documentation MUST show the new file name in their commands, and the CI smoke test MUST
  keep using this file. The same pipeline MUST run a configuration validity check on the server's
  `docker-compose.yml`.

**Portability and embedding model**

- **FR-026**: Images, scripts, model files and the stack definition MUST contain nothing specific
  to one CPU architecture. The same stack definition MUST run unchanged on an x86-64 host and on
  an ARM64 host. Model files tuned for one CPU family MUST NOT be used, such as quantized files
  built for one instruction set (AVX2, AVX-512 VNNI).
- **FR-027**: The Render-constrained int8 model MUST be replaced by `BAAI/bge-m3` dense
  embeddings (1024 dimensions). These are run from the pinned int8 ONNX export of that model in
  the `Xenova/bge-m3` repository, file `onnx/model_int8.onnx`. `BAAI/bge-m3` names the model; the
  model setting and the stored vector tag name the repository the file comes from. The model
  MUST run on CPU on x86-64 and ARM64 and meet the Raspberry Pi 5 targets in SC-010 to SC-012.
  Portable tuning, such as the number of inference threads and model copies per container, may
  be used to get there. If the targets are still missed:
  - memory (SC-012) is met by reducing web workers or threads;
  - if latency then misses SC-010 or SC-011, `bge-m3` stays, and the target is relaxed to the
    measured value with the user's sign-off and recorded in the plan's research.
- **FR-028**: The plan MUST record how `bge-m3` int8 compares with the current model on the
  evaluation set, and its latency and memory on a development machine. Latency and memory on
  the Raspberry Pi 5 MUST be measured with the stack budget check during the first deployment,
  and recorded together with the inference thread count and worker count used. The feature is
  complete only when those measurements meet SC-010 to SC-012, or the targets have been relaxed
  under FR-027.
- **FR-029**: The chosen model's license MUST allow redistributing its weights inside the public
  images, and the model's revision MUST be pinned.
- **FR-030**: The project MUST support one embedding model at a time. Its identity (name and
  pinned revision) MUST be defined in exactly one place: a build-time setting read from an
  environment variable, with a default fallback. The model-specific details the code needs, such
  as vector size and text preparation, MUST be defined alongside it. The image build, model
  loading at runtime, the model tag stored with each vector, search compatibility checks, the
  backfill command, CI and the tests MUST all take the model from that setting. No other code or
  build file may hard-code it.
- **FR-033**: Images MUST ship with the model named by the setting at build time, and running
  containers MUST use the model in their image without downloading one at runtime. Changing the
  model means rebuilding the images with a new value.
- **FR-034**: On startup, before the site serves traffic, stored vectors MUST be brought in line
  with the image's model, the same way database migrations are applied today. Vector storage MUST
  adapt to the model's vector size, and every book whose vector is missing or was made by another
  model MUST be re-encoded. Books that already match MUST be left alone, so a startup without a
  model change adds no noticeable time. Only the web service does this; the background worker
  never does.
- **FR-031**: The image build MUST fetch the configured model through a dedicated script that
  reads the same setting, not through inline commands in the image recipe. The same script MUST
  also work outside the image build, for example to pre-fetch the model for local development.
- **FR-032**: Search quality MUST be checked against a fixed evaluation set: English and Ukrainian
  queries, including cross-language ones, each with its expected books from the seed catalog. CI
  MUST run the set with the real model on both architectures.

### Key Entities

- **Published image version**: one `main` or version-tag build of the application, in x86-64
  and ARM64 variants. It is identified by an immutable commit reference, and also by its version
  if it is a tag build. A `main` build is also identified by the moving "latest `main`" reference
  while it is the newest successful one.
- **Server stack**: the set of services on the Pi, defined in the repository, configured with the
  operator's environment values and set to follow either the latest version or a pinned one.
- **Deployment webhook**: a secret, stack-specific URL issued by Portainer. Calling it makes
  Portainer fetch the stack definition, re-pull the images and redeploy.
- **Operator configuration**: secrets and environment-specific settings kept only in Portainer,
  never in the repository or the images.
- **Embedding model setting**: the single, build-time definition of which model, at which pinned
  revision, encodes books and queries, together with that model's vector size and
  text-preparation details. Each image ships with exactly that model. Every stored book vector is
  tagged with the model that produced it, and search uses only vectors that match the image's
  model.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A change merged into `main` that passes the checks is live on the Pi within 30
  minutes of the merge, with no manual action.
- **SC-002**: No redeploy builds an image on the Pi; every update uses published images.
- **SC-003**: An operator who knows Docker and Portainer but not this project completes
  first-time setup from the guide in under 60 minutes without reading application code.
- **SC-004**: After three automatic redeploys and one host reboot, every record created before
  them is intact and every activity event queued before them is processed.
- **SC-005**: The operator can roll back to an earlier published version in under 5 minutes,
  following the guide, with no repository change.
- **SC-006**: Every failed or skipped deployment trigger shows on its pipeline run. When the site
  address is configured, so does every redeploy that isn't confirmed within 15 minutes. None are
  silent.
- **SC-007**: The site on the Pi behaves as it did on Render. The home page, API docs, API schema
  and semantic search all answer, and search returns results for the standard smoke-test query.
- **SC-008**: No secret value or webhook address appears in the repository, the published images
  or the pipeline logs.
- **SC-009**: During a routine automatic redeploy that does not change the embedding model, the
  site is unavailable for less than 2 minutes.
- **SC-010**: On the Raspberry Pi 5, 95% of semantic searches return results in under 500 ms on
  a catalog of up to 1,000 books.
- **SC-011**: On the Raspberry Pi 5, saving a book, including generating its embedding, takes
  under 2 seconds.
- **SC-012**: On the Raspberry Pi 5, the whole stack (web, background worker, database and
  broker) uses no more than 4 GB of memory in total. This includes peak load, with searches and
  book saves running in every web worker.
- **SC-013**: On the evaluation set, the new model ranks the expected book first for at least as
  many queries as the current model does, and every expected book appears in the top 3.
- **SC-014**: After a redeploy that changes the embedding model, the site on the Raspberry Pi 5
  is back with complete search results within 10 minutes for a catalog of up to 1,000 books.

## Assumptions

- The Raspberry Pi 5 runs a 64-bit OS and has 8 GB of RAM, shared with a few other stacks. This
  site's budget is about 4 GB (SC-012). 32-bit ARM images are out of scope.
- The operator runs Docker Engine and Portainer Business Edition. Portainer manages the Pi's own
  Docker as its local environment, with no Edge agent.
- Search must serve English and Ukrainian, including cross-language queries, as the seed catalog
  and the current real-model tests already do.
- `bge-m3` uses the same XLM-R tokenizer vocabulary as the current model, so tokenization does
  not change. It needs no `query:`/`passage:` prefixes, and only its dense output is used. The
  int8 file is a community ONNX export, pinned by revision. Its int8 arithmetic may give slightly
  different scores on x86-64 and ARM64, so the evaluation set (FR-032) must pass on both.
- No public benchmark is specific to Ukrainian retrieval, so the project's evaluation set
  (FR-032) is the deciding quality check.
- GitHub-hosted native ARM64 runners are available to this public repository at no cost.
- The catalog stays demo-sized, up to about 1,000 books.
- Portainer is already reachable from the internet over HTTPS at an address the operator
  controls. Providing and securing that address, including its certificate and which paths are
  exposed, is the operator's job. The guide gives the recommended exposure (FR-021).
- The repository is public, so Portainer reads the stack definition without Git credentials, and
  the existing container package can already be pulled anonymously. If either becomes private,
  the guide notes which credentials to add.
- The Pi starts with a fresh database, and no data moves from Render. The Render site is a
  seeded demo on a disposable free-tier database.
- Exposing the site to the internet (domain, TLS certificate, reverse proxy, router or firewall
  rules) is the operator's job. The application only needs to support it through configuration
  (FR-014).
- Someone with admin rights on the GitHub repository creates the `production` environment and
  adds the webhook secret to it. The guide names this step explicitly, because the operator may
  not be the repository owner.
- Lint, and the full smoke test on both x86-64 and ARM64, are the gate for publishing.
- Cleaning up old images in the registry and on the Pi is out of scope. The guide may mention
  pruning.
- Constitution v1.0.0 required the Render deployment, and named the `multilingual-e5-small`
  model and 384-dimension vectors. It was amended to v2.0.0 on 2026-10-20 to describe the
  Raspberry Pi deployment, multi-architecture images and the single model setting, so this
  feature no longer conflicts with it. The amendment ships in this feature's pull request.
- Render remains the live fallback until the operator confirms the Pi deployment. Only then are
  the Render services shut down.
