# Contract: Database and broker images, volumes and the one-time reset (PR 3)

**Requirements**: FR-021–FR-024, SC-009 | **Research**: R12–R14 |
**Data model**: [§3–4](../data-model.md#3-service-data-volumes-pr-3)

## Compose services

Both stacks must match exactly, and a test parses both files to enforce it.

| Service | Image | Volume → mount | Unchanged |
|---|---|---|---|
| `db` | `pgvector/pgvector:0.8.7-pg18` | `pgdata18` → `/var/lib/postgresql` | `POSTGRES_*` variables and the `pg_isready` healthcheck |
| `redis` | `redis:8.10.2-alpine` | `redisdata8` → `/data` | `redis-server --appendonly yes --appendfsync always --maxmemory-policy noeviction` and the `redis-cli ping` healthcheck |

**Rules**:
- Tags are exact versions. No floating tags such as `pg18` or `8-alpine`.
- Both images are published for `linux/amd64` and `linux/arm64`.
- The `pgdata` and `redisdata` volume definitions are removed from both files, so Compose no
  longer creates them. Existing ones on the Pi stay until the operator deletes them.
- `web` and `worker` services, environment variables and `.env.example` are unchanged.
- The server stack still starts from published images and Portainer environment values alone.

## Reset on the Raspberry Pi

This is the required content for the operator guide section, which also links to it from
"Backup and restore". The container and volume names assume the stack is called `library`.

1. **Check that the server holds only seed data.** Stop if this does not hold.

   ```bash
   docker exec library-db-1 psql -U postgres -d library_db -At \
     -c "select email from authentication_customuser order by email"
   # expect exactly: alice@library.com, bob@library.com, librarian@library.com, reader@library.com
   docker exec library-db-1 psql -U postgres -d library_db -At \
     -c "select (select count(*) from author_author), (select count(*) from book_book), (select count(*) from order_order)"
   # expect the counts of a freshly seeded development stack (quickstart §4.1)
   ```

   If another user exists, or the counts differ, real data may be present. **Do not continue**;
   ask the maintainers for a way to carry the data over.
2. **Before the merge**, set `DJANGO_SEED=true` in the stack's environment variables and save.
   A redeploy on save is harmless: on the current database seeding does nothing, because it
   skips once users exist.
3. **Take the site off the internet** (pause the proxy route or the port forward). Seeding
   recreates the demo accounts with their published passwords, and FR-023 requires them to be
   replaced before the site is reachable.
4. **Merge PR 3.** The webhook redeploys the stack:
   - `db` starts PostgreSQL 18 on the empty `pgdata18`, and `redis` starts on the empty
     `redisdata8`;
   - `web` runs the migrations, seeds, re-encodes every book with the current model, then serves.

   Confirm the new commit from the local network, as the guide's "Confirm deployments" section
   describes.
5. **Replace the demo passwords** as the guide's seeding warning describes. Set
   `DJANGO_SEED=false`, save, then make the site reachable again.
6. **Verify (SC-009)**:
   - the step 1 queries now return the fresh-seed values;
   - `select count(*) from book_book b left join book_bookembedding e on e.book_id = b.id
     where e.book_id is null` returns `0`;
   - a search finds each seeded book;
   - `scripts/smoke_stack_budget.py` passes, as in "Measure the stack on the Pi".
7. **Delete the old volumes** in Portainer (**Volumes**): `library_pgdata` and
   `library_redisdata`. Until then, reverting PR 3 on `main` brings the previous stack back with
   its data. Afterwards, a rollback needs another reset.

## Development and CI

- CI runs `docker compose … down -v` after every run, so it always starts on the new volumes.
- Local developers seed automatically, because `DJANGO_SEED` defaults to `true` in
  `docker-compose-dev.yml`. The README tells them they can remove the old
  `<project>_pgdata` and `<project>_redisdata` volumes.
