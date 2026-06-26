#!/usr/bin/env python3
"""SUPERVOID Brain — state-compiler CLI.

Run from ``backend/`` with the virtualenv active:

    python scripts/brain_compiler.py compile-studio [--full]
    python scripts/brain_compiler.py compile-project --work-id ID  [--full]
    python scripts/brain_compiler.py compile-project --world-id ID [--full]
    python scripts/brain_compiler.py compile-stale [--batch N]   # one pass, exit
    python scripts/brain_compiler.py rebuild-all                  # full DR rebuild
    python scripts/brain_compiler.py verify                       # incremental==full
    python scripts/brain_compiler.py health                       # compiler health
    python scripts/brain_compiler.py worker [--interval S]        # drain + compile loop

Builds the ready-to-use studio / project mental state deterministically from the
database — no Redis/Kafka/cloud, PostgreSQL/SQLite + the existing app only. The
``worker`` runs the staleness consumer (drain) then compiles stale states.
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path

# Make the app importable regardless of CWD.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlmodel import Session, select  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import engine  # noqa: E402
from app.models.brain import ProjectBrainState  # noqa: E402
from app.services import brain  # noqa: E402
from app.services.brain import compiler  # noqa: E402
from app.utils.logging import configure_logging, get_logger  # noqa: E402

log = get_logger("app.brain.compiler")

_STOP = False


def _install_signal_handlers() -> None:
    def _handle(signum, _frame):
        global _STOP
        _STOP = True
        log.info("brain-compiler worker: signal %s, stopping after this pass", signum)

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)


def cmd_compile_studio(args) -> int:
    with Session(engine) as session:
        result = brain.compile_studio(session, full=args.full)
    print(json.dumps(result, indent=2))
    return 0


def cmd_compile_project(args) -> int:
    if bool(args.work_id) == bool(args.world_id):
        print("error: pass exactly one of --work-id / --world-id", file=sys.stderr)
        return 2
    with Session(engine) as session:
        result = brain.compile_project(
            session, work_id=args.work_id, story_world_id=args.world_id, full=args.full
        )
    print(json.dumps(result, indent=2))
    return 0


def cmd_compile_stale(args) -> int:
    with Session(engine) as session:
        result = brain.compile_stale(session, batch=args.batch)
    log.info(
        "brain-compiler compile-stale: studio=%s projects=%d failed=%d",
        bool(result.get("studio")), len(result.get("projects", [])), len(result.get("failed", [])),
    )
    print(json.dumps(result, indent=2))
    return 0 if not result.get("failed") else 1


def _all_project_scopes(session: Session) -> list[tuple]:
    rows = session.exec(select(ProjectBrainState).order_by(ProjectBrainState.id)).all()
    return [(r.work_id, r.story_world_id) for r in rows]


def cmd_rebuild_all(_args) -> int:
    """Full deterministic rebuild of studio + every existing project state."""
    out = {"studio": None, "projects": []}
    with Session(engine) as session:
        out["studio"] = brain.compile_studio(session, full=True)
        scopes = _all_project_scopes(session)
    for work_id, world_id in scopes:
        with Session(engine) as session:
            out["projects"].append(
                brain.compile_project(
                    session, work_id=work_id, story_world_id=world_id, full=True
                )
            )
    print(json.dumps(out, indent=2))
    return 0


def cmd_verify(_args) -> int:
    """Recompute each state two ways at one high-water mark — a fresh full build
    and the current incremental state — and assert the checksums match."""
    mismatches = []
    with Session(engine) as session:
        to_seq = compiler.head_sequence(session)
        studio = brain.get_studio_state(session)
        if studio is not None:
            full = brain.compile_studio(session, full=True, to_seq=to_seq, commit=False)
            if full["checksum"] != studio.checksum:
                mismatches.append({"scope": "studio", "stored": studio.checksum, "full": full["checksum"]})
            session.rollback()
        for work_id, world_id in _all_project_scopes(session):
            state = brain.get_project_state(session, work_id=work_id, story_world_id=world_id)
            full = brain.compile_project(
                session, work_id=work_id, story_world_id=world_id,
                full=True, to_seq=to_seq, commit=False,
            )
            if state is not None and full["checksum"] != state.checksum:
                mismatches.append({
                    "scope": "project", "ref": work_id or world_id,
                    "stored": state.checksum, "full": full["checksum"],
                })
            session.rollback()
    print(json.dumps({"to_seq": to_seq, "mismatches": mismatches}, indent=2))
    return 0 if not mismatches else 1


def cmd_health(_args) -> int:
    with Session(engine) as session:
        print(json.dumps(brain.compiler_health(session), indent=2, default=str))
    return 0


def cmd_worker(args) -> int:
    interval = args.interval if args.interval is not None else settings.brain_worker_interval
    _install_signal_handlers()
    log.info("brain-compiler worker: starting (interval=%.1fs)", interval)
    while not _STOP:
        try:
            with Session(engine) as session:
                brain.drain(session)          # consume events → flag stale
            with Session(engine) as session:
                result = brain.compile_stale(session)
            if result.get("studio") or result.get("projects") or result.get("failed"):
                log.info(
                    "brain-compiler worker: studio=%s projects=%d failed=%d",
                    bool(result.get("studio")), len(result.get("projects", [])),
                    len(result.get("failed", [])),
                )
        except Exception:  # keep the worker alive across transient errors
            log.exception("brain-compiler worker: pass failed")
        slept = 0.0
        while slept < interval and not _STOP:
            time.sleep(min(0.25, interval - slept))
            slept += 0.25
    log.info("brain-compiler worker: stopped")
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="brain_compiler", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_studio = sub.add_parser("compile-studio", help="compile the studio state")
    p_studio.add_argument("--full", action="store_true", help="full rebuild")
    p_studio.set_defaults(func=cmd_compile_studio)

    p_proj = sub.add_parser("compile-project", help="compile one project state")
    p_proj.add_argument("--work-id", dest="work_id", default=None)
    p_proj.add_argument("--world-id", dest="world_id", default=None)
    p_proj.add_argument("--full", action="store_true", help="full rebuild")
    p_proj.set_defaults(func=cmd_compile_project)

    p_stale = sub.add_parser("compile-stale", help="compile every stale state, then exit")
    p_stale.add_argument("--batch", type=int, default=None)
    p_stale.set_defaults(func=cmd_compile_stale)

    sub.add_parser("rebuild-all", help="full rebuild of studio + all projects (DR)").set_defaults(func=cmd_rebuild_all)
    sub.add_parser("verify", help="assert incremental state == full rebuild checksums").set_defaults(func=cmd_verify)
    sub.add_parser("health", help="print compiler health").set_defaults(func=cmd_health)

    p_worker = sub.add_parser("worker", help="loop: drain events + compile stale")
    p_worker.add_argument("--interval", type=float, default=None, help="poll interval seconds")
    p_worker.set_defaults(func=cmd_worker)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
