"""Alembic helpers shared by the app, the management CLI, and tests.

One source of truth for building the Alembic ``Config`` (URL resolved from
settings unless overridden), plus thin wrappers for the operations the rest of
the system needs: upgrade, downgrade, stamp, current revision, a non-destructive
``ensure_migrated`` for startup, and a dialect-agnostic schema verifier for CI.
"""
from __future__ import annotations

from typing import Optional

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlmodel import SQLModel

import app.models  # noqa: F401  (register every table on SQLModel.metadata)
from app.config import BASE_DIR, settings

ALEMBIC_INI = BASE_DIR / "alembic.ini"
ALEMBIC_DIR = BASE_DIR / "alembic"

# Presence of any of these on a connection with no ``alembic_version`` table
# means we are looking at a legacy, pre-Alembic database created by init_db().
_LEGACY_MARKER_TABLES = ("users", "works", "manuscripts", "authors")


def alembic_config(url: Optional[str] = None) -> Config:
    """Build an Alembic Config pointed at this project, with the URL resolved
    from ``settings`` unless an explicit ``url`` is given (used by tests)."""
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", url or settings.database_url)
    return cfg


def run_upgrade(url: Optional[str] = None, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def run_downgrade(url: Optional[str] = None, revision: str = "-1") -> None:
    command.downgrade(alembic_config(url), revision)


def stamp(url: Optional[str] = None, revision: str = "head") -> None:
    """Mark a database as being at ``revision`` without running any DDL."""
    command.stamp(alembic_config(url), revision)


def current_revision(url: Optional[str] = None) -> Optional[str]:
    engine = create_engine(url or settings.database_url)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def ensure_migrated(url: Optional[str] = None) -> str:
    """Bring a database to head **non-destructively**.

    - Already managed (``alembic_version`` present) -> ``upgrade head``.
    - Legacy pre-Alembic DB (core tables exist, no version table) -> ``stamp
      head`` (the current schema *is* the baseline; never recreate tables).
    - Empty DB -> ``upgrade head`` (creates the full schema).

    Returns one of ``upgraded`` / ``stamped`` / ``created``.
    """
    target_url = url or settings.database_url
    engine = create_engine(target_url)
    try:
        insp = inspect(engine)
        has_version = insp.has_table("alembic_version")
        has_legacy = any(insp.has_table(t) for t in _LEGACY_MARKER_TABLES)
    finally:
        engine.dispose()

    cfg = alembic_config(target_url)
    if has_version:
        command.upgrade(cfg, "head")
        return "upgraded"
    if has_legacy:
        # Pre-existing populated database — adopt it at the baseline.
        command.stamp(cfg, "head")
        return "stamped"
    command.upgrade(cfg, "head")
    return "created"


def verify_schema(url: Optional[str] = None) -> list[str]:
    """Compare the live database schema to ``SQLModel.metadata`` (tables and
    column names). Returns a list of human-readable discrepancies; an empty
    list means the database matches the models.

    Deliberately structural (names only) rather than full type comparison: this
    stays dialect-agnostic (no SQLite/Postgres enum/CHECK noise) while still
    catching the failure that matters — a model added without a migration.
    """
    engine = create_engine(url or settings.database_url)
    problems: list[str] = []
    try:
        insp = inspect(engine)
        meta_tables = set(SQLModel.metadata.tables)
        db_tables = {
            name
            for name in insp.get_table_names()
            if name != "alembic_version" and not name.startswith("sqlite_")
        }

        for table in sorted(meta_tables - db_tables):
            problems.append(f"missing table: {table}")
        for table in sorted(db_tables - meta_tables):
            problems.append(f"unexpected table: {table}")

        for table in sorted(meta_tables & db_tables):
            meta_cols = set(SQLModel.metadata.tables[table].columns.keys())
            db_cols = {col["name"] for col in insp.get_columns(table)}
            for col in sorted(meta_cols - db_cols):
                problems.append(f"{table}: missing column '{col}'")
            for col in sorted(db_cols - meta_cols):
                problems.append(f"{table}: unexpected column '{col}'")
    finally:
        engine.dispose()
    return problems
