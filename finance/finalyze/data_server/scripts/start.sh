#!/bin/bash
set -e

# Wait for database to be ready
echo "Waiting for database..."
while ! nc -z postgres 5432; do
  sleep 1
done
echo "Database is ready!"

# Run database migrations (if using alembic)
# uv run alembic upgrade head

# Start the server
exec uv run uvicorn data_server.main:app --host 0.0.0.0 --port 8000
