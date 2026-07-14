#!/bin/sh
# ---------------------------------------------------------------------------
# Docker entrypoint — runs once per container start, before the main process.
#
# Why this exists: docker-compose's `depends_on: db: condition: service_healthy`
# only guarantees Postgres is accepting TCP connections — it says nothing
# about whether the `users` table (or any future table) actually exists.
# Without this, a fresh `docker compose up` would boot the API successfully
# but every DB-backed request (signup, login, ...) would fail with
# "relation users does not exist" until someone manually ran
# `alembic upgrade head` inside the container.
#
# `set -e` ensures the container fails fast (and loudly, in `docker compose
# up` logs) if migrations fail, rather than starting an API that will error
# on every DB-backed request.
#
# `exec "$@"` replaces this shell process with the actual command (the
# Dockerfile's CMD, or docker-compose's `command:` override) as PID 1, so
# it correctly receives SIGTERM on `docker compose down` / `docker stop`
# instead of an orphaned shell swallowing the signal.
# ---------------------------------------------------------------------------
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting application..."
exec "$@"
