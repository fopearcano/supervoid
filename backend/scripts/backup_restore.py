#!/usr/bin/env python
"""Backup and restore for SUPERVOID Publishing — records *and* stored assets.

A logical, dialect-agnostic backup: every table in the SQLModel metadata is
dumped to JSON (FK-dependency order, types preserved), and the local asset
storage tree is copied alongside it. Restore rebuilds the schema from the
migrations, loads the rows, and copies the assets back. Because the dump is
driven by ``SQLModel.metadata``, it automatically covers every new record type
(assets, provenance, agent runs, integrations, business, curation, …) without
per-table maintenance.

    python scripts/backup_restore.py backup  [--out DIR]
    python scripts/backup_restore.py restore --in DIR [--url URL] [--reset]

The configured database / storage path (from settings) are used unless
overridden. ``backup`` never mutates anything; ``restore`` writes into the
target database and storage path (use ``--reset`` to clear existing rows first).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# Make the application package importable when run as a plain script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import Date, DateTime, create_engine, insert, select  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

import app.models  # noqa: E402,F401  (register every table on the metadata)
from app.config import settings  # noqa: E402
from app.migrations import current_revision, ensure_migrated  # noqa: E402

DATA_FILE = "data.json"
MANIFEST_FILE = "manifest.json"
STORAGE_DIRNAME = "storage"
BACKUP_SCHEMA = "supervoid.backup/1"


def _is_temporal(column) -> bool:
    return isinstance(column.type, (DateTime, Date))


def _encode_row(table, mapping: dict) -> dict:
    """Row -> JSON-safe dict. Temporal columns become ISO strings; JSON columns
    (dict/list) pass through untouched."""
    out: dict = {}
    for col in table.columns:
        value = mapping[col.name]
        if value is not None and _is_temporal(col):
            out[col.name] = value.isoformat()
        else:
            out[col.name] = value
    return out


def _decode_row(table, data: dict) -> dict:
    out: dict = {}
    for col in table.columns:
        value = data.get(col.name)
        if value is not None and isinstance(col.type, DateTime):
            out[col.name] = datetime.fromisoformat(value)
        elif value is not None and isinstance(col.type, Date):
            out[col.name] = date.fromisoformat(value)
        else:
            out[col.name] = value
    return out


def backup(
    out_dir: str | Path,
    *,
    url: Optional[str] = None,
    storage_path: Optional[str] = None,
) -> dict:
    """Dump all records and copy the asset storage tree into ``out_dir``."""
    url = url or settings.database_url
    storage_path = storage_path or settings.storage_path
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    engine = create_engine(url)
    tables: dict[str, list[dict]] = {}
    counts: dict[str, int] = {}
    try:
        with engine.connect() as conn:
            for table in SQLModel.metadata.sorted_tables:
                rows = [
                    _encode_row(table, dict(r._mapping))
                    for r in conn.execute(select(table))
                ]
                tables[table.name] = rows
                counts[table.name] = len(rows)
        revision = current_revision(url)
    finally:
        engine.dispose()

    (out / DATA_FILE).write_text(
        json.dumps({"schema": BACKUP_SCHEMA, "tables": tables}, indent=2, default=str),
        encoding="utf-8",
    )

    # Copy the asset storage tree (real uploads, generated/ingested packages).
    files_copied = 0
    src_storage = Path(storage_path)
    dst_storage = out / STORAGE_DIRNAME
    if dst_storage.exists():
        shutil.rmtree(dst_storage)
    if src_storage.is_dir():
        shutil.copytree(src_storage, dst_storage)
        files_copied = sum(1 for p in dst_storage.rglob("*") if p.is_file())

    manifest = {
        "schema": BACKUP_SCHEMA,
        "alembic_revision": revision,
        "row_counts": counts,
        "total_rows": sum(counts.values()),
        "storage_files": files_copied,
    }
    (out / MANIFEST_FILE).write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )
    return manifest


def restore(
    in_dir: str | Path,
    *,
    url: Optional[str] = None,
    storage_path: Optional[str] = None,
    reset: bool = False,
) -> dict:
    """Rebuild the schema, load the dumped rows, and copy assets back.

    The target schema is brought to head via the migrations first. With
    ``reset`` every table is cleared before loading (otherwise a non-empty
    target is rejected to avoid clobbering live data by accident)."""
    url = url or settings.database_url
    storage_path = storage_path or settings.storage_path
    src = Path(in_dir)
    payload = json.loads((src / DATA_FILE).read_text(encoding="utf-8"))
    tables = payload["tables"]

    # Ensure the destination schema exists and is at head.
    ensure_migrated(url)

    engine = create_engine(url)
    loaded: dict[str, int] = {}
    sorted_tables = list(SQLModel.metadata.sorted_tables)
    try:
        with engine.begin() as conn:
            is_sqlite = conn.dialect.name == "sqlite"
            if is_sqlite:
                conn.exec_driver_sql("PRAGMA foreign_keys=OFF")

            existing = {
                t.name: conn.execute(select(t)).first() is not None
                for t in sorted_tables
            }
            if not reset and any(existing.values()):
                raise SystemExit(
                    "refusing to restore into a non-empty database; pass --reset "
                    "to clear it first."
                )
            if reset:
                for table in reversed(sorted_tables):
                    conn.execute(table.delete())

            for table in sorted_tables:
                rows = [_decode_row(table, r) for r in tables.get(table.name, [])]
                if rows:
                    conn.execute(insert(table), rows)
                loaded[table.name] = len(rows)
    finally:
        engine.dispose()

    # Copy the asset storage tree back (merge into the configured root).
    files_copied = 0
    src_storage = src / STORAGE_DIRNAME
    if src_storage.is_dir():
        dst_storage = Path(storage_path)
        dst_storage.mkdir(parents=True, exist_ok=True)
        for item in src_storage.rglob("*"):
            if item.is_file():
                rel = item.relative_to(src_storage)
                target = dst_storage / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
                files_copied += 1

    return {
        "row_counts": loaded,
        "total_rows": sum(loaded.values()),
        "storage_files": files_copied,
    }


def _default_backup_dir() -> str:
    # No Date.now() in scripts is fine — use the configured backups root with a
    # fixed name; callers can pass --out for a timestamped directory.
    return str(Path(settings.storage_path).parent / "backups" / "latest")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="backup_restore",
        description="Backup/restore SUPERVOID records and stored assets",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_backup = sub.add_parser("backup", help="dump records + copy assets")
    p_backup.add_argument("--out", default=None, help="output directory")
    p_backup.add_argument("--url", default=None, help="source database URL")

    p_restore = sub.add_parser("restore", help="load records + restore assets")
    p_restore.add_argument("--in", dest="in_dir", required=True, help="backup directory")
    p_restore.add_argument("--url", default=None, help="target database URL")
    p_restore.add_argument(
        "--reset", action="store_true", help="clear the target tables first"
    )

    args = parser.parse_args(argv)
    if args.cmd == "backup":
        out = args.out or _default_backup_dir()
        manifest = backup(out, url=args.url)
        print(f"backed up {manifest['total_rows']} rows and "
              f"{manifest['storage_files']} files to {out}")
        return 0
    if args.cmd == "restore":
        stats = restore(args.in_dir, url=args.url, reset=args.reset)
        print(f"restored {stats['total_rows']} rows and "
              f"{stats['storage_files']} files")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
