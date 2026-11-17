#!/bin/bash
# Runs on container start: migrate, make sure an admin exists, serve.
set -e

echo "Running database migrations..."
alembic upgrade head

# Accounts are created only by administrators, so an empty users table has no
# way in. Seeds the first SUPER_ADMIN from ADMIN_BOOTSTRAP_LOGIN/PASSWORD; a
# no-op once one exists, and never stops the start.
echo "Ensuring an administrator exists..."
python -m scripts.bootstrap_admin || echo "bootstrap_admin: skipped"

echo "Starting the API..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
