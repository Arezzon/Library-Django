# Deploying to a Raspberry Pi 5 with Portainer

This guide sets up the library site on a Raspberry Pi 5 that runs Docker and Portainer
Business Edition (BE). Portainer deploys the site as a Git repository stack from this
repository, and every merge into `main` redeploys it automatically.

It is written for an operator who knows Docker and Portainer but not this project. You don't
need to read any application code.

## Who does what

| Already done in this repository | You do this |
|---|---|
| `docker-compose.yml`: the server stack (web, worker, PostgreSQL, Redis), using published images only | **On the Pi**: install a 64-bit OS, Docker Engine and Portainer BE |
| Multi-architecture images (`linux/amd64`, `linux/arm64`) published to `ghcr.io/arezzon/library-django` on every merge into `main` and every `v*` tag | **In Portainer**: create the stack from the repository, set its environment variables, turn on the webhook |
| CI runs lint and the full smoke test on amd64 and arm64 before anything is published | **In Portainer / your network**: make the stack webhook reachable over HTTPS with a trusted certificate |
| CI calls the Portainer webhook after both architectures are published, and checks that the site reports the new commit | **In GitHub** (repository admin): create the `production` environment, its secret `PORTAINER_WEBHOOK_URL` and optional variable `SITE_URL` |
| The image ships with its embedding model and re-encodes stored vectors on startup when the model changes | **In Render**: shut the old services down once the Pi is verified |

## Contents

