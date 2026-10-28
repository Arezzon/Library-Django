# Deploying to a Raspberry Pi 5 with Portainer

This guide sets up the library site on a Raspberry Pi 5 that runs Docker and Portainer
Business Edition (BE). Portainer deploys the site as a Git repository stack from this
repository, and every merge into `main` redeploys it automatically.

It is written for an operator who knows Docker and Portainer but not this project. You don't
need to read any application code.

## Who does what

| Already done in this repository | You do this |
|---|---|
| `docker-compose.yml`: the server stack (web, worker, PostgreSQL, Redis, daily backups), using published images only | **On the Pi**: install a 64-bit OS, Docker Engine and Portainer BE |
| Multi-architecture images (`linux/amd64`, `linux/arm64`) published to `ghcr.io/arezzon/library-django` on every merge into `main` and every `v*` tag | **In Portainer**: create the stack from the repository, set its environment variables, turn on the webhook |
| CI runs lint and the full smoke test on amd64 and arm64 before anything is published | **In Portainer / your network**: make the stack webhook reachable over HTTPS with a trusted certificate |
| CI calls the Portainer webhook after both architectures are published, and checks that the site reports the new commit | **In GitHub** (repository admin): create the `production` environment, its secret `PORTAINER_WEBHOOK_URL` and optional variable `SITE_URL` |
| The image ships with its embedding model and re-encodes stored vectors on startup when the model changes | **In Render**: shut the old services down once the Pi is verified |

## Contents

