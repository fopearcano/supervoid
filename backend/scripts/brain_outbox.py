#!/usr/bin/env python3
"""SUPERVOID Brain — event-outbox CLI.

Run from ``backend/`` with the virtualenv active:

    python scripts/brain_outbox.py status        # monitoring snapshot
    python scripts/brain_outbox.py run-once       # deterministic: drain backlog, exit
    python scripts/brain_outbox.py worker          # background loop (drain, sleep, repeat)
    python scripts/brain_outbox.py reconcile       # detect + re-flag missed changes
    python scripts/brain_outbox.py replay [IDS...]  # re-queue dead-lettered events

Uses PostgreSQL/SQLite + the existing application — no Redis/Kafka/cloud.
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

from sqlmodel import Session  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import engine  # noqa: E402
from app.services import brain  # noqa: E402
from app.utils.logging import configure_logging, get_logger  # noqa: E402

log = get_logger("app.brain.outbox")

_STOP = False


def _install_signal_handlers() -> None:
    def _handle(signum, _frame):
        global _STOP
        _STOP = True
        log.info("brain-outbox worker: received signal %s, stopping after this pass", signum)

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)


def cmd_status(_args) -> int:
    with Session(engine) as session:
        print(json.dumps(brain.outbox_status(session), indent=2))
    return 0


def cmd_run_once(_args) -> int:
    with Session(engine) as session:
        result = brain.drain(session)
    log.info("brain-outbox run-once: %s", result)
    print(json.dumps(result, indent=2))
    return 0


def cmd_reconcile(_args) -> int:
    with Session(engine) as session:
        result = brain.reconcile(session)
    log.info("brain-outbox reconcile: %s", result)
    print(json.dumps(result, indent=2))
    return 0


def cmd_replay(args) -> int:
    with Session(engine) as session:
        requeued = brain.replay_failed(session, event_ids=args.ids or None)
    log.info("brain-outbox replay: requeued %d dead-lettered event(s)", requeued)
    print(json.dumps({"requeued": requeued}, indent=2))
    return 0


def cmd_worker(args) -> int:
    interval = args.interval if args.interval is not None else settings.brain_worker_interval
    _install_signal_handlers()
    log.info("brain-outbox worker: starting (interval=%.1fs)", interval)
    while not _STOP:
        try:
            with Session(engine) as session:
                result = brain.drain(session)
            if result["processed"] or result["failed"]:
                log.info("brain-outbox worker: %s", result)
        except Exception:  # keep the worker alive across transient errors
            log.exception("brain-outbox worker: pass failed")
        # Sleep in short slices so signals are honoured promptly.
        slept = 0.0
        while slept < interval and not _STOP:
            time.sleep(min(0.25, interval - slept))
            slept += 0.25
    log.info("brain-outbox worker: stopped")
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="brain_outbox", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="print a monitoring snapshot").set_defaults(func=cmd_status)
    sub.add_parser("run-once", help="drain the current backlog and exit").set_defaults(func=cmd_run_once)
    sub.add_parser("reconcile", help="detect + re-flag missed changes").set_defaults(func=cmd_reconcile)

    p_replay = sub.add_parser("replay", help="re-queue dead-lettered events")
    p_replay.add_argument("ids", nargs="*", help="event ids (default: all FAILED)")
    p_replay.set_defaults(func=cmd_replay)

    p_worker = sub.add_parser("worker", help="run the background worker loop")
    p_worker.add_argument("--interval", type=float, default=None, help="poll interval seconds")
    p_worker.set_defaults(func=cmd_worker)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
