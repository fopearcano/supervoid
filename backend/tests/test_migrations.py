from __future__ import annotations

from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlmodel import Session, SQLModel, select

import app.models  # noqa: F401  (register tables)
from app.auth.security import hash_password
from app.migrations import (
    alembic_config,
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


def _head() -> str:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


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


def _drop_alembic_version(url: str) -> None:
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE alembic_version")
    finally:
        engine.dispose()


# --- baseline & migrations-match-models -----------------------------------


def test_head_upgrade_creates_full_schema(tmp_path: Path) -> None:
    url = _url(tmp_path)
    run_upgrade(url, "head")

    assert current_revision(url) == _head()
    # The migration-built schema must match the models exactly (the CI guard).
    assert verify_schema(url) == []
    tables = _table_names(url)
    for expected in SQLModel.metadata.tables:
        assert expected in tables
    assert "alembic_version" in tables


def test_upgrade_downgrade_roundtrip(tmp_path: Path) -> None:
    url = _url(tmp_path)
    run_upgrade(url, "head")
    assert current_revision(url) == _head()

    run_downgrade(url, "base")
    assert current_revision(url) is None
    tables = _table_names(url)
    assert "users" not in tables
    assert "works" not in tables
    assert "story_worlds" not in tables


def test_baseline_then_upgrade_step(tmp_path: Path) -> None:
    # The schema can be built incrementally: baseline first, then forward.
    url = _url(tmp_path)
    run_upgrade(url, BASELINE)
    assert current_revision(url) == BASELINE
    assert "story_worlds" not in _table_names(url)  # not in baseline

    run_upgrade(url, "head")
    assert current_revision(url) == _head()
    assert "story_worlds" in _table_names(url)
    assert verify_schema(url) == []


# --- non-destructive adoption of existing databases ------------------------


def test_ensure_migrated_adopts_current_legacy_db(tmp_path: Path) -> None:
    url = _url(tmp_path)
    # Legacy DB created by init_db()/create_all of the CURRENT models, with data.
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    engine.dispose()
    _seed_one_user(url)

    assert ensure_migrated(url) == "stamped"  # schema already matches models
    assert current_revision(url) == _head()
    assert _count_users(url) == 1

    assert ensure_migrated(url) == "upgraded"  # now managed -> no-op upgrade
    assert _count_users(url) == 1


def test_ensure_migrated_brings_forward_old_schema(tmp_path: Path) -> None:
    url = _url(tmp_path)
    # Simulate a pre-Alembic DB at the OLD (baseline) schema: build baseline,
    # add data, then strip the version table.
    run_upgrade(url, BASELINE)
    _seed_one_user(url)
    _drop_alembic_version(url)
    assert "story_worlds" not in _table_names(url)

    assert ensure_migrated(url) == "migrated"  # stamp baseline + upgrade forward
    assert current_revision(url) == _head()
    assert "story_worlds" in _table_names(url)
    assert verify_schema(url) == []
    assert _count_users(url) == 1  # data preserved


def test_ensure_migrated_creates_fresh_db(tmp_path: Path) -> None:
    url = _url(tmp_path)
    assert ensure_migrated(url) == "created"
    assert current_revision(url) == _head()
    assert verify_schema(url) == []


def test_ensure_migrated_upgrades_managed_db(tmp_path: Path) -> None:
    url = _url(tmp_path)
    run_upgrade(url, "head")
    assert ensure_migrated(url) == "upgraded"


def test_stamp_marks_revision_without_ddl(tmp_path: Path) -> None:
    url = _url(tmp_path)
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    engine.dispose()

    assert current_revision(url) is None
    stamp(url, "head")
    assert current_revision(url) == _head()


# --- drift detection -------------------------------------------------------


def test_verify_schema_detects_missing_tables(tmp_path: Path) -> None:
    url = _url(tmp_path)
    create_engine(url).dispose()  # touch the file; no tables
    problems = verify_schema(url)
    assert problems
    assert any(p.startswith("missing table") for p in problems)
