#!/bin/sh
# Container entrypoint: wait for Postgres, migrate, optionally seed, then exec CMD.
set -e

DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"

echo "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT}..."
# Busy-wait using Python's socket (no nc dependency needed)
while ! python - <<PY 2>/dev/null
import socket, os, sys
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

echo "Starting server..."
exec "$@"
