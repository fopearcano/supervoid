#!/usr/bin/env python
"""Database migration management for SUPERVOID Publishing.

A thin CLI over Alembic + app.migrations. Run from the backend directory:

    python scripts/manage_db.py current      # show the current revision
    python scripts/manage_db.py upgrade      # upgrade to head
    python scripts/manage_db.py downgrade -1 # step back one revision
    python scripts/manage_db.py stamp head   # adopt an existing DB at head
    python scripts/manage_db.py ensure       # non-destructive: stamp legacy / upgrade / create
    python scripts/manage_db.py verify       # structural check: configured DB vs models
    python scripts/manage_db.py check        # CI: migrations build a schema matching the models

All commands resolve the database URL from settings (DATABASE_URL) except
``check``, which uses a throwaway SQLite database and needs no configured DB.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

# Make the application package importable when run as a plain script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import command  # noqa: E402

from app.migrations import (  # noqa: E402
    alembic_config,
    current_revision,
    ensure_migrated,
    run_downgrade,
    run_upgrade,
    stamp,
    verify_schema,
)


def _cmd_current(_args) -> int:
    print(current_revision() or "(none)")
    return 0


def _cmd_upgrade(args) -> int:
    run_upgrade(revision=args.revision)
    print(f"upgraded to {args.revision}")
    return 0


def _cmd_downgrade(args) -> int:
    run_downgrade(revision=args.revision)
    print(f"downgraded to {args.revision}")
    return 0


def _cmd_stamp(args) -> int:
    stamp(revision=args.revision)
    print(f"stamped {args.revision}")
    return 0


def _cmd_ensure(_args) -> int:
    print(f"ensure: {ensure_migrated()}")
    return 0


def _cmd_history(_args) -> int:
    command.history(alembic_config(), verbose=True)
    return 0


def _cmd_verify(_args) -> int:
    problems = verify_schema()
    if problems:
        print("schema OUT OF SYNC with models:")
        for problem in problems:
            print(" -", problem)
        return 1
    print("schema matches models ✓")
    return 0


def _cmd_check(_args) -> int:
    # CI-safe: build the schema purely from migrations on a throwaway SQLite
    # database, then confirm it matches the models. No real/configured DB.
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{Path(tmp) / 'check.db'}"
        run_upgrade(url, "head")
        problems = verify_schema(url)
    if problems:
        print("migrations DO NOT match the models:")
        for problem in problems:
            print(" -", problem)
        return 1
    print("migrations match the models ✓")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="manage_db", description="SUPERVOID Publishing database migrations"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("current", help="print current revision").set_defaults(
        func=_cmd_current
    )
    p_up = sub.add_parser("upgrade", help="upgrade (default: head)")
    p_up.add_argument("revision", nargs="?", default="head")
    p_up.set_defaults(func=_cmd_upgrade)
    p_dn = sub.add_parser("downgrade", help="downgrade (default: -1)")
    p_dn.add_argument("revision", nargs="?", default="-1")
    p_dn.set_defaults(func=_cmd_downgrade)
    p_st = sub.add_parser("stamp", help="stamp a revision without DDL (default: head)")
    p_st.add_argument("revision", nargs="?", default="head")
    p_st.set_defaults(func=_cmd_stamp)
    sub.add_parser("ensure", help="non-destructive adopt/upgrade/create").set_defaults(
        func=_cmd_ensure
    )
    sub.add_parser("history", help="show migration history").set_defaults(
        func=_cmd_history
    )
    sub.add_parser("verify", help="structural check: configured DB vs models").set_defaults(
        func=_cmd_verify
    )
    sub.add_parser("check", help="CI: migrations build a schema matching the models").set_defaults(
        func=_cmd_check
    )

    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
