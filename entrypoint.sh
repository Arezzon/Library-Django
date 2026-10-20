#!/bin/sh
# Container entrypoint: wait for Postgres, migrate, optionally seed, then exec CMD.
set -e

DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"

# DATABASE_URL takes precedence over DB_* in the Django settings as well.
if [ -n "${DATABASE_URL}" ]; then
  echo "Waiting for PostgreSQL from DATABASE_URL..."
else
  echo "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT}..."
fi
# Busy-wait using Python's socket (no nc dependency needed)
while ! python - <<PY 2>/dev/null
import socket, os, sys
from urllib.parse import urlsplit
url = os.getenv("DATABASE_URL")
if url:
    parts = urlsplit(url)
    host, port = parts.hostname, parts.port or 5432
else:
    host = os.getenv("DB_HOST", "postgres")
    port = int(os.getenv("DB_PORT", "5432"))
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect((host, port))
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
PY
do
  echo "  PostgreSQL is unavailable - sleeping 1s"
  sleep 1
done
echo "PostgreSQL is up - continuing"

echo "Applying database migrations..."
python manage.py migrate --noinput

if [ "${DJANGO_SEED}" = "true" ]; then
  echo "Seeding database with sample data..."
  python seed_db.py
fi

# Bring stored vectors in line with the image's model before serving traffic.
# Books that already match are skipped, so a normal start runs no inference;
# a failure stops startup (set -e) and the next start resumes where it ended.
echo "Re-encoding stale book embeddings..."
python manage.py generate_book_embeddings --offline --threads "$(python -c 'import os; print(min(os.cpu_count() or 1, 4))')"

echo "Starting server..."

exec "$@"
