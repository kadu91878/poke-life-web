#!/bin/sh
set -e

SQLITE_TARGET="${SQLITE_PATH:-/app/backend/db.sqlite3}"
mkdir -p "$(dirname "$SQLITE_TARGET")"

python manage.py migrate --noinput

exec daphne -b 0.0.0.0 -p "${PORT:-8000}" config.asgi:application
