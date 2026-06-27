#!/usr/bin/env python3
"""SUPERVOID Brain — evaluation harness CLI (Prompt 17).

Run from ``backend/`` with the virtualenv active:

    python scripts/run_eval.py run                       # vs the CONFIGURED provider
    python scripts/run_eval.py run --out-dir eval-reports # choose the output dir
    python scripts/run_eval.py run --json r.json --md r.md
    python scripts/run_eval.py list                      # print the corpus (no run)

The harness runs the versioned corpus against whatever provider is configured —
the offline **dry-run** provider, or the **configured vLLM** when
``ai_provider=vllm`` — so candidate models are compared through CONFIGURATION,
never code changes. A production default model is recommended ONLY from a live
provider's real SUPERVOID task results; a dry-run run validates the harness and
the governed surfaces but is explicitly NOT a basis for a model decision.

The evaluation always runs against a fresh, **throwaway** in-memory database
seeded by the eval world builder — it never reads or writes the real SUPERVOID
database.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make the app importable regardless of CWD.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from app.config import settings  # noqa: E402
from app.eval.corpus import CORPUS, CORPUS_VERSION  # noqa: E402
from app.eval.harness import run_corpus  # noqa: E402
from app.eval.report import build_report, to_markdown  # noqa: E402
from app.utils.logging import configure_logging, get_logger  # noqa: E402

log = get_logger("app.brain.eval")


def _throwaway_session() -> Session:
    """A fresh in-memory SQLite DB so the eval never touches the real database."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    # Import the model package so every table is registered before create_all.
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _default_paths(out_dir: Path, provider_hint: str) -> tuple[Path, Path]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = f"eval_{CORPUS_VERSION}_{provider_hint}_{stamp}"
    return out_dir / f"{base}.json", out_dir / f"{base}.md"


def cmd_run(args) -> int:
    provider_hint = "vllm" if settings.ai_provider == "vllm" else "dry_run"
    with _throwaway_session() as session:
        result = run_corpus(session)
    report = build_report(result, generated_at=datetime.now(timezone.utc).isoformat())

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = Path(args.json) if args.json else None
    md_path = Path(args.md) if args.md else None
    if json_path is None or md_path is None:
        dflt_json, dflt_md = _default_paths(out_dir, result.provider)
        json_path = json_path or dflt_json
        md_path = md_path or dflt_md

    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(to_markdown(report), encoding="utf-8")

    agg = result.aggregate
    rec = report["recommendation"]
    log.info("eval: %s — %s/%s passed (provider=%s live=%s)",
             CORPUS_VERSION, agg["passed"], agg["cases"], result.provider, result.is_live)
    print(f"SUPERVOID evaluation — {CORPUS_VERSION}")
    print(f"  provider : {result.provider} (live={result.is_live}, model={result.model})")
    print(f"  pass rate: {agg['passed']}/{agg['cases']} ({agg['pass_rate']}) · "
          f"mean score {agg['mean_score']}")
    print(f"  dimensions: {agg['dimension_pass_rates']}")
    print(f"  benchmark : {agg['benchmark']}")
    if not args.quiet:
        print("  cases:")
        for c in report["cases"]:
            mark = "PASS" if c["passed"] else "FAIL"
            fails = [d["dimension"] for d in c["dims"] if not d["passed"]]
            extra = f" fails={fails}" if fails else ""
            print(f"    [{mark}] {c['case_id']:28s} score={c['score']}{extra}")
    print(f"  recommendation: {rec['recommended_model'] or '(none — ' + rec['basis'] + ')'}")
    print(f"  → {json_path}")
    print(f"  → {md_path}")
    # A non-zero exit when deterministic checks regress, so CI can gate on it.
    return 0 if agg["pass_rate"] >= 1.0 else 1


def cmd_list(_args) -> int:
    print(f"SUPERVOID evaluation corpus — {CORPUS_VERSION} ({len(CORPUS)} cases)")
    for c in CORPUS:
        print(f"  {c.id:28s} {c.kind.value:28s} user={c.user:9s} "
              f"approval={c.expected_approval}")
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="run_eval", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run the corpus vs the configured provider")
    p_run.add_argument("--out-dir", default="eval-reports", help="report output directory")
    p_run.add_argument("--json", default=None, help="explicit JSON report path")
    p_run.add_argument("--md", default=None, help="explicit markdown report path")
    p_run.add_argument("--quiet", action="store_true", help="omit the per-case table")
    p_run.set_defaults(func=cmd_run)

    sub.add_parser("list", help="print the corpus and exit").set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
