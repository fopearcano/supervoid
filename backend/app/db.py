from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _engine_kwargs() -> dict:
    kwargs: dict = {"echo": settings.database_echo}
    if settings.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


engine: Engine = create_engine(settings.database_url, **_engine_kwargs())


def init_db() -> None:
    """Create database schema directly from the models.

    Retained for backward compatibility (fresh dev databases, the test suite,
    and any caller importing it). ``prepare_database`` is the startup entry
    point that chooses between this and managed migrations.
    """
    from app import models  # noqa: F401  (registers metadata)

    SQLModel.metadata.create_all(engine)


def prepare_database() -> str:
    """Prepare the schema at startup according to ``settings.db_init_strategy``.

    - ``create_all`` (default): ``init_db()`` — fast path for fresh dev DBs.
    - ``migrate``: run Alembic, non-destructively adopting a legacy database.
    - ``skip``: do nothing (migrations are applied out-of-band).

    Returns the mode actually used (for logging). Unknown values fall back to
    the safe developer default, ``create_all``.
    """
    strategy = (settings.db_init_strategy or "create_all").lower()
    if strategy == "migrate":
        from app.migrations import ensure_migrated

        ensure_migrated()
        return "migrate"
    if strategy == "skip":
        return "skip"
    init_db()
    return "create_all"


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
