from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlmodel import Session, SQLModel, select

import app.models  # noqa: F401  (register tables)
from app.auth.security import hash_password
from app.migrations import (
    current_revision,
    ensure_migrated,
    run_downgrade,
    run_upgrade,
    stamp,
    verify_schema,
)
from app.models import User
from app.models.enums import UserRole

BASELINE = "0001_baseline"


def _url(tmp_path: Path, name: str = "m.db") -> str:
    return f"sqlite:///{tmp_path / name}"


def _table_names(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _seed_one_user(url: str) -> None:
    engine = create_engine(url)
    try:
        with Session(engine) as session:
            session.add(
                User(
                    email="legacy@supervoid.test",
                    full_name="Legacy User",
                    role=UserRole.ADMIN,
                    hashed_password=hash_password("x"),
                )
            )
            session.commit()
    finally:
        engine.dispose()


def _count_users(url: str) -> int:
    engine = create_engine(url)
    try:
        with Session(engine) as session:
            return len(session.exec(select(User)).all())
    finally:
        engine.dispose()


# --- baseline & migrations-match-models -----------------------------------


def test_baseline_upgrade_creates_full_schema(tmp_path: Path) -> None:
    url = _url(tmp_path)
    run_upgrade(url, "head")

    assert current_revision(url) == BASELINE
    # The migration-built schema must match the models exactly (the CI guard).
    assert verify_schema(url) == []
    tables = _table_names(url)
    for expected in SQLModel.metadata.tables:
        assert expected in tables
    assert "alembic_version" in tables


def test_upgrade_downgrade_roundtrip(tmp_path: Path) -> None:
    url = _url(tmp_path)
    run_upgrade(url, "head")
    assert current_revision(url) == BASELINE

    run_downgrade(url, "base")
    assert current_revision(url) is None
    tables = _table_names(url)
    assert "users" not in tables
    assert "works" not in tables


# --- non-destructive adoption of an existing (pre-Alembic) database --------


def test_ensure_migrated_adopts_legacy_db_without_recreation(tmp_path: Path) -> None:
    url = _url(tmp_path)
    # Simulate a legacy DB created by init_db()/create_all, with real data.
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    engine.dispose()
    _seed_one_user(url)

    # No alembic_version yet, but core tables exist -> must STAMP, not recreate.
    assert ensure_migrated(url) == "stamped"
    assert current_revision(url) == BASELINE
    # Data survived (no destructive recreation).
    assert _count_users(url) == 1

    # A second run is now a normal (no-op) upgrade.
    assert ensure_migrated(url) == "upgraded"
    assert _count_users(url) == 1


def test_ensure_migrated_creates_fresh_db(tmp_path: Path) -> None:
    url = _url(tmp_path)
    assert ensure_migrated(url) == "created"
    assert current_revision(url) == BASELINE
    assert verify_schema(url) == []


def test_ensure_migrated_upgrades_managed_db(tmp_path: Path) -> None:
    url = _url(tmp_path)
    run_upgrade(url, "head")  # already managed (alembic_version present)
    assert ensure_migrated(url) == "upgraded"


def test_stamp_marks_revision_without_ddl(tmp_path: Path) -> None:
    url = _url(tmp_path)
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    engine.dispose()

    assert current_revision(url) is None
    stamp(url, "head")
    assert current_revision(url) == BASELINE


# --- drift detection -------------------------------------------------------


def test_verify_schema_detects_missing_tables(tmp_path: Path) -> None:
    # An empty database is missing every model table -> drift reported.
    url = _url(tmp_path)
    create_engine(url).dispose()  # touch the file; no tables
    problems = verify_schema(url)
    assert problems
    assert any(p.startswith("missing table") for p in problems)