- [Prerequisites](#prerequisites)
- [Create the stack](#create-the-stack)
- [Environment variables](#environment-variables)
- [Create the first librarian account](#create-the-first-librarian-account)
- [Review librarian accounts after an update](#review-librarian-accounts-after-an-update)
- [First deployment checklist](#first-deployment-checklist)
- [Viewing logs](#viewing-logs)
- [Daily backups](#daily-backups)
- [Weekly copy to another machine](#weekly-copy-to-another-machine)
- [Restore into a separate database](#restore-into-a-separate-database)
- [Restore after losing the database](#restore-after-losing-the-database)
- [Rehearse a restore](#rehearse-a-restore)
- [Check data persistence and limits](#check-data-persistence-and-limits)
- [Upgrade to PostgreSQL 18 and Redis 8 (one-time reset)](#upgrade-to-postgresql-18-and-redis-8-one-time-reset)
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
| `LOG_LEVEL` | no | `INFO` | How much the web service, Gunicorn and the worker log: `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`. See [Viewing logs](#viewing-logs). Any other value stops the web service with an error naming this setting. |
| `DB_NAME` / `DB_USER` | no | `library_db` / `postgres` | Database name and user. |
| `WEB_CONCURRENCY` | no | `3` | Gunicorn web workers. Each holds one model copy of about 0.6 GB. |
| `BOOK_EMBEDDING_THREADS` | no | `2` | Inference threads per web worker. |
| `BACKUP_HOUR` | no | `1` | The UTC hour at or after which each day's backup runs. `1` is 03:00 or 04:00 in Kyiv. See [Daily backups](#daily-backups). Any value other than a whole number from 0 to 23 stops the `backup` service with an error naming this setting. |
| `BACKUP_KEEP_DAYS` | no | `7` | Backups older than this many days are deleted; the 7 newest always stay. Any value other than a whole number stops the `backup` service with an error naming this setting. |

Generate `SECRET_KEY` and `DB_PASSWORD` on any machine with Python:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

> **Warning: `DB_PASSWORD` is fixed when the database volume is first created.** Changing the
> variable later does not change the password inside the existing database; the site would
> fail to connect. To change it, change it in PostgreSQL first, or remove the `pgdata18` volume
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

## Review librarian accounts after an update

Sign-up always creates a visitor account, and only a librarian can make someone a librarian.
Librarians manage the catalog, the loans and every account, and they reach the Django admin,
so only the people who run the library should hold the role. Review the librarian accounts
right after deploying this release, and again whenever someone leaves the library team.

1. Signed in as a librarian, open `/admin/authentication/customuser/?role__exact=1`, the
   user list filtered to librarians.
2. List when each of them last signed in. An account's creation time cannot tell you when it
   was made, so rely on the email address and the last sign-in:

   ```bash
   docker exec library-web-1 python manage.py shell -c "from authentication.models import CustomUser
   for user in CustomUser.objects.filter(role=1).order_by('email'): print(user.email, user.last_login, user.is_active)"
   ```

   Replace `library` with your stack name.
3. For every account that does not belong to an authorized librarian, open it in the admin and
   either set **Role** to `visitor` or untick **Active**. Deactivating keeps the account and its
   loans, and the person can no longer sign in.
4. Record the date, the number of accounts reviewed and each change (the email and what you
   changed), and send the record to the maintainers.

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

Every service writes one line per record, in one format:

```text
2026-10-27T10:15:30.123Z WARNING web 8f14e45fceea167a5a36dedd4bea2543 django.request: Forbidden: /api/v1/user/
```

The fields are the time in UTC with milliseconds, the level, the service (`web`, `worker` or
`backup`), the request identifier (`-` outside a request), the logger and the message. Every
line of a traceback starts the same way, followed by `| `. Passwords, secrets, session
identifiers and search text never appear: they are replaced with `[redacted]`.

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

**Follow one request.** Every response carries an `X-Request-ID` header, and the background
work a request starts logs the same identifier. To find every line of one request, in the web
service and in the worker:

```bash
id=8f14e45fceea167a5a36dedd4bea2543
for c in library-web-1 library-worker-1; do docker logs "$c" 2>&1 | grep "$id"; done
```

In Portainer, open each container's **Logs** and search for the identifier.

**Level.** `LOG_LEVEL` sets how much the web service, Gunicorn and the worker write. `INFO`, the
default, includes the startup steps; `WARNING` keeps only warnings and errors, refused requests
included.

**Rotation.** Docker keeps at most 5 files of 10 MB per container and deletes older lines, so
the five containers use at most 250 MB of disk, under the 500 MB limit.

**Audit trail.** Librarians read who changed what in the admin site, at
`/admin/audit/auditentry/`: roles and account status, loans, and books' copies and deletions,
each with its time, channel and request identifier. Nobody can edit or delete an entry.

## Daily backups

The database lives in the `pgdata18` volume and the event queue in `redisdata8`. Both survive
redeploys and reboots. The `backup` service backs the database up every day into a volume of its
own, `pgbackups`, so removing or recreating `pgdata18` leaves the backups intact.

- **Schedule**: every 10 minutes the service checks whether today's backup (UTC) exists. If it
  doesn't and the hour is at or after `BACKUP_HOUR` (default `1`, which is 03:00 or 04:00 in
  Kyiv), it takes one. A failed run is retried at the next check, so on a healthy server the
  newest backup is never older than 24 hours.
- **Each run**:
  - takes one consistent `pg_dump` of the whole database;
  - reads the whole archive back to check it;
  - writes a checksum file;
  - deletes backups older than `BACKUP_KEEP_DAYS` (default `7`), except that the 7 newest always
    stay.
- **Files**: `/backups/library-<UTC time>.dump` and its `.dump.sha256`. A `.partial` file is a
  backup in progress; a failed run deletes it and keeps every earlier backup.
- **Who can read them**: the files are mode 600 and owned by root, so only the operator can read
  them on the Pi. **Backups contain every account's password hash and readers' personal data.**
  Never put a backup or a copy of one in the repository, an image or a shared folder.

Replace `library` with your stack name:

| Task | Command |
|---|---|
| Check the latest result | `docker logs --tail 20 library-backup-1` |
| List the backups | `docker exec library-backup-1 ls -lh /backups` |
| Take a backup now | `docker exec library-backup-1 library-backup once` |

A successful run logs one line such as
`2026-10-28T01:00:04.512Z INFO backup - backup: created library-20261028T010000Z.dump (48.2 MB) in 4.3 s; check passed; 7 kept, 1 removed`.
A failed run logs an `ERROR` line with the step and the cause, for example
`... ERROR backup - backup: failed at pg_dump: ...; earlier backups kept; next try in 10 minutes`.

## Weekly copy to another machine

Daily backups stay on the Pi. Once a week, copy the newest one to another machine, so that losing
the Pi or its disk costs at most a week of data:

1. Copy the newest backup and its checksum out of the container:

   ```bash
   file=$(docker exec library-backup-1 sh -c 'ls -1t /backups/*.dump | head -1')
   docker cp "library-backup-1:$file" . && docker cp "library-backup-1:$file.sha256" .
   ```

2. Move both files to the other machine with `scp`.
3. On the other machine, check them:
   - `sha256sum -c library-<time>.dump.sha256` reports `OK`;
   - `pg_restore --list library-<time>.dump` lists the archive. Use a PostgreSQL 18 client, or
     `docker run --rm -v "$PWD":/b:ro pgvector/pgvector:0.8.7-pg18 pg_restore --list /b/library-<time>.dump`.
4. Keep the last 4 weekly copies there, readable only by you (`chmod 600`).
5. Delete the transfer copies from the Pi's home folder.

## Restore into a separate database

Use this to check a backup, or to look at old data, without touching the live database. The
temporary web container uses about 0.7 GB of memory while it runs.

1. Create an empty database (use your `DB_USER`):

   ```bash
   docker exec library-db-1 createdb -U postgres library_restore
   ```

2. Restore the backup into it:

   ```bash
   docker exec library-backup-1 pg_restore --no-owner --exit-on-error -d library_restore /backups/library-<time>.dump
   ```

3. Start a temporary web container from the stack's image on port 8001. It needs the stack's
   `SECRET_KEY` and `DB_PASSWORD`; `read -rs` keeps them out of the shell history:

   ```bash
   read -rs -p "SECRET_KEY: " SECRET_KEY; echo; export SECRET_KEY
   read -rs -p "DB_PASSWORD: " DB_PASSWORD; echo; export DB_PASSWORD
   docker run --rm -d --name library-restore-check --network library_default -p 8001:8000 \
     -e SECRET_KEY -e DB_PASSWORD -e DB_USER=postgres -e DB_HOST=db -e DB_NAME=library_restore \
     -e WEB_CONCURRENCY=1 -e CELERY_BROKER_URL=redis://redis:6379/15 \
     -e TRUST_X_FORWARDED_PROTO=False -e ALLOWED_HOSTS=localhost,127.0.0.1,<pi address> \
     "$(docker inspect --format '{{.Config.Image}}' library-web-1)"
   ```

   Its events go to broker database 15, so the live worker never sees them, and its cookies work
   over plain HTTP on port 8001.
4. Check the restored copy:
   - the record counts match the backup's. Take the counts of the live database right before
     `library-backup once` with the query in [Check data persistence and limits](#check-data-persistence-and-limits),
     then run it with `-d library_restore`;
   - a librarian can sign in at `http://<pi address>:8001/authentication/login/`;
   - a search in the catalog returns books.
5. Clean up:

   ```bash
   docker stop library-restore-check
   docker exec library-db-1 dropdb -U postgres library_restore
   docker exec library-redis-1 redis-cli -n 15 flushdb
   ```

Restoring into an older release than the one that made the backup is not supported.

## Restore after losing the database

1. Stop `web` and `worker` in Portainer.
2. Remove and recreate the `pgdata18` volume (this deletes the old data), then start `db`.
3. Restore the newest backup into the live database:

   ```bash
   docker exec library-backup-1 pg_restore --no-owner --exit-on-error -d library_db /backups/library-<time>.dump
   ```

4. Start `web`. It migrates the database and re-encodes any book vectors that don't match its
   model, as it does after every deployment.
5. Start `worker`.

## Rehearse a restore

Rehearse "Restore into a separate database" once after setting up backups, at a quiet time, with
a fresh backup (`library-backup once`). Time it from `createdb` to a passing search; the target is
under 60 minutes. Send the maintainers:

| Field | Example |
|---|---|
| Date and operator | 2026-11-02, the operator's name |
| Backup | `library-20261102T010000Z.dump`, 48.2 MB |
| Restore duration | 3 min 20 s, from `createdb` to a passing search |
| Counts | All tables match, or the differences |
| Sign-in and search | A librarian signed in; a search for "detective" returned books |
| Peak memory | From `docker stats` during the rehearsal |

## Check data persistence and limits

Do this once after deploying backups, and after any change to the Pi's storage. Replace `library`
with your stack name, and `postgres` and `library_db` with your `DB_USER` and `DB_NAME`.

1. **Record counts**: take them before and after each step below; they must match every time.

   ```bash
   docker exec library-db-1 psql -U postgres -d library_db -At -F ' ' -c "select 'accounts', count(*) from authentication_customuser
   union all select 'authors', count(*) from author_author union all select 'books', count(*) from book_book
   union all select 'book vectors', count(*) from book_bookembedding union all select 'loans', count(*) from order_order
   union all select 'events', count(*) from events_userevent"
   ```

2. **Restart each service** and time how long the site takes to answer again (under 3 minutes):

   ```bash
   for s in db redis web worker backup; do
     docker restart library-$s-1; start=$(date +%s)
     until curl -fsS -o /dev/null http://localhost:8000/api/v1/version/; do sleep 2; done
     echo "$s: back in $(( $(date +%s) - start )) s"
   done
   ```

   Repeat after a redeploy in Portainer and after `sudo reboot`, timing the reboot from another
   machine.
3. **First request after a quiet day**: after 24 hours without traffic, time the first request and
   a second one; they should be about as fast:
   `curl -s -o /dev/null -w '%{time_total} s\n' http://localhost:8000/authentication/login/`.
4. **Limits**:
   - `docker system df -v` for the space used by `pgdata18`, `redisdata8` and `pgbackups`, and
     `df -h /` for the free space;
   - `sudo du -ch /var/lib/docker/containers/*/*-json.log | tail -1` for the logs;
   - memory, from [Measure the stack on the Pi](#measure-the-stack-on-the-pi);
   - confirm that the old Render services are gone ([Shut down Render](#shut-down-render-after-the-pi-is-verified)).

Send each result to the maintainers. The site stores no uploaded files: every record lives in the
database that the backups cover, and a future upload feature must keep its files in a volume that
the backups also cover.

## Upgrade to PostgreSQL 18 and Redis 8 (one-time reset)

The stack moved from PostgreSQL 15 and Redis 7.4 to PostgreSQL 18 (`pgvector/pgvector:0.8.7-pg18`)
and Redis 8 (`redis:8.10.2-alpine`). PostgreSQL 18 cannot read PostgreSQL 15 data files, so the
upgraded services use new, empty volumes (`pgdata18`, `redisdata8`). The site's data is **not
moved**: it was demo seed data only, so it is dropped and seeded again. The old `pgdata` and
`redisdata` volumes stay untouched until step 7, so until then reverting the change on `main`
brings the previous stack back exactly as it was.

The commands assume the stack is called `library`; replace it with your stack name.

1. **Check that the server holds only seed data.** Stop here if it does not.

   ```bash
   docker exec library-db-1 psql -U postgres -d library_db -At \
     -c "select email from authentication_customuser order by email"
   # expect exactly: alice@library.com, bob@library.com, librarian@library.com, reader@library.com
   docker exec library-db-1 psql -U postgres -d library_db -At \
     -c "select (select count(*) from author_author), (select count(*) from book_book), (select count(*) from order_order)"
   # expect: 8|9|3
   ```

   If another user exists or the counts differ, real data may be present. **Do not continue**;
   ask the maintainers for a way to carry the data over.
2. **Before the change is merged**, set `DJANGO_SEED=true` in the stack's environment variables
   and save. If Portainer redeploys the stack on save, that is harmless: on the current database
   seeding does nothing, because it skips once users exist.
3. **Take the site off the internet**, for example by pausing the reverse proxy route or the
   port forward. Seeding recreates the demo accounts with the passwords published in the
   README, including a librarian, and they must be replaced before the site is reachable again.
4. **Merge the change.** The webhook redeploys the stack: `db` starts PostgreSQL 18 on the empty
   `pgdata18` and `redis` starts on the empty `redisdata8`; `web` runs the migrations, seeds,
   encodes every book with the current model, then serves. Confirm the new commit as
   [Confirm deployments](#confirm-deployments) describes, from the local network.
5. **Replace the demo passwords** as the `DJANGO_SEED` warning in
   [Environment variables](#environment-variables) describes, set `DJANGO_SEED=false` and save,
   then make the site reachable again.
6. **Verify**:
   - the step 1 queries return the same four emails and `8|9|3`;
   - this returns `0` (no book without a vector):

     ```bash
     docker exec library-db-1 psql -U postgres -d library_db -At \
       -c "select count(*) from book_book b left join book_bookembedding e on e.book_id = b.id where e.book_id is null"
     ```

   - a search finds the seeded books;
   - [Measure the stack on the Pi](#measure-the-stack-on-the-pi) passes.
7. **Delete the old volumes** in Portainer (**Volumes**): `library_pgdata` and
   `library_redisdata`. After this, rolling back means another reset on the previous images.

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
- 95% of catalog page loads finish within **2 s**;
- saving a book (including its embedding) takes under **2 s**.

The check needs Python 3 and Docker on the Pi; it only reads the running containers and adds
and deletes a few temporary books named `budget-check-…`.

1. Get the script. The repository is public, so a shallow clone is enough:

   ```bash
   git clone --depth 1 https://github.com/Arezzon/Library-Django.git
   cd Library-Django
   ```

2. Run it against your stack (use the stack name from Portainer and the site's port). The
   catalog should hold books, for example the demo data (`DJANGO_SEED=true`) or your own.
   Search and the catalog are open only to signed-in accounts, so the script signs in first:
   `--email` names an active account, for example your librarian account. It asks for that
   account's password, or reads it from `BUDGET_CHECK_PASSWORD`; never put the password on the
   command line, where it would stay in the shell history.

   ```bash
   python3 scripts/smoke_stack_budget.py --project-name library \
     --base-url http://localhost:8000 --email librarian@example.com \
     --max-memory-gib 4 --max-search-p95-ms 500 --max-catalog-p95-ms 2000 \
     --max-save-ms 2000
   ```

   It prints a JSON summary ending in `"result": "PASS"` or `"result": "FAIL: …"`. Its
   `catalog_ms` part times 60 loads of the catalog page, `/book/`: `first` is the first load,
   and 95% of the loads took at most `p95` milliseconds. If it stops with "Could not sign in",
   check the email and the password.

3. If it fails, change one setting in the stack's environment variables, redeploy, and run it
   again:
   1. **Memory too high**: lower `WEB_CONCURRENCY` from `3` to `2`. Each worker holds one model
      copy of about 0.6 GB.
   2. **Searches or saves too slow**: raise `BOOK_EMBEDDING_THREADS` from `2` to `3`, then `4`.
      If that doesn't help, lower `WEB_CONCURRENCY` to free CPU cores.
   3. **Catalog pages too slow**: the page does no model work, so first run the check again
      when nothing else is running, such as a backup or an update. If it still fails, lower
      `WEB_CONCURRENCY` to free CPU cores.
   No rebuild is needed for any of them.

4. **Report the results**: send the JSON summary, with the values of `WEB_CONCURRENCY` and
   `BOOK_EMBEDDING_THREADS` you used, to the maintainers. They are recorded in
   `specs/001-rpi-portainer-deploy/research.md` (§R1), and the feature counts as complete only
   once the targets are met there, or relaxed to the measured values with the project owner's
   sign-off. The catalog timing is also recorded in `specs/003-priority-tech-debt/research.md`,
   under "Measurements".

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