- [Prerequisites](#prerequisites)
- [Create the stack](#create-the-stack)
- [Environment variables](#environment-variables)
- [Create the first librarian account](#create-the-first-librarian-account)
- [First deployment checklist](#first-deployment-checklist)
- [Viewing logs](#viewing-logs)
- [Backup and restore](#backup-and-restore)
- [Turn on automatic updates](#turn-on-automatic-updates)
- [Make the webhook reachable](#make-the-webhook-reachable)
- [Create the production GitHub environment](#create-the-production-github-environment)
- [Rotate the webhook](#rotate-the-webhook)
- [Measure the stack on the Pi](#measure-the-stack-on-the-pi)
- [Confirm deployments](#confirm-deployments)
- [What the pipeline messages mean](#what-the-pipeline-messages-mean)
- [Pin, roll back and unpin](#pin-roll-back-and-unpin)
- [Rolling back past the Raspberry Pi feature](#rolling-back-past-the-raspberry-pi-feature)
- [Shut down Render (after the Pi is verified)](#shut-down-render-after-the-pi-is-verified)

## Prerequisites

- A **Raspberry Pi 5 with 8 GB of RAM** running a **64-bit** OS (Raspberry Pi OS 64-bit or
  Ubuntu Server arm64). 32-bit systems can't run the images. Check with `uname -m`: it must
  print `aarch64`.
- **Docker Engine** 25 or newer (`docker version`), with the Compose plugin.
- **Portainer Business Edition** managing the Pi's own Docker as its **local** environment.
  No Edge agent is needed.
- About **4 GB of free memory** for this stack, and about 5 GB of disk for the images and data.
  The web service keeps one copy of the search model (about 0.6 GB) in each Gunicorn worker.
- Outbound internet access from the Pi to `github.com` and `ghcr.io`. The repository and the
  image are public, so Portainer needs no credentials. If either becomes private, add Git
  credentials to the stack and a `ghcr.io` registry with a read-only token in Portainer.

## Create the stack

1. In Portainer, open the Pi's local environment, then **Stacks → Add stack**.
2. Name the stack, for example `library`.
3. Under **Build method**, choose **Repository** and fill in:

   | Field | Value |
   |---|---|
   | Repository URL | `https://github.com/Arezzon/Library-Django` |
   | Repository reference | `refs/heads/main` |
   | Compose path | `docker-compose.yml` |
   | Authentication | Off (the repository is public) |

   Leave **Relative path volumes** off: the stack is self-contained and uses named volumes
   only.
4. Add the environment variables from the next section. At least `SECRET_KEY` and
   `DB_PASSWORD` are required.
5. Leave **GitOps updates** off for now. You turn it on after the first deployment works
   (see the automatic updates section).
6. Click **Deploy the stack**. Portainer pulls the images; nothing is built on the Pi.

Without `SECRET_KEY` or `DB_PASSWORD`, the deployment stops with an error naming the missing
variable, for example `Set SECRET_KEY in the Portainer stack environment`.

## Environment variables

Set these in the stack's **Environment variables** section. Values stay in Portainer; they are
never committed to the repository or baked into the images.

| Variable | Required | Default | What it does |
|---|---|---|---|
| `SECRET_KEY` | **yes** | none | Django's signing key. Generate one (see below) and keep it secret. |
| `DB_PASSWORD` | **yes** | none | PostgreSQL password. See the warning below. |
| `ALLOWED_HOSTS` | no | `localhost,127.0.0.1` | Comma list of the hostnames the site answers to, for example `library.example.com,192.168.1.50`. `localhost` and `127.0.0.1` are always allowed for the health check. |
| `CSRF_TRUSTED_ORIGINS` | no | empty | Comma list of public origins that submit forms, for example `https://library.example.com`. Needed behind a proxy that serves HTTPS. |
| `TRUST_X_FORWARDED_PROTO` | no | `False` | Set `True` only when the site is behind your own HTTPS reverse proxy or tunnel that sets `X-Forwarded-Proto`. Leave it `False` when clients reach the Pi directly. When `True`, sign-in and form cookies are sent over HTTPS only, so sign in through the HTTPS address, not `http://<pi address>`. Any case works, as do `1`/`0`, `yes`/`no` and `on`/`off`; any other value stops the app at startup with an error naming this setting. |
| `WEB_PORT` | no | `8000` | Host port the site listens on. |
| `IMAGE_TAG` | no | `main` | `main` follows the newest build. Set `sha-<short commit>` or a version such as `1.2.3` to pin one. |
| `IMAGE_REPOSITORY` | no | `ghcr.io/arezzon/library-django` | Only for forks that publish their own images. |
| `DJANGO_SEED` | no | `false` | `true` loads demo data. See the warning below. |
| `DEBUG` | no | `False` | Must stay `False` on the server. |
| `DB_NAME` / `DB_USER` | no | `library_db` / `postgres` | Database name and user. |
| `WEB_CONCURRENCY` | no | `3` | Gunicorn web workers. Each holds one model copy of about 0.6 GB. |
| `BOOK_EMBEDDING_THREADS` | no | `2` | Inference threads per web worker. |

Generate `SECRET_KEY` and `DB_PASSWORD` on any machine with Python:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

> **Warning: `DB_PASSWORD` is fixed when the database volume is first created.** Changing the
> variable later does not change the password inside the existing database; the site would
> fail to connect. To change it, change it in PostgreSQL first, or remove the `pgdata` volume
> (which deletes all data).

> **Warning: `DJANGO_SEED=true` creates demo accounts whose passwords are published in the
> README**, including a librarian account. Use it only for a demo, and never on a site that
> holds real data. Seeding does nothing once users exist, so redeploys don't duplicate data.
> **Before the site is reachable from the internet**, change or delete those accounts'
> passwords. For each seeded email, run
> `docker exec -it library-web-1 python manage.py changepassword <email>`
> (replace `library` with your stack name).

Don't set any `BOOK_EMBEDDING_MODEL*` variable here: the search model ships inside the image,
and the stack doesn't pass these variables to the containers, so they have no effect. Choosing
another model means building new images. (If a different model setting does reach the web
container, for example through an edited Compose file, it refuses to start with the
`book.E001` error instead of mixing vectors.)

## Create the first librarian account

With `DJANGO_SEED` off (the default), the database starts with no users, so nobody can sign
in yet. Once `web` is running, create the first account; it becomes a librarian and a Django
admin. In Portainer, open the `web` container, then **Console → Connect** (with `/bin/sh`), or
on the Pi run:

```bash
docker exec -it library-web-1 python manage.py createsuperuser
```

Replace `library` with your stack name. It asks for an email, first, last and middle name (enter
`-` if there is none) and a password. Sign in at `/authentication/login/` with that email. Other
users can register on the site; the librarian manages them and the catalog, and `/admin/`
offers the Django admin.

## First deployment checklist

After **Deploy the stack**, check each item. The first start can take a few minutes while the
images download and the search vectors are built.

1. **Four containers run**: `db`, `redis`, `web` and `worker` show as running in Portainer, and
   `web` shows as **healthy**. (`web` turns healthy once it serves requests.)
2. **The images were pulled for ARM64, not built**:

   ```bash
   docker image inspect ghcr.io/arezzon/library-django:main --format '{{.Architecture}}'
   ```

   It prints `arm64`.
3. **The site answers** at `http://<pi address>:<WEB_PORT>/`:
   - the home page `/` loads (anonymous visitors are sent to the sign-in page);
   - the API documentation `/api/docs/` loads;
   - a search works, for example
     `http://<pi address>:8000/api/v1/books/search/?q=detective` returns a JSON list (it is empty
     until books exist; with `DJANGO_SEED=true` it returns the demo books).
4. **The running version** is reported at `/api/v1/version/`, for example
   `{"commit": "4f2c…"}`.
5. **Data survives restarts**: signed in as the librarian, create a book, then redeploy the stack and reboot the Pi. The book
   is still there and all four containers come back on their own.
6. **Portainer behaves as this setup expects.** Check this once automatic updates are on
   ([Turn on automatic updates](#turn-on-automatic-updates)), and again after upgrading
   Portainer:
   - the webhook accepts a `POST`: `curl -fsS -o /dev/null -w '%{http_code}
' -X POST <webhook URL>`
     prints `204`, and the stack redeploys;
   - with **Force redeployment** on, that call redeploys even though no new commit exists;
   - with **Re-pull image** on, a redeploy after a merge runs the new `main` image
     (`/api/v1/version/` reports the merged commit);
   - a failed pull keeps the old containers: set `IMAGE_TAG` to a tag that doesn't exist,
     redeploy, and check the site still answers; then remove `IMAGE_TAG` again.

## Viewing logs

- **In Portainer**: open the stack, then a container (for example `web`), then **Logs**. The
  `web` log shows startup in order: migrations, optional seeding, `Re-encoding stale book
  embeddings...` with a `Generated: N` line, then Gunicorn.
- **On the Pi**:

  ```bash
  docker ps --filter label=com.docker.compose.project=library     # container names
  docker logs --tail 200 -f library-web-1
  docker logs --tail 200 -f library-worker-1
  ```

  Replace `library` with your stack name.

## Backup and restore

The database lives in the `pgdata` volume and the event queue in `redisdata`. Both survive
redeploys and reboots. Back up the database regularly:

```bash
# Back up (run on the Pi; use your stack's db container name and DB_USER/DB_NAME).
docker exec library-db-1 pg_dump -U postgres library_db > library-$(date +%F).sql

# Restore into an empty database (for example after recreating the volume).
docker exec -i library-db-1 psql -U postgres -d library_db < library-2026-10-20.sql
```

After a restore, restart `web`: it re-encodes any book vectors that don't match its model.

## Turn on automatic updates

Do this once the first deployment works.

1. In Portainer, open the stack, then **Editor** (or **GitOps updates** in the stack details).
2. Turn **GitOps updates** on and set:

   | Setting | Value |
   |---|---|
   | Mechanism | **Webhook** |
   | Re-pull image | **On**, so each redeploy pulls the newest image for `IMAGE_TAG` |
   | Force redeployment | **On**, so a webhook redeploys even when the Git files did not change (only the image moved) |

3. Copy the **webhook URL** Portainer shows. It looks like
   `https://<portainer host>/api/stacks/webhooks/<id>`.
4. Click **Update the stack**.

Treat the webhook URL as a secret: anyone who has it can make the Pi redeploy. Don't paste it
into issues, chat or logs.

Why a webhook and not polling: CI calls the webhook only after the images for both
architectures are published. Portainer's Git polling would see the new commit before its images
exist and redeploy the old image.

## Make the webhook reachable

GitHub's runners call the webhook from the internet, so it has to be reachable over HTTPS with
a **publicly trusted certificate**. CI always verifies the certificate, so a self-signed one
fails the deployment.

- Expose **only** the path `/api/stacks/webhooks/` through your HTTPS reverse proxy or tunnel.
  Keep the Portainer login page and the rest of its API off the internet. For example, with
  Caddy:

  ```text
  portainer.example.com {
      @webhook path /api/stacks/webhooks/*
      handle @webhook {
          reverse_proxy https://127.0.0.1:9443 {
              transport http {
                  tls_insecure_skip_verify   # Portainer's local self-signed certificate only
              }
          }
      }
      respond 404
  }
  ```

  (The `tls_insecure_skip_verify` line covers only the hop from the proxy to Portainer on the
  Pi itself. The public side uses Caddy's trusted certificate.)
- Test from **outside** your network, for example from a phone hotspot:

  ```bash
  curl -sS -o /dev/null -w '%{http_code}\n' -X POST '<webhook url>'
  ```

  `204` (or another `2xx`) means it works, and Portainer redeploys the stack. A certificate
  error means the certificate isn't publicly trusted.

## Create the production GitHub environment

This needs **admin** rights on the GitHub repository. If you aren't an admin, send these steps
to one.

1. In the repository, open **Settings → Environments → New environment**, name it
   `production`, and click **Configure environment**.
2. Under **Deployment branches and tags**, choose **Selected branches and tags** and add the
   branch `main`. Version tags only publish images and never deploy, so no tag pattern is
   needed. If an older setup added the tag pattern `v*`, remove it.
3. Under **Environment secrets**, click **Add environment secret**: name
   `PORTAINER_WEBHOOK_URL`, value the webhook URL from Portainer.

Only the pipeline's `deploy` job uses this environment, so pull-request runs can never read the
secret. If the workflow runs before you create the environment, GitHub creates `production`
automatically **without** the branch rules; add them as above.

Until the secret exists, every merge still publishes images, and the run shows a warning that
deployment was skipped.

## Rotate the webhook

Rotate it whenever it may have leaked, or as routine:

1. In Portainer, open the stack's GitOps updates and regenerate the webhook. The old URL stops
   working immediately.
2. In GitHub, **Settings → Environments → production**, update `PORTAINER_WEBHOOK_URL` with the
   new URL.
3. Re-run the last pipeline's `deploy` job, or merge a change, to confirm it.

## Measure the stack on the Pi

Do this once after the first deployment, and again after changing `WEB_CONCURRENCY` or
`BOOK_EMBEDDING_THREADS`. The site's targets on the Pi are:

- the whole stack uses at most **4 GiB** of memory, even under load;
- 95% of searches answer in under **500 ms**;
- saving a book (including its embedding) takes under **2 s**.

The check needs Python 3 and Docker on the Pi; it only reads the running containers and adds
and deletes a few temporary books named `budget-check-…`.

1. Get the script. The repository is public, so a shallow clone is enough:

   ```bash
   git clone --depth 1 https://github.com/Arezzon/Library-Django.git
   cd Library-Django
   ```

2. Run it against your stack (use the stack name from Portainer and the site's port). The
   catalog should hold books, for example the demo data (`DJANGO_SEED=true`) or your own:

   ```bash
   python3 scripts/smoke_stack_budget.py --project-name library \
     --base-url http://localhost:8000 \
     --max-memory-gib 4 --max-search-p95-ms 500 --max-save-ms 2000
   ```

   It prints a JSON summary ending in `"result": "PASS"` or `"result": "FAIL: …"`.

3. If it fails, change one setting in the stack's environment variables, redeploy, and run it
   again:
   1. **Memory too high**: lower `WEB_CONCURRENCY` from `3` to `2`. Each worker holds one model
      copy of about 0.6 GB.
   2. **Searches or saves too slow**: raise `BOOK_EMBEDDING_THREADS` from `2` to `3`, then `4`.
      If that doesn't help, lower `WEB_CONCURRENCY` to free CPU cores.
   No rebuild is needed for either.

4. **Report the results**: send the JSON summary, with the values of `WEB_CONCURRENCY` and
   `BOOK_EMBEDDING_THREADS` you used, to the maintainers. They are recorded in
   `specs/001-rpi-portainer-deploy/research.md` (§R1), and the feature counts as complete only
   once the targets are met there, or relaxed to the measured values with the project owner's
   sign-off.

## Confirm deployments

Calling the webhook only proves Portainer accepted the request. To have CI check that the Pi
actually serves the new version, add the site's public address:

1. In GitHub, **Settings → Environments → production → Environment variables → Add
   variable**: name `SITE_URL`, value the site's public base URL, for example
   `https://library.example.com` (no trailing path).
2. After each webhook call, the `deploy` job polls `<SITE_URL>/api/v1/version/` every 15 seconds
   for up to 15 minutes. It passes when the site reports the run's commit or a newer commit on
   `main`, and fails otherwise.

Without `SITE_URL`, the check is skipped with a notice. The address is a variable, not a
secret, but the pipeline doesn't print it.

Portainer answers the webhook only after it has pulled the new images. The first deployment and
a model change pull large images, which can take longer than the pipeline's 5-minute limit.
With `SITE_URL` set, the `deploy` job then waits for the site instead of failing. Without it,
nothing can confirm the redeploy, so the job fails and asks you to check Portainer.

## What the pipeline messages mean

These appear on the `deploy` job of the **Docker Build** workflow run, and on the `promote` job
for the first one.

| Message | Meaning | What to do |
|---|---|---|
| *A newer commit already moved main; this build was published as sha-… only.* (notice, `promote`) | An older run finished after a newer one. Its image is published under `sha-…` but doesn't become `main`, and no redeploy runs. | Nothing. |
| *Version tags only publish images; the server was not redeployed. To run this version, set IMAGE_TAG=… in Portainer.* (notice, `promote`) | A version tag published `X.Y.Z` and `sha-…` images. Tags never redeploy; the Pi keeps following `main`. | Nothing, or pin the version (see [Pin, roll back and unpin](#pin-roll-back-and-unpin)). |
| *Images … published; server deployment skipped because PORTAINER_WEBHOOK_URL is not configured.* (warning) | The `production` environment has no webhook secret. Images were published. | Add the secret (see [Create the production GitHub environment](#create-the-production-github-environment)). |
| *Redeploy triggered for … (HTTP 204).* | Portainer accepted the webhook. | Nothing. |
| *Images … were published, but the server was not redeployed (HTTP … / curl exit …).* (error) | The webhook failed. HTTP 404 means a wrong or regenerated URL; `HTTP 000 / curl exit 6` or `7` means the address isn't reachable; `curl exit 60` means the certificate isn't publicly trusted; `curl exit 28` means the request didn't get through in time. | Fix the cause, then re-run the `deploy` job, or redeploy by hand in Portainer. |
| *Portainer did not answer within 300 s; it may still be pulling the images for …. Waiting for the site to confirm the redeploy.* (warning) | Portainer received the webhook but was still pulling images when the limit ran out. | Nothing if the job then confirms the redeploy. Otherwise follow the message that comes next. |
| *Portainer did not answer in time and SITE_URL is not configured, so the redeploy for … can't be confirmed. Check the stack in Portainer.* (error) | As above, but there's no `SITE_URL` to check the result. | In Portainer, check that the stack finished updating and `web` is healthy. Add `SITE_URL` to avoid this next time. |
| *Redeploy not confirmed: SITE_URL is not configured for the production environment.* (notice) | The redeploy was triggered, and confirmation is off. | Optional: add `SITE_URL` (see [Confirm deployments](#confirm-deployments)). |
| *Redeploy confirmed: the site runs ….* | The Pi serves this commit or a newer one. | Nothing. |
| *Redeploy for … was triggered but not confirmed: the site reports …. The stack may be pinned, unhealthy or still starting.* (error) | Within 15 minutes the site never reported this commit. It is pinned to another version, the new version failed to start, the image pull failed, or startup is still running (for example re-encoding after a model change). | Check the stack in Portainer: is `IMAGE_TAG` set, and is `web` healthy? Read the `web` logs. Re-run `deploy` once fixed. |

## Pin, roll back and unpin

Every successful build stays available under an immutable tag `sha-<first 7 characters of the
commit>`, and version tags `vX.Y.Z` also as `X.Y.Z`. To roll back:

1. Find the build to return to: the **Docker Build** run of that commit, or the repository's
   **Packages → library-django** page, lists its `sha-…` tag.
2. In Portainer, open the stack, set the environment variable `IMAGE_TAG=sha-<short commit>`
   (or a version such as `1.2.3`), and click **Update the stack** with **Re-pull image** on.
3. Check that `/api/v1/version/` reports that commit.

While the stack is pinned:

- merges still publish images, and the webhook still redeploys, but the Pi stays on the pinned
  build;
- if `SITE_URL` is set, each `deploy` confirmation **fails on purpose** with "may be pinned". To
  silence it during a long pin, remove `SITE_URL` from the environment and add it back later.

To unpin, **remove** `IMAGE_TAG` (or set it to `main`) and update the stack. The site returns to
the newest `main` build.

Database migrations that a newer version already applied are **not** reverted by a rollback.
Most are compatible with the previous version; if one isn't, restore the backup taken before
the upgrade (see [Backup and restore](#backup-and-restore)).

## Rolling back past the Raspberry Pi feature

Images built before this deployment existed have **no ARM64 variant**, so they can't run on
the Pi; the oldest image you can pin there is the first one built with this guide. On an
x86-64 host you can pin such an image, but it uses the previous search model and ignores the
vectors made by the current one. After pinning it, rebuild its vectors:

```bash
docker exec <web container> python manage.py generate_book_embeddings
```

Search then returns results again. Rolling forward later re-encodes the vectors automatically
on startup.

## Shut down Render (after the Pi is verified)

Render stays the fallback until the Pi deployment works. Shut it down only after the
[first deployment checklist](#first-deployment-checklist) passes and at least one automatic
redeploy has been confirmed.

The repository no longer contains the Render Blueprint file, but a Blueprint that is already
connected keeps its services, and may keep deploying from `main`. In the Render dashboard:

1. Open the **`library-django`** web service and either turn **Auto-Deploy** off or, if you no
   longer need it, **Delete Web Service** (Settings → Delete).
2. Delete the **`library-queue`** Key Value instance.
3. Delete the **`library-db`** PostgreSQL database. Its data is a seeded demo and is not moved
   to the Pi; export it first with Render's backup tools if you want a copy.
4. Open **Blueprints**, select this repository's Blueprint, and delete it, so Render stops
   syncing from `main`.

Afterwards, a merge into `main` triggers no Render deploy, and only the Pi updates.
