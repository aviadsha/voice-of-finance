#!/bin/sh
set -e

# Apply database migrations before starting (disable with RUN_MIGRATIONS=false).
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "Running database migrations..."
  alembic upgrade head
fi

# Optionally insert demo content (no API keys required).
if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  python -m app.cli seed
fi

exec "$@"
