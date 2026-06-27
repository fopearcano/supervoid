"""Tests for the optional fine-tuning data pipeline (Prompt 18).

The pipeline is PREPARED, never auto-run. These verify: sanitisation + the
exclusion rules; the review workflow (only approved examples export); versioned
JSONL export with a train/val split by project + category; the adapter registry's
required fields; and — the core guard — that an adapter is deployable ONLY when it
beats the base on the project evaluation without weakening permissions or approval
behaviour, with rollback returning to the base model.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session

from app.config import settings
from app.models.enums import AdapterStatus, TuningCandidateStatus, TuningExampleKind
from app.services import tuning
from app.services.tuning.errors import TuningDeployBlocked, TuningExclusion


# --- sanitisation + exclusion ----------------------------------------------
def test_sanitize_strips_cot_and_redacts_secrets():
    r = tuning.sanitize_example(
        [{"role": "user", "content": "How should I respond?"}],
        "The answer. <think>my private reasoning</think> token=sk-ABCDEFGHIJ1234567890",
    )
    assert r.ok
    assert "<think>" not in r.cleaned_target and "my private reasoning" not in r.cleaned_target
    assert "sk-" not in r.cleaned_target
    assert "chain_of_thought" in r.redactions
    assert r.contains_sensitive is True


def test_sanitize_blocks_private_contract_unless_approved_and_anonymised():
    raw = [{"role": "user", "content": "This Agreement, whereas the royalty rate is 12% of net receipts."}]
    blocked = tuning.sanitize_example(raw, "ok")
    assert blocked.ok is False
    assert any("contract" in r for r in blocked.blocked_reasons)
    # Allowed only when explicitly approved AND anonymised.
    allowed = tuning.sanitize_example(raw, "ok", allow_contract=True, anonymised=True)
    assert allowed.ok is True


def test_sanitize_blocks_member_data_unless_anonymised():
    raw = [{"role": "user", "content": "Email me at jane.doe@example.com about the page."}]
    assert tuning.sanitize_example(raw, "ok").ok is False
    assert tuning.sanitize_example(raw, "ok", anonymised=True).ok is True


def test_sanitize_flags_temporary_status_as_warning_not_block():
    r = tuning.sanitize_example(
        [{"role": "user", "content": "status: in_progress on chapter two"}], "noted"
    )
    assert r.ok is True
    assert any("temporary_status" in n for n in r.notes)


def test_propose_rejects_excluded_content(session: Session):
    with pytest.raises(TuningExclusion):
        tuning.propose_example(
            session, kind=TuningExampleKind.STRONG_RESPONSE,
            messages=[{"role": "user", "content": "see contract"}],
            target_output="This Agreement, whereas the grant of rights is worldwide.",
        )


def test_all_nine_collect_kinds_are_accepted(session: Session):
    for kind in TuningExampleKind:
        ex = tuning.propose_example(
            session, kind=kind,
            messages=[{"role": "user", "content": f"teach {kind.value}"}],
            target_output=f"behaviour for {kind.value}",
        )
        assert ex.status == TuningCandidateStatus.PENDING
    assert len(list(TuningExampleKind)) == 9


# --- review workflow -------------------------------------------------------
def test_only_approved_examples_are_exported(session: Session, tmp_path: Path, admin_user):
    approved, pending, rejected = [], None, None
    for i in range(12):
        ex = tuning.propose_example(
            session, kind=TuningExampleKind.TOOL_CHOICE,
            messages=[{"role": "user", "content": f"q{i}"}], target_output=f"a{i}",
            work_id="W1", task_category="general", created_by_id=admin_user.id,
        )
        tuning.approve_example(session, ex, reviewer_id=admin_user.id)
        approved.append(ex)
    pending = tuning.propose_example(
        session, kind=TuningExampleKind.TOOL_CHOICE,
        messages=[{"role": "user", "content": "pending"}], target_output="x")
    rejected = tuning.propose_example(
        session, kind=TuningExampleKind.TOOL_CHOICE,
        messages=[{"role": "user", "content": "bad"}], target_output="y")
    tuning.reject_example(session, rejected, reviewer_id=admin_user.id)
    session.commit()

    dataset = tuning.export_dataset(session, version="ft-v1", base_dir=tmp_path)
    assert dataset.example_count == 12              # only the approved ones
    assert pending.status == TuningCandidateStatus.PENDING
    assert rejected.status == TuningCandidateStatus.REJECTED
    # Exported examples are frozen.
    assert all(e.status == TuningCandidateStatus.EXPORTED for e in approved)
    assert all(e.dataset_version == "ft-v1" for e in approved)


def test_export_requires_minimum_examples(session: Session, tmp_path: Path):
    ex = tuning.propose_example(
        session, kind=TuningExampleKind.STRONG_RESPONSE,
        messages=[{"role": "user", "content": "q"}], target_output="a")
    tuning.approve_example(session, ex)
    session.commit()
    with pytest.raises(ValueError):
        tuning.export_dataset(session, version="too-small", base_dir=tmp_path)


def test_export_splits_by_project_and_category(session: Session, tmp_path: Path):
    # 3 examples in each of 4 (project, category) groups → 12 total.
    for project in ("W1", "W2"):
        for category in ("cat_a", "cat_b"):
            for i in range(3):
                ex = tuning.propose_example(
                    session, kind=TuningExampleKind.PRODUCTION_PLAN,
                    messages=[{"role": "user", "content": f"{project}-{category}-{i}"}],
                    target_output="plan", work_id=project, task_category=category)
                tuning.approve_example(session, ex)
    session.commit()

    dataset = tuning.export_dataset(session, version="ft-split", val_fraction=0.34, base_dir=tmp_path)
    assert dataset.train_count + dataset.val_count == 12
    assert dataset.val_count >= 4          # ≥1 from each of the 4 groups
    assert dataset.split_strategy == "project+category"
    # Both projects represented in train AND val on disk.
    train_lines = Path(dataset.train_path).read_text().splitlines()
    val_lines = Path(dataset.val_path).read_text().splitlines()
    assert len(train_lines) == dataset.train_count and len(val_lines) == dataset.val_count
    assert any('"project": "W1"' in ln for ln in train_lines)
    assert any('"project": "W2"' in ln for ln in val_lines)
    # The final assistant turn (the behaviour to teach) is present; no CoT.
    assert all('"role": "assistant"' in ln for ln in train_lines)


# --- adapter registry + deploy gate ----------------------------------------
_GOOD = {"pass_rate": 1.0, "mean_score": 1.0,
         "dimension_pass_rates": {"correctness": 1.0, "permissions": 1.0, "approval": 1.0}}
_BASE = {"pass_rate": 0.9, "mean_score": 0.9,
         "dimension_pass_rates": {"correctness": 0.9, "permissions": 1.0, "approval": 1.0}}


def test_adapter_registry_records_required_fields(session: Session):
    a = tuning.register_adapter(
        session, name="cand-7b", base_model="supervoid-brain", dataset_version="ft-v1",
        licence="apache-2.0", training_parameters={"method": "lora", "lora_rank": 8})
    assert a.base_model == "supervoid-brain"
    assert a.dataset_version == "ft-v1"
    assert a.licence == "apache-2.0"
    assert a.training_parameters["lora_rank"] == 8
    assert a.status == AdapterStatus.REGISTERED
    assert a.evaluation_results == {}
    # Default training parameters are recorded when not supplied.
    b = tuning.register_adapter(session, name="defaults")
    assert b.training_parameters["method"] == "lora"
    assert b.base_model == settings.tuning_default_base_model


def test_deploy_blocked_when_not_beating_base(session: Session):
    a = tuning.register_adapter(session, name="same")
    tuning.record_evaluation(session, a, base_aggregate=_GOOD, adapter_aggregate=_GOOD)
    assert a.beats_base is False
    ok, reason = tuning.deploy_gate(a)
    assert ok is False and "beat" in reason
    with pytest.raises(TuningDeployBlocked):
        tuning.approve_adapter(session, a)


def test_deploy_blocked_when_weakening_permissions(session: Session):
    weak = {"pass_rate": 1.0, "mean_score": 1.0,
            "dimension_pass_rates": {"correctness": 1.0, "permissions": 0.8, "approval": 1.0}}
    a = tuning.register_adapter(session, name="weak-perms")
    tuning.record_evaluation(session, a, base_aggregate=_BASE, adapter_aggregate=weak)
    assert a.permissions_preserved is False
    ok, reason = tuning.deploy_gate(a)
    assert ok is False and "permission" in reason


def test_deploy_blocked_when_weakening_approval(session: Session):
    weak = {"pass_rate": 1.0, "mean_score": 1.0,
            "dimension_pass_rates": {"correctness": 1.0, "permissions": 1.0, "approval": 0.7}}
    a = tuning.register_adapter(session, name="weak-approval")
    tuning.record_evaluation(session, a, base_aggregate=_BASE, adapter_aggregate=weak)
    assert a.approval_preserved is False
    assert tuning.deploy_gate(a)[0] is False


def test_deploy_and_rollback_to_base(session: Session, admin_user):
    a = tuning.register_adapter(session, name="winner")
    tuning.record_evaluation(session, a, base_aggregate=_BASE, adapter_aggregate=_GOOD)
    assert a.beats_base and a.permissions_preserved and a.approval_preserved
    tuning.approve_adapter(session, a, approver_id=admin_user.id)
    tuning.deploy_adapter(session, a, actor_id=admin_user.id)
    assert a.status == AdapterStatus.DEPLOYED
    assert tuning.active_adapter(session).id == a.id

    rolled = tuning.rollback_to_base(session, actor_id=admin_user.id)
    assert rolled.id == a.id and rolled.status == AdapterStatus.ROLLED_BACK
    assert tuning.active_adapter(session) is None         # back to base


def test_only_one_adapter_deployed_at_a_time(session: Session, admin_user):
    a = tuning.register_adapter(session, name="first")
    b = tuning.register_adapter(session, name="second")
    for ad in (a, b):
        tuning.record_evaluation(session, ad, base_aggregate=_BASE, adapter_aggregate=_GOOD)
        tuning.approve_adapter(session, ad, approver_id=admin_user.id)
    tuning.deploy_adapter(session, a, actor_id=admin_user.id)
    tuning.deploy_adapter(session, b, actor_id=admin_user.id)
    assert tuning.active_adapter(session).id == b.id
    assert a.status == AdapterStatus.ROLLED_BACK


def test_evaluate_against_corpus_dry_run_keeps_deploy_blocked(session: Session):
    """The safe default: with no real adapter, base == adapter on the project
    corpus, so the adapter does not beat base and deployment stays blocked."""
    a = tuning.register_adapter(session, name="offline")
    tuning.evaluate_adapter(session, a)
    assert a.status == AdapterStatus.EVALUATED
    assert a.evaluation_results["adapter"]["pass_rate"] == a.evaluation_results["base"]["pass_rate"]
    assert a.beats_base is False
    assert tuning.deploy_gate(a)[0] is False


def test_vllm_lora_config_shape(session: Session, admin_user):
    # Base model when nothing is deployed.
    base_cfg = tuning.vllm_lora_config(session)
    assert base_cfg["enable_lora"] is False and base_cfg["lora_modules"] == []

    a = tuning.register_adapter(session, name="lora-x", artifact_ref="/opt/brain/adapters/lora-x")
    tuning.record_evaluation(session, a, base_aggregate=_BASE, adapter_aggregate=_GOOD)
    tuning.approve_adapter(session, a, approver_id=admin_user.id)
    tuning.deploy_adapter(session, a, actor_id=admin_user.id)
    cfg = tuning.vllm_lora_config(session)
    assert cfg["enable_lora"] is True
    assert cfg["lora_modules"] == [{"name": "lora-x", "path": "/opt/brain/adapters/lora-x"}]
    assert "--enable-lora" in cfg["cli"] and "lora-x=/opt/brain/adapters/lora-x" in cfg["cli"]
    assert cfg["env"]["VLLM_ENABLE_LORA"] == "1"


# --- HTTP surface (admin-only) ---------------------------------------------
def test_tuning_endpoints_are_admin_only(editor_client, anon_client):
    assert editor_client.get("/api/brain/tuning/adapters").status_code == 403
    assert anon_client.get("/api/brain/tuning/candidates").status_code in (401, 403)


def test_propose_gated_by_tuning_enabled(client, monkeypatch):
    payload = {"kind": "strong_response",
               "messages": [{"role": "user", "content": "hi"}], "target_output": "hello"}
    monkeypatch.setattr(settings, "tuning_enabled", False)
    assert client.post("/api/brain/tuning/candidates", json=payload).status_code == 503
    monkeypatch.setattr(settings, "tuning_enabled", True)
    resp = client.post("/api/brain/tuning/candidates", json=payload)
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"


def test_http_excluded_candidate_returns_422(client, monkeypatch):
    monkeypatch.setattr(settings, "tuning_enabled", True)
    payload = {"kind": "strong_response",
               "messages": [{"role": "user", "content": "x"}],
               "target_output": "This Agreement, whereas the grant of rights..."}
    resp = client.post("/api/brain/tuning/candidates", json=payload)
    assert resp.status_code == 422
    assert "excluded" in resp.json()["detail"]


def test_http_deploy_gate_blocks_then_allows(client):
    reg = client.post("/api/brain/tuning/adapters", json={"name": "http-cand"})
    adapter_id = reg.json()["id"]
    # Not beating base → approve is 409.
    client.post(f"/api/brain/tuning/adapters/{adapter_id}/evaluate",
                json={"base_aggregate": _GOOD, "adapter_aggregate": _GOOD})
    blocked = client.post(f"/api/brain/tuning/adapters/{adapter_id}/approve")
    assert blocked.status_code == 409 and "deploy_blocked" in blocked.json()["detail"]
    # Beats base + preserves permissions/approval → approve + deploy succeed.
    client.post(f"/api/brain/tuning/adapters/{adapter_id}/evaluate",
                json={"base_aggregate": _BASE, "adapter_aggregate": _GOOD})
    assert client.post(f"/api/brain/tuning/adapters/{adapter_id}/approve").status_code == 200
    deployed = client.post(f"/api/brain/tuning/adapters/{adapter_id}/deploy")
    assert deployed.status_code == 200 and deployed.json()["status"] == "deployed"
    active = client.get("/api/brain/tuning/active").json()
    assert active["serving_base_model"] is False and active["adapter"]["id"] == adapter_id
    # Rollback → base model.
    client.post(f"/api/brain/tuning/adapters/{adapter_id}/rollback")
    assert client.get("/api/brain/tuning/active").json()["serving_base_model"] is True
