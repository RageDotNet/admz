#!/bin/sh
# Agent DMZ entrypoint: permissions → migrate → serve (infra-v2.md startup order).
set -e

DB_PATH="${DMZ_DB_FILE:-/var/lib/dmz/dmz.db}"
mkdir -p "$(dirname "$DB_PATH")"

# Enforce owner-only permissions on the SQLite DB file (#16).
if [ -f "$DB_PATH" ]; then
    chmod 0600 "$DB_PATH"
fi

alembic upgrade head

# New file created by alembic: enforce 0600 after creation as well.
if [ -f "$DB_PATH" ]; then
    chmod 0600 "$DB_PATH"
fi

# Gunicorn log-level is lowercase; config/env often uses INFO.
log_level=$(printf '%s' "${LOG_LEVEL:-info}" | tr '[:upper:]' '[:lower:]')

exec gunicorn -w 2 --threads 16 --timeout 900 --graceful-timeout 900 --keep-alive 5 \
    -b 0.0.0.0:8000 --worker-class gthread \
    --access-logfile - --error-logfile - --capture-output \
    --log-level "$log_level" \
    'admz.app:create_app_standalone()'
