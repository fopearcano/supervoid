"""Evaluation report + model recommendation (Prompt 17).

A production default model is recommended ONLY from real SUPERVOID task results
against a live provider. A dry-run run validates the harness and the governed
surfaces but is explicitly NOT a basis for a model decision.
"""
from __future__ import annotations

from typing import Optional

from app.eval.harness import CorpusResult
from app.eval.scoring import case_result_dict


def recommend_default(result: CorpusResult) -> dict:
    agg = result.aggregate
    if not result.is_live:
        return {
            "recommended_model": None,
            "basis": "dry_run",
            "summary": (
                "Results are from the offline dry-run provider. They validate the "
                "evaluation harness and the governed surfaces (permissions, citations, "
                "approval gates, injection fencing), but they are NOT a basis for a "
                "production model decision. Re-run against the configured vLLM "
                "(ai_provider=vllm) to choose a default from real SUPERVOID task results."
            ),
        }
    deterministic_ok = agg["dimension_pass_rates"].get("correctness", 0) >= 0.9 and agg["pass_rate"] >= 0.9
    return {
        "recommended_model": result.model if deterministic_ok else None,
        "basis": "live_supervoid_tasks",
        "summary": (
            f"Model '{result.model}' (provider '{result.provider}') passed "
            f"{agg['passed']}/{agg['cases']} SUPERVOID task cases "
            f"(correctness {agg['dimension_pass_rates'].get('correctness')}, "
            f"avg latency {agg['benchmark'].get('latency_ms_avg')} ms). "
            + ("Recommended as the default." if deterministic_ok else
               "NOT recommended — deterministic checks below threshold; investigate failures.")
        ),
    }


def build_report(result: CorpusResult, *, generated_at: Optional[str] = None) -> dict:
    return {
        "corpus_version": result.corpus_version,
        "provider": result.provider,
        "model": result.model,
        "is_live": result.is_live,
        "generated_at": generated_at,
        "aggregate": result.aggregate,
        "recommendation": recommend_default(result),
        "cases": [case_result_dict(c) for c in result.cases],
    }


def to_markdown(report: dict) -> str:
    agg = report["aggregate"]
    bm = agg.get("benchmark", {})
    lines = [
        f"# SUPERVOID evaluation report — {report['corpus_version']}",
        "",
        f"- Provider: **{report['provider']}** · model: **{report['model']}** · "
        f"live: **{report['is_live']}**",
        f"- Generated: {report.get('generated_at') or 'n/a'}",
        f"- Pass rate: **{agg['passed']}/{agg['cases']}** ({agg['pass_rate']}) · "
        f"mean score {agg['mean_score']}",
        "",
        "## Recommendation",
        "",
        report["recommendation"]["summary"],
        "",
        "## Deterministic dimensions",
        "",
        "| dimension | pass rate |",
        "| --- | --- |",
    ]
    for dim, rate in agg["dimension_pass_rates"].items():
        lines.append(f"| {dim} | {rate} |")
    lines += [
        "",
        "## Benchmark (averages)",
        "",
        f"- latency: {bm.get('latency_ms_avg')} ms",
        f"- prompt tokens: {bm.get('prompt_tokens_avg')} · completion tokens: {bm.get('completion_tokens_avg')}",
        f"- retrieval count: {bm.get('retrieval_count_avg')} · stable-prefix tokens: {bm.get('stable_prefix_tokens_avg')}",
        f"- cache-eligible rate: {bm.get('cache_eligible_rate')}",
        "",
        "## Cases",
        "",
        "| case | kind | passed | score | correct |",
        "| --- | --- | --- | --- | --- |",
    ]
    for c in report["cases"]:
        lines.append(
            f"| {c['case_id']} | {c['kind']} | {'✓' if c['passed'] else '✗'} | "
            f"{c['score']} | {c['benchmark'].get('correct')} |"
        )
    return "\n".join(lines) + "\n"
