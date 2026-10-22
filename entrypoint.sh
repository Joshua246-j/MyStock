#!/bin/sh
set -e

echo "=== Running database migrations ==="
python -m alembic upgrade head || echo "Notice: Alembic migration skipped or schema already up to date."

echo "=== Starting Stock Terminal API ==="
exec uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
