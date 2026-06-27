"""Adapter registry, project-evaluation gate, deploy + rollback (Prompt 18).

The registry records everything a deployment decision needs (base model, dataset
version, training parameters, licence, evaluation results, deployment status). An
adapter is evaluated against the **Phase-17 SUPERVOID corpus** and is deployable
ONLY when it beats the base on that project-specific evaluation **without
weakening permissions or approval behaviour**. Rollback returns serving to the
base model. Only one adapter is DEPLOYED at a time.

Nothing trains here and nothing is auto-deployed; evaluation runs the corpus
against the configured providers on throwaway in-memory databases (never the real
database), exactly like the eval CLI.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import settings
from app.models import TuningAdapter
from app.models.base import utcnow
from app.models.enums import AdapterStatus
from app.services.tuning.errors import TuningDeployBlocked


def default_training_parameters() -> dict:
    return {
        "method": "lora",
        "lora_rank": settings.tuning_lora_rank,
        "lora_alpha": settings.tuning_lora_alpha,
        "lora_dropout": settings.tuning_lora_dropout,
        "learning_rate": settings.tuning_learning_rate,
        "epochs": settings.tuning_epochs,
    }


def register_adapter(
    session: Session,
    *,
    name: str,
    base_model: Optional[str] = None,
    dataset_version: Optional[str] = None,
    training_parameters: Optional[dict] = None,
    licence: str = "proprietary",
    artifact_ref: Optional[str] = None,
    created_by_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> TuningAdapter:
    if not (name or "").strip():
        raise ValueError("Adapter name is required.")
    adapter = TuningAdapter(
        name=name.strip(),
        base_model=(base_model or settings.tuning_default_base_model),
        dataset_version=dataset_version,
        training_parameters=training_parameters or default_training_parameters(),
        licence=licence or "proprietary",
        artifact_ref=artifact_ref,
        status=AdapterStatus.REGISTERED,
        created_by_id=created_by_id,
        notes=notes,
    )
    session.add(adapter)
    session.flush()
    return adapter


def get_adapter(session: Session, adapter_id: str) -> Optional[TuningAdapter]:
    return session.get(TuningAdapter, adapter_id)


def list_adapters(session: Session, *, limit: int = 100, offset: int = 0) -> list[TuningAdapter]:
    stmt = select(TuningAdapter).order_by(TuningAdapter.created_at.desc()).offset(offset).limit(limit)
    return list(session.exec(stmt).all())


# === evaluation comparison + deploy gate ===================================
def compare_results(base_aggregate: dict, adapter_aggregate: dict) -> dict:
    """Compare two Phase-17 corpus aggregates and decide deployability.

    Deployable iff the adapter **beats the base** (not worse overall and strictly
    better somewhere) AND **does not weaken** permissions or approval, AND meets
    the absolute deploy floor (pass-rate / correctness)."""
    bp = float(base_aggregate.get("pass_rate", 0) or 0)
    ap = float(adapter_aggregate.get("pass_rate", 0) or 0)
    bm = float(base_aggregate.get("mean_score", 0) or 0)
    am = float(adapter_aggregate.get("mean_score", 0) or 0)
    bdim = base_aggregate.get("dimension_pass_rates", {}) or {}
    adim = adapter_aggregate.get("dimension_pass_rates", {}) or {}

    def pair(name):
        return float(bdim.get(name, 0) or 0), float(adim.get(name, 0) or 0)

    b_corr, a_corr = pair("correctness")
    b_perm, a_perm = pair("permissions")
    b_appr, a_appr = pair("approval")

    permissions_preserved = a_perm >= b_perm
    approval_preserved = a_appr >= b_appr
    not_worse_overall = ap >= bp and a_corr >= b_corr
    strictly_better = ap > bp or am > bm or a_corr > b_corr
    beats_base = not_worse_overall and strictly_better
    meets_floor = (
        ap >= settings.tuning_deploy_min_pass_rate
        and a_corr >= settings.tuning_deploy_min_correctness
    )
    deployable = beats_base and permissions_preserved and approval_preserved and meets_floor

    reasons = []
    if not beats_base:
        reasons.append("does not beat the base model on the project evaluation")
    if not permissions_preserved:
        reasons.append("weakens permissions behaviour")
    if not approval_preserved:
        reasons.append("weakens approval behaviour")
    if not meets_floor:
        reasons.append(
            f"below deploy floor (pass_rate≥{settings.tuning_deploy_min_pass_rate}, "
            f"correctness≥{settings.tuning_deploy_min_correctness})"
        )

    return {
        "beats_base": beats_base,
        "permissions_preserved": permissions_preserved,
        "approval_preserved": approval_preserved,
        "meets_floor": meets_floor,
        "deployable": deployable,
        "reason": "; ".join(reasons) if reasons else "",
        "deltas": {
            "pass_rate": round(ap - bp, 4),
            "mean_score": round(am - bm, 4),
            "correctness": round(a_corr - b_corr, 4),
            "permissions": round(a_perm - b_perm, 4),
            "approval": round(a_appr - b_appr, 4),
        },
        "base": {"pass_rate": bp, "mean_score": bm, "correctness": b_corr,
                 "permissions": b_perm, "approval": b_appr},
        "adapter": {"pass_rate": ap, "mean_score": am, "correctness": a_corr,
                    "permissions": a_perm, "approval": a_appr},
    }


def record_evaluation(
    session: Session,
    adapter: TuningAdapter,
    *,
    base_aggregate: dict,
    adapter_aggregate: dict,
    base_model_name: Optional[str] = None,
    adapter_model_name: Optional[str] = None,
    corpus_version: Optional[str] = None,
) -> TuningAdapter:
    """Store a base-vs-adapter comparison + gate verdict on the adapter."""
    cmp = compare_results(base_aggregate, adapter_aggregate)
    adapter.evaluation_results = {
        "corpus_version": corpus_version,
        "base_model": base_model_name,
        "adapter_model": adapter_model_name,
        "base": base_aggregate,
        "adapter": adapter_aggregate,
        "comparison": cmp,
    }
    adapter.beats_base = cmp["beats_base"]
    adapter.permissions_preserved = cmp["permissions_preserved"]
    adapter.approval_preserved = cmp["approval_preserved"]
    adapter.deploy_blocked_reason = None if cmp["deployable"] else cmp["reason"]
    adapter.status = AdapterStatus.EVALUATED
    adapter.evaluated_at = utcnow()
    session.add(adapter)
    session.flush()
    return adapter


def _run_corpus_isolated(provider):
    """Run the Phase-17 corpus on a throwaway in-memory DB (never the real one)."""
    from app.eval.harness import run_corpus

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    import app.models  # noqa: F401 (register tables)

    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        return run_corpus(s, provider=provider)


def evaluate_adapter(
    session: Session,
    adapter: TuningAdapter,
    *,
    base_provider=None,
    adapter_provider=None,
) -> TuningAdapter:
    """Run the project evaluation for the base and the adapter and record it.

    In the offline default both providers are the dry-run provider, so the adapter
    does not beat the base and deployment stays blocked — the correct safe default.
    A real comparison points ``adapter_provider`` at the vLLM serving the LoRA."""
    from app.services.ai.providers import get_provider

    base_provider = base_provider or get_provider()
    adapter_provider = adapter_provider or base_provider
    base_res = _run_corpus_isolated(base_provider)
    adapter_res = _run_corpus_isolated(adapter_provider)
    return record_evaluation(
        session, adapter,
        base_aggregate=base_res.aggregate, adapter_aggregate=adapter_res.aggregate,
        base_model_name=base_res.model, adapter_model_name=adapter_res.model,
        corpus_version=base_res.corpus_version,
    )


def deploy_gate(adapter: TuningAdapter) -> tuple[bool, str]:
    """The single source of truth for 'may this adapter be deployed?'."""
    if adapter.status in (AdapterStatus.REGISTERED, AdapterStatus.REJECTED):
        return False, "adapter has not been evaluated against the project corpus"
    cmp = (adapter.evaluation_results or {}).get("comparison", {})
    if not cmp:
        return False, "no evaluation results recorded"
    if not cmp.get("deployable"):
        return False, cmp.get("reason") or "does not beat base / weakens permissions or approval"
    return True, ""


def approve_adapter(
    session: Session, adapter: TuningAdapter, *, approver_id: Optional[str] = None
) -> TuningAdapter:
    ok, reason = deploy_gate(adapter)
    if not ok:
        raise TuningDeployBlocked(reason)
    adapter.status = AdapterStatus.APPROVED
    adapter.approved_by_id = approver_id
    adapter.approved_at = utcnow()
    session.add(adapter)
    session.flush()
    return adapter


def deploy_adapter(
    session: Session, adapter: TuningAdapter, *, actor_id: Optional[str] = None
) -> TuningAdapter:
    """Deploy an APPROVED adapter (re-checks the gate defensively). Demotes any
    previously-deployed adapter so exactly one is active."""
    ok, reason = deploy_gate(adapter)
    if not ok:
        raise TuningDeployBlocked(reason)
    if adapter.status not in (AdapterStatus.APPROVED, AdapterStatus.DEPLOYED):
        raise TuningDeployBlocked("approve the adapter before deploying it")
    for other in session.exec(
        select(TuningAdapter).where(TuningAdapter.status == AdapterStatus.DEPLOYED)
    ).all():
        if other.id != adapter.id:
            other.status = AdapterStatus.ROLLED_BACK
            other.rolled_back_at = utcnow()
            session.add(other)
    adapter.status = AdapterStatus.DEPLOYED
    adapter.deployed_at = utcnow()
    session.add(adapter)
    session.flush()
    return adapter


def rollback_to_base(
    session: Session, *, actor_id: Optional[str] = None, adapter: Optional[TuningAdapter] = None
) -> Optional[TuningAdapter]:
    """Roll the active adapter back to the base model. Returns the rolled-back
    adapter, or None if the base model was already active."""
    target = adapter or active_adapter(session)
    if target is None:
        return None
    target.status = AdapterStatus.ROLLED_BACK
    target.rolled_back_at = utcnow()
    session.add(target)
    session.flush()
    return target


def reject_adapter(
    session: Session, adapter: TuningAdapter, *, actor_id: Optional[str] = None,
    reason: str = "",
) -> TuningAdapter:
    adapter.status = AdapterStatus.REJECTED
    adapter.deploy_blocked_reason = reason or adapter.deploy_blocked_reason
    session.add(adapter)
    session.flush()
    return adapter


def active_adapter(session: Session) -> Optional[TuningAdapter]:
    return session.exec(
        select(TuningAdapter)
        .where(TuningAdapter.status == AdapterStatus.DEPLOYED)
        .order_by(TuningAdapter.deployed_at.desc())
    ).first()


def vllm_lora_config(session: Session, adapter: Optional[TuningAdapter] = None) -> dict:
    """A vLLM-compatible LoRA serving config for the active (or given) adapter.

    Deployment is recorded in the registry; APPLYING this config to the running
    vLLM (restart with these flags) is a deliberate deploy-host step — nothing is
    auto-applied. With no adapter active, the base model is served."""
    target = adapter or active_adapter(session)
    if target is None:
        return {
            "enable_lora": False,
            "base_model": settings.tuning_default_base_model,
            "lora_modules": [],
            "note": "Serving the base model; no adapter deployed.",
        }
    path = target.artifact_ref or f"{settings.tuning_adapter_mount_dir.rstrip('/')}/{target.id}"
    module = f"{target.name}={path}"
    return {
        "enable_lora": True,
        "base_model": target.base_model,
        "max_lora_rank": settings.tuning_vllm_max_lora_rank,
        "served_model_name": target.name,
        "lora_modules": [{"name": target.name, "path": path}],
        "cli": (
            f"--enable-lora --max-lora-rank {settings.tuning_vllm_max_lora_rank} "
            f"--lora-modules {module}"
        ),
        "env": {
            "VLLM_ENABLE_LORA": "1",
            "VLLM_MAX_LORA_RANK": str(settings.tuning_vllm_max_lora_rank),
            "VLLM_LORA_MODULES": module,
        },
        "note": (
            "Apply on the GPU host (restart vLLM with these flags). Deployment is "
            "recorded here; serving is a deploy-host step."
        ),
    }
