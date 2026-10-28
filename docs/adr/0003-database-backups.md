# 3. Database backups: a sidecar on the database image

- **Status**: Accepted, 2026-10-28
- **Issue**: KAN-68 (part of KAN-62)

## Context

The PostgreSQL database is the library's only record of its accounts, books, loans and activity.
It lives in one Docker volume on a Raspberry Pi 5. Losing that volume or the Pi's disk would lose
everything, and the team's risk register lists data loss as risk R7. KAN-62 requires daily
backups that are checked, kept for at least a week, stored apart from the database, and restored
once in a rehearsal.

The server runs a Portainer stack from published images. It must start from images and stack
variables alone, with nothing installed or scheduled on the Pi itself, and stay within 4 GB of
memory.

## Decision

- **A `backup` service in both Compose stacks**, on `pgvector/pgvector:0.8.7-pg18`, the database's
  own image. Its `pg_dump` always matches the server's major version, it runs on amd64 and arm64,
  and it adds no new image to trust.
- **An inline POSIX shell script**, installed as `library-backup` when the container starts. Every
  10 minutes it checks whether today's backup (UTC) exists. If it doesn't and the hour is at or
  after `BACKUP_HOUR`, it takes one.
- **Each run** does four things:
  1. takes `pg_dump --format=custom`, one consistent snapshot of the whole database;
  2. reads the whole archive back with `pg_restore` before keeping it;
  3. writes a SHA-256 checksum that names the file without its folder, so the check also works on
     another machine;
  4. deletes backups older than `BACKUP_KEEP_DAYS` (7 by default), but always keeps the 7 newest.
- **A failed run** logs the failed step and its cause. It deletes only its own partial file, and
  the next check retries.
- **Storage**: the backups live in their own volume, `pgbackups`, so recreating the database volume
  leaves them intact. The files are mode 600 and owned by root, because they hold password hashes
  and personal data.
- **Off the Pi**: once a week, the operator copies the newest backup to another machine by hand and
  checks it there. The operator guide gives the steps.
- **CI** takes a backup on every run, restores it into a scratch database and compares the exact
  row count of every table. That is the reproducible trial restore that KAN-62 asks for.

## Consequences

- While the Pi's storage survives, at most one day of data can be lost. If the Pi or its disk is
  lost, up to a week can be lost: the age of the newest weekly copy.
- The weekly copy is a manual step, and a missed week widens that window. An automatic off-device
  copy is recorded in the debt register as the follow-up for when the site holds real readers'
  data.
- The service costs an idle shell loop, plus `pg_dump` for a few seconds a day. The stack's memory
  check measures it with everything else.
- A restore needs the operator guide's steps. Restoring into an older release than the one that
  made the backup is not supported.

## Alternatives considered

- **Cron on the Pi**: it runs outside the stack, so Portainer can't reproduce or redeploy it.
- **`pg_dump` from the app image through Celery**: the app image has no PostgreSQL 18 client.
  Adding one grows the image and ties backups to the application.
- **A third-party backup image**: one more image to trust and keep current, for what one script
  does.
- **A bind mount to a folder on the Pi**: it needs a host path that Docker creates owned by root,
  and Portainer may not allow relative paths for the stack.
- **Physical backups with WAL archiving**: more storage and moving parts than a 24-hour recovery
  point needs.
- **An automatic copy to another machine or a cloud bucket**: deferred. It needs credentials and a
  destination that the project doesn't have yet.
