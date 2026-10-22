#!/bin/sh
set -e

echo "=== Running database migrations ==="
python -m alembic upgrade head

echo "=== Starting Stock Terminal API ==="
exec uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
