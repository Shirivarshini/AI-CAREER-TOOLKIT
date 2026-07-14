"""
Alembic migration environment.

Why this file exists
---------------------
Alembic needs to know (a) how to connect to the database and (b) where
the SQLAlchemy metadata describing all tables lives, so it can compare
the two and autogenerate migration scripts.

How it works
------------
- The DB URL is pulled from our own `app.config.settings.get_settings()`
  (SYNC_DATABASE_URI, using psycopg2) instead of duplicating credentials
  in alembic.ini — one source of truth for config.
- `target_metadata` points at `app.core.database.Base.metadata`. As soon
  as ORM models are defined (later modules) and imported in
  `app/models/__init__.py`, `alembic revision --autogenerate` will pick
  them up automatically.
- Migrations run in "offline" mode (generates SQL without a live DB
  connection) or "online" mode (executes directly against the DB) — both
  are supported, matching Alembic's standard template.

Where future code should go
----------------------------
Nothing else needs to change here as new models are added — just make
sure new model modules are imported inside `app/models/__init__.py` so
their tables register on `Base.metadata`.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the `app` package importable when Alembic is run from the backend/ dir.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.config.settings import get_settings  # noqa: E402
from app.core.database import Base  # noqa: E402
import app.models  # noqa: E402,F401  (ensures all models are registered on Base.metadata)

# Alembic Config object, provides access to values in alembic.ini
config = context.config

# Interpret the config file for logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject our real DB URL (sync driver) from app settings.
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.SYNC_DATABASE_URI)

# Metadata used for autogeneration.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (generates raw SQL)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
