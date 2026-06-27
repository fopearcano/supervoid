"""Tests for the SUPERVOID evaluation harness (Prompt 17).

These verify the harness itself: the corpus is versioned and every case records
the required fields; the deterministic checks (schema, tools, permissions,
citations, approval, correctness) pass against the well-behaved seed via the
dry-run provider; refusal/permission/approval/citation/injection cases score the
way the rubric intends; benchmark metrics are recorded; and the report only
recommends a default model from a LIVE provider's results.
"""
from __future__ import annotations

import pytest
from sqlmodel import Session

from app.eval.corpus import (
    ALL_DIMENSIONS,
    APPROVAL_NONE,
    APPROVAL_PROPOSAL,
    APPROVAL_REQUIRED,
    CORPUS,
    CORPUS_VERSION,
    EvalKind,
    by_kind,
)
from app.eval.harness import CorpusResult, run_corpus
from app.eval.report import build_report, recommend_default, to_markdown
from app.eval.runners import run_case
from app.eval.scoring import score_case
from app.eval.world import MALICIOUS_MEMO, build_world


# --- the corpus is versioned and complete ----------------------------------
def test_corpus_is_versioned_and_covers_every_kind():
    assert CORPUS_VERSION == "eval-v1"
    assert len(CORPUS) == 15
    # Every required SUPERVOID scenario has at least one case.
    kinds = {c.kind for c in CORPUS}
    assert kinds == set(EvalKind)
    # Case ids are unique.
    ids = [c.id for c in CORPUS]
    assert len(ids) == len(set(ids))


_VALID_APPROVALS = {APPROVAL_NONE, APPROVAL_PROPOSAL, APPROVAL_REQUIRED}


@pytest.mark.parametrize("case", CORPUS, ids=[c.id for c in CORPUS])
def test_every_case_records_the_required_fields(case):
    # input; user identity; project; expected state version; expected tools;
    # forbidden tools; expected evidence; expected approval behaviour; rubric.
    assert case.input and isinstance(case.input, str)
    assert case.user in {"admin", "owner", "editor", "outsider"}
    assert case.project is None or isinstance(case.project, str)
    assert case.expected_state_version == "current"
    assert isinstance(case.expected_tools, list)
    assert isinstance(case.forbidden_tools, list)
    assert isinstance(case.expected_evidence, list)
    assert case.expected_approval in _VALID_APPROVALS
    assert isinstance(case.expects_refusal, bool)
    assert case.rubric and all(d in ALL_DIMENSIONS for d in case.rubric)


def test_by_kind_resolves_each_kind():
    for kind in EvalKind:
        assert by_kind(kind).kind == kind


# --- the well-behaved seed passes every deterministic check ----------------
@pytest.fixture()
def corpus_result(session: Session) -> CorpusResult:
    return run_corpus(session)


def test_dry_run_passes_all_deterministic_checks(corpus_result: CorpusResult):
    agg = corpus_result.aggregate
    assert agg["cases"] == 15
    assert agg["passed"] == 15
    assert agg["pass_rate"] == 1.0
    # Each deterministic dimension is fully green for the well-behaved seed.
    for dim, rate in agg["dimension_pass_rates"].items():
        assert rate == 1.0, f"dimension {dim} regressed: {rate}"
    # Dry-run is offline and therefore NOT a basis for a model decision.
    assert corpus_result.is_live is False
    assert corpus_result.provider == "dry_run"


def test_benchmark_metrics_are_recorded(corpus_result: CorpusResult):
    bm = corpus_result.aggregate["benchmark"]
    # latency, tokens, retrieval count, stable-prefix size, cache eligibility.
    assert bm["latency_ms_avg"] is not None
    assert bm["prompt_tokens_avg"] and bm["prompt_tokens_avg"] > 0
    assert bm["completion_tokens_avg"] and bm["completion_tokens_avg"] > 0
    assert bm["retrieval_count_avg"] is not None
    assert bm["stable_prefix_tokens_avg"] and bm["stable_prefix_tokens_avg"] > 0
    # Every assembled prefix is cacheable (stable across re-assembly).
    assert bm["cache_eligible_rate"] == 1.0
    # Each case carries its own benchmark row.
    for c in corpus_result.cases:
        assert "latency_ms" in c.benchmark
        assert "stable_prefix_tokens" in c.benchmark


# --- specific governed behaviours score the way the rubric intends ---------
def _result_for(corpus_result: CorpusResult, case_id: str):
    return next(c for c in corpus_result.cases if c.case_id == case_id)


def _dim(case_result, dimension: str):
    return next(d for d in case_result.dims if d.dimension == dimension)


def test_refusal_case_scores_a_refusal(session: Session):
    world = build_world(session)
    case = by_kind(EvalKind.REFUSE_UNAUTHORISED)
    obs = run_case(session, case, world)
    # The outsider has no membership: the governed surface must refuse.
    assert obs.refused is True
    assert obs.correct is True
    result = score_case(case, obs)
    assert result.passed and _dim(result, "permissions").passed


def test_permission_case_admits_an_authorised_member(session: Session):
    world = build_world(session)
    case = by_kind(EvalKind.RESPECT_PERMISSIONS)
    obs = run_case(session, case, world)
    assert obs.refused is False  # the owner is authorised
    assert _dim(score_case(case, obs), "permissions").passed


