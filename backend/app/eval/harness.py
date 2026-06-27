"""The evaluation harness orchestrator (Prompt 17).

Runs the versioned corpus against whatever provider is configured — the
**dry-run** provider offline, or the **configured vLLM** when
``ai_provider=vllm`` — so candidate models are compared through configuration,
never code changes. Aggregates deterministic scores + benchmark metrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session

from app.config import settings
from app.eval.corpus import ALL_DIMENSIONS, CORPUS, CORPUS_VERSION
from app.eval.runners import run_case
from app.eval.scoring import CaseResult, score_case
from app.eval.world import build_world
from app.services.ai.providers import get_provider


@dataclass
class CorpusResult:
    corpus_version: str
    provider: str
    model: str
    is_live: bool
    cases: list[CaseResult] = field(default_factory=list)
    aggregate: dict = field(default_factory=dict)


def _aggregate(cases: list[CaseResult]) -> dict:
    n = len(cases) or 1
    passed = sum(1 for c in cases if c.passed)
    dim_totals: dict[str, list[int]] = {d: [0, 0] for d in ALL_DIMENSIONS}
    for c in cases:
        for d in c.dims:
            dim_totals[d.dimension][1] += 1
            if d.passed:
                dim_totals[d.dimension][0] += 1
    dim_rates = {
        d: round(tot[0] / tot[1], 4) for d, tot in dim_totals.items() if tot[1] > 0
    }

    def _avg(key):
        vals = [c.benchmark.get(key) for c in cases if c.benchmark.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    cache_vals = [c.benchmark.get("cache_eligible") for c in cases if c.benchmark.get("cache_eligible") is not None]
    return {
        "cases": len(cases),
        "passed": passed,
        "pass_rate": round(passed / n, 4),
        "mean_score": round(sum(c.score for c in cases) / n, 4),
        "dimension_pass_rates": dim_rates,
        "benchmark": {
            "latency_ms_avg": _avg("latency_ms"),
            "prompt_tokens_avg": _avg("prompt_tokens"),
            "completion_tokens_avg": _avg("completion_tokens"),
            "retrieval_count_avg": _avg("retrieval_count"),
            "stable_prefix_tokens_avg": _avg("stable_prefix_tokens"),
            "cache_eligible_rate": (round(sum(1 for v in cache_vals if v) / len(cache_vals), 4)
                                    if cache_vals else None),
        },
    }


def run_corpus(session: Session, *, provider=None) -> CorpusResult:
    provider = provider or get_provider()
    world = build_world(session)
    cases: list[CaseResult] = []
    for case in CORPUS:
        obs = run_case(session, case, world, provider=provider)
        cases.append(score_case(case, obs))
    return CorpusResult(
        corpus_version=CORPUS_VERSION, provider=provider.name, model=settings.ai_model,
        is_live=provider.name != "dry_run", cases=cases, aggregate=_aggregate(cases),
    )
