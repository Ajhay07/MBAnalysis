#!/bin/sh
# Runs at container START (not build time), so it runs against the Railway
# persistent volume, which doesn't exist yet during the build step.
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Bootstrapping admin user (no-op if users already exist or ADMIN_EMAIL/ADMIN_PASSWORD unset)..."
python create_admin.py || true

echo "Starting server on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