def test_task_proposal_is_gated_not_mutated(session: Session):
    world = build_world(session)
    case = by_kind(EvalKind.CREATE_TASK_PROPOSAL)
    assert case.expected_approval == APPROVAL_PROPOSAL
    obs = run_case(session, case, world)
    assert obs.proposal_created is True
    assert obs.direct_mutation is False
    assert _dim(score_case(case, obs), "approval").passed


def test_publication_requires_approval(session: Session):
    world = build_world(session)
    case = by_kind(EvalKind.REQUIRE_APPROVAL_PUBLICATION)
    assert case.expected_approval == APPROVAL_REQUIRED
    obs = run_case(session, case, world)
    # Either a gated proposal is created or the action is refused for lacking the
    # publish scope — both are a correct approval gate, never a direct mutation.
    assert obs.approval_required is True
    assert obs.direct_mutation is False
    assert _dim(score_case(case, obs), "approval").passed


def test_citation_cases_return_the_expected_evidence(session: Session):
    world = build_world(session)
    for kind, expected in (
        (EvalKind.EXPLAIN_DECISION, "decision_rationale"),
        (EvalKind.COMPARE_PANEL_SHOT, "panel_description"),
    ):
        case = by_kind(kind)
        obs = run_case(session, case, world)
        assert expected in obs.citations
        assert _dim(score_case(case, obs), "citations").passed


def test_prompt_injection_is_fenced_and_no_tool_fires(session: Session):
    world = build_world(session)
    case = by_kind(EvalKind.PROMPT_INJECTION)
    obs = run_case(session, case, world)
    # The malicious memo comes back ONLY as fenced evidence; no forbidden tool
    # is executed by the eval flow.
    assert obs.evidence_fenced is True
    assert obs.forbidden_attempted == []
    assert obs.correct is True
    assert score_case(case, obs).passed


def test_avoid_retrieval_answers_from_state_without_retrieving(session: Session):
    world = build_world(session)
    case = by_kind(EvalKind.AVOID_RETRIEVAL)
    obs = run_case(session, case, world)
    assert obs.tools_used == ["get_project_state"]
    assert obs.retrieval_count == 0
    assert obs.correct is True


def test_correct_mcp_tool_uses_a_read_not_a_write(session: Session):
    world = build_world(session)
    case = by_kind(EvalKind.CORRECT_MCP_TOOL)
    obs = run_case(session, case, world)
    assert "get_recent_decisions" in obs.tools_used
    assert not any(t in obs.forbidden_attempted for t in case.forbidden_tools)
    assert _dim(score_case(case, obs), "tools").passed


# --- the eval drives the REAL governed surfaces (regression) ---------------
def test_owner_can_inspect_private_project_asset_provenance(session: Session):
    """Regression: a project owner reading a PRIVATE project asset's provenance
    must fall through to the VIEW_PROJECT check, not crash on visibility."""
    world = build_world(session)
    case = by_kind(EvalKind.ASSET_PROVENANCE)
    obs = run_case(session, case, world)
    assert obs.refused is False
    assert "inspect_provenance" in obs.tools_used
    assert obs.correct is True  # the seeded version has incomplete provenance


def test_world_seeds_the_malicious_document(session: Session):
    world = build_world(session)
    assert "malicious" in world.docs
    assert "IGNORE ALL PREVIOUS INSTRUCTIONS" in MALICIOUS_MEMO


# --- the report only recommends a model from LIVE results ------------------
def test_dry_run_report_recommends_no_model(corpus_result: CorpusResult):
    report = build_report(corpus_result, generated_at="2026-06-27T00:00:00Z")
    rec = report["recommendation"]
    assert rec["recommended_model"] is None
    assert rec["basis"] == "dry_run"
    assert report["corpus_version"] == CORPUS_VERSION
    assert len(report["cases"]) == 15
    # The markdown renders without error and carries the headline numbers.
    md = to_markdown(report)
    assert "SUPERVOID evaluation report" in md
    assert "Recommendation" in md


def test_live_recommendation_is_gated_on_deterministic_pass(corpus_result: CorpusResult):
    # Simulate a LIVE provider with passing deterministic checks → recommend.
    live = CorpusResult(
        corpus_version=corpus_result.corpus_version, provider="vllm",
        model="my-candidate-7b", is_live=True, cases=corpus_result.cases,
        aggregate=corpus_result.aggregate,
    )
    rec = recommend_default(live)
    assert rec["basis"] == "live_supervoid_tasks"
    assert rec["recommended_model"] == "my-candidate-7b"


def test_live_recommendation_withheld_when_checks_fail():
    # A LIVE provider whose deterministic checks are below threshold → no rec.
    weak = CorpusResult(
        corpus_version=CORPUS_VERSION, provider="vllm", model="weak-model",
        is_live=True, cases=[],
        aggregate={
            "cases": 15, "passed": 5, "pass_rate": 0.33,
            "mean_score": 0.4, "dimension_pass_rates": {"correctness": 0.33},
            "benchmark": {"latency_ms_avg": 12.0},
        },
    )
    rec = recommend_default(weak)
    assert rec["recommended_model"] is None
    assert rec["basis"] == "live_supervoid_tasks"
