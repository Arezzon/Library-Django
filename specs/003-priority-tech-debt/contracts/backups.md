# Contract: Database backups, the weekly copy and restores (PR 9)

**Requirements**: FR-025 to FR-033, SC-005, SC-006 | **Research**: R22 to R24

The operator uses this contract. The operator guide's backup sections follow it.

## The backup service

| Item | Value |
|---|---|
| Service | `backup`, in `docker-compose.yml` and `docker-compose-dev.yml`. A test keeps the two definitions identical. |
| Image | `pgvector/pgvector:0.8.7-pg18`, the same as `db` |
| Volume | `pgbackups`, mounted at `/backups`. It is separate from `pgdata18`, so removing or recreating the database volume leaves backups intact. |
| Connection | `PGHOST=db`, with `PGDATABASE`, `PGUSER` and `PGPASSWORD` taken from `DB_NAME`, `DB_USER` and `DB_PASSWORD` |
| Command | `library-backup loop` (default) or `library-backup once` |
| Logging | The common line format (logs-and-audit.md), service `backup`, rotated like every other service |

| Variable | Default | Meaning |
|---|---|---|
| `BACKUP_HOUR` | `1` | The UTC hour at or after which each day's backup runs; 1 is 03:00 or 04:00 in Kyiv |
| `BACKUP_KEEP_DAYS` | `7` | Backups older than this are removed, but the 7 newest always stay |

Both variables are documented in `.env.example`, the README and the operator guide. Neither is a
secret.

## Files

```text
/backups/library-20261028T010000Z.dump          # PostgreSQL custom format, whole database
/backups/library-20261028T010000Z.dump.sha256   # "<sha256>  library-20261028T010000Z.dump"
```

- **Mode**: 600, owned by root, so only the operator can read them on the Pi (FR-028).
- **Contents**: every account with its password hash, plus personal data. The files never go into
  the repository, the image or a shared folder.
- **While running**: a `.partial` file is the backup in progress. It is deleted if the run fails.

## One run

| Step | Success | Failure |
|---|---|---|
| 1. `pg_dump --format=custom` to `<name>.partial` | One consistent snapshot | Log an ERROR with `pg_dump`'s message; delete the partial file |
| 2. `pg_restore --list`, then `pg_restore --file=/dev/null` | The whole archive reads | Log an ERROR ("check failed"); delete the partial file |
| 3. Write `<name>.sha256` and rename the file | — | Log an ERROR |
| 4. Prune: delete files older than `BACKUP_KEEP_DAYS` that are not among the 7 newest | Log how many were kept and removed | Never runs after a failed step |

The run ends with one log line:

```text
2026-10-28T01:00:04.512Z INFO backup - backup: created library-20261028T010000Z.dump (48.2 MB) in 4.3 s; check passed; 7 kept, 1 removed
2026-10-28T01:00:01.020Z ERROR backup - backup: failed at pg_dump: connection to server at "db" failed; earlier backups kept; next try in 10 minutes
```

**Schedule**: the loop checks every 10 minutes. If no backup from today (UTC) exists and the hour is
at or after `BACKUP_HOUR`, it runs one, so a failed run is retried within 10 minutes. With a
healthy server, the newest backup is never older than 24 hours (SC-006).

## Operator commands

Replace `library` with the stack name.

| Task | Command |
|---|---|
| Run a backup now | `docker exec library-backup-1 library-backup once` |
| List backups | `docker exec library-backup-1 ls -lh /backups` |
| Check the latest result | `docker logs --tail 20 library-backup-1` |

## Weekly copy to another machine (FR-026)

1. Copy the newest backup and its checksum out of the container:
   `docker cp library-backup-1:/backups/<file> .` and `docker cp
   library-backup-1:/backups/<file>.sha256 .`
2. Move both to the other machine with `scp`.
3. On the other machine:
   - `sha256sum -c <file>.sha256` reports OK.
   - `pg_restore --list <file>` lists the archive. Use a PostgreSQL 18 client, or `docker run --rm
     -v "$PWD":/b:ro pgvector/pgvector:0.8.7-pg18 pg_restore --list /b/<file>`.
4. Keep the last 4 weekly copies there, readable only by the operator.
5. Delete the transfer copies from the Pi's home folder.

The weekly copy keeps the data-loss window to at most 7 days if the Pi and its disk are lost. The
register keeps an automatic off-device copy as a follow-up (FR-055).

## Restore into a separate database (FR-029)

The live database is never touched. The steps are:

1. Create an empty database:
   `docker exec library-db-1 createdb -U <DB_USER> library_restore`
2. Restore the backup into it:
   `docker exec library-backup-1 pg_restore --no-owner --exit-on-error -d library_restore /backups/<file>`
3. Start a temporary web container from the same image, with:
   - port `8001`;
   - `DB_NAME=library_restore`, `WEB_CONCURRENCY=1` and `CELERY_BROKER_URL=redis://redis:6379/15`;
   - the stack's network, and its `SECRET_KEY`, `DB_USER` and `DB_PASSWORD`.
4. Check the restored copy:
   - the record counts match the backup's (quickstart §0);
   - a librarian can sign in at port 8001;
   - a search returns results.
5. Clean up: stop and remove the temporary container, run `dropdb library_restore`, then `docker exec
   library-redis-1 redis-cli -n 15 flushdb`.

The temporary container adds about 0.7 GB of memory while it runs. Restoring into an older release
than the one that made the backup is not supported.

## Restore after losing the database

1. Stop `web` and `worker`.
2. Recreate `pgdata18`, and start `db`.
3. Restore into `library_db` with `pg_restore --no-owner --exit-on-error -d library_db`.
4. Start `web`: it migrates and re-encodes stale book vectors, as it does today.
5. Start `worker`.

## Rehearsal record (FR-029, SC-006)

Before KAN-62 closes, research.md's Measurements, and then the register, record one rehearsal:

| Field | Example |
|---|---|
| Date and operator | 2026-11-02, the operator's name |
| Backup | `library-20261102T010000Z.dump`, 48.2 MB |
| Restore duration | 3 min 20 s, from `createdb` to a passing search (target: 60 min) |
| Counts | All 9 tables match (or the differences, listed) |
| Sign-in and search | Librarian signed in; search "detective" returned 4 books |
| Peak memory | 3.4 GiB during the rehearsal |

## CI check (PR 9)

On every smoke-test runner, after the stack starts:
1. `docker compose exec -T backup library-backup once` succeeds.
2. The newest file restores into `library_restore`.
3. The exact counts of every table match `library_db`.
4. `library_restore` is dropped.

Any failure fails the job.
