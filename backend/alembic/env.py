"""Alembic environment for SUPERVOID Publishing.

Single source of truth for the schema is the SQLModel metadata; the database
URL comes from the application settings (or an explicit url set on the Config by
app.migrations). Works for both SQLite (with batch/ALTER emulation) and
PostgreSQL.
"""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# Make the application package importable regardless of the working directory
# from which alembic is invoked (env.py lives at backend/alembic/env.py).
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402
import app.models  # noqa: E402,F401  (registers every table on SQLModel.metadata)
from sqlmodel import SQLModel  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _resolve_url() -> str:
    """Explicit url on the Config wins; otherwise fall back to settings."""
    url = config.get_main_option("sqlalchemy.url")
    return url or settings.database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection."""
    url = _resolve_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    url = _resolve_url()
    connectable = create_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite cannot ALTER most things in place; batch mode rebuilds
            # tables so future migrations work on SQLite as well as Postgres.
            render_as_batch=is_sqlite,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
