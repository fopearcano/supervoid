"""Optional fine-tuning data pipeline API (Prompt 18) — INTERNAL, admin-only.

Candidate collection + review, versioned dataset export, and the adapter registry
(register → evaluate against the Phase-17 corpus → approve → deploy → rollback),
plus the vLLM LoRA serving config. Nothing trains or deploys automatically:
collection is gated behind ``tuning_enabled``; an adapter is deployable ONLY when
it beats the base on the project evaluation without weakening permissions or
approval behaviour.

Everything is gated to admins.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.auth import ADMIN_ONLY
from app.auth.dependencies import get_current_user
from app.config import settings
from app.db import get_session
from app.models import User
from app.models.enums import TuningCandidateStatus, TuningExampleKind
from app.schemas.tuning import (
    AdapterActionRequest,
    AdapterEvaluateRequest,
    AdapterRegisterRequest,
    DatasetExportRequest,
    TuningAdapterRead,
    TuningDatasetRead,
    TuningExampleCreate,
    TuningExampleRead,
    TuningReviewRequest,
)
from app.services import tuning
from app.services.tuning.errors import TuningDeployBlocked, TuningExclusion
from app.utils.logging import log_event

router = APIRouter(prefix="/brain/tuning", tags=["brain-tuning"], dependencies=ADMIN_ONLY)


def _audit(action: str, actor: User, **fields) -> None:
    log_event("tuning.action", action=action, actor=actor.id, **fields)


# === candidates + review ===================================================
@router.get("/candidates", response_model=list[TuningExampleRead])
def list_candidates(
    status: TuningCandidateStatus | None = Query(default=None),
    kind: TuningExampleKind | None = Query(default=None),
    work_id: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[TuningExampleRead]:
    rows = tuning.list_examples(session, status=status, kind=kind, work_id=work_id,
                               limit=limit, offset=offset)
    return [TuningExampleRead.model_validate(r, from_attributes=True) for r in rows]


@router.post("/candidates", response_model=TuningExampleRead, status_code=201)
def propose_candidate(
    body: TuningExampleCreate, session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TuningExampleRead:
    if not settings.tuning_enabled:
        raise HTTPException(status_code=503, detail="Fine-tuning collection is disabled (tuning_enabled=false).")
    try:
        example = tuning.propose_example(
            session, kind=body.kind, messages=body.messages, target_output=body.target_output,
            created_by_id=user.id, source_type=body.source_type, source_id=body.source_id,
            work_id=body.work_id, story_world_id=body.story_world_id, task_category=body.task_category,
            tool_calls=body.tool_calls, expected_tools=body.expected_tools,
            forbidden_tools=body.forbidden_tools, approval_behaviour=body.approval_behaviour,
            retrieval_expectation=body.retrieval_expectation, refusal=body.refusal,
            rationale=body.rationale, anonymised=body.anonymised, allow_contract=body.allow_contract,
        )
    except TuningExclusion as exc:
        raise HTTPException(status_code=422, detail={"excluded": exc.reasons})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session.commit()
    session.refresh(example)
    _audit("propose_candidate", user, example_id=example.id, kind=body.kind.value)
    return TuningExampleRead.model_validate(example, from_attributes=True)


def _load_example(session: Session, example_id: str):
    example = tuning.get_example(session, example_id)
    if example is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return example


@router.get("/candidates/{example_id}", response_model=TuningExampleRead)
def get_candidate(example_id: str, session: Session = Depends(get_session)) -> TuningExampleRead:
    return TuningExampleRead.model_validate(_load_example(session, example_id), from_attributes=True)


@router.post("/candidates/{example_id}/approve", response_model=TuningExampleRead)
def approve_candidate(
    example_id: str, body: TuningReviewRequest = TuningReviewRequest(),
    session: Session = Depends(get_session), user: User = Depends(get_current_user),
) -> TuningExampleRead:
    example = _load_example(session, example_id)
    try:
        tuning.approve_example(session, example, reviewer_id=user.id, note=body.note)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    session.commit()
    session.refresh(example)
    _audit("approve_candidate", user, example_id=example_id)
    return TuningExampleRead.model_validate(example, from_attributes=True)


@router.post("/candidates/{example_id}/reject", response_model=TuningExampleRead)
def reject_candidate(
    example_id: str, body: TuningReviewRequest = TuningReviewRequest(),
    session: Session = Depends(get_session), user: User = Depends(get_current_user),
) -> TuningExampleRead:
    example = _load_example(session, example_id)
    try:
        tuning.reject_example(session, example, reviewer_id=user.id, note=body.note)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    session.commit()
    session.refresh(example)
    _audit("reject_candidate", user, example_id=example_id)
    return TuningExampleRead.model_validate(example, from_attributes=True)


# === datasets ==============================================================
@router.get("/datasets", response_model=list[TuningDatasetRead])
def list_datasets(session: Session = Depends(get_session)) -> list[TuningDatasetRead]:
    return [TuningDatasetRead.model_validate(r, from_attributes=True)
            for r in tuning.list_datasets(session)]


@router.post("/datasets", response_model=TuningDatasetRead, status_code=201)
def export_dataset(
    body: DatasetExportRequest, session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TuningDatasetRead:
    try:
        dataset = tuning.export_dataset(
            session, version=body.version, description=body.description,
            created_by_id=user.id, val_fraction=body.val_fraction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session.commit()
    session.refresh(dataset)
    _audit("export_dataset", user, version=dataset.version, count=dataset.example_count)
    return TuningDatasetRead.model_validate(dataset, from_attributes=True)


@router.get("/datasets/{dataset_id}", response_model=TuningDatasetRead)
def get_dataset(dataset_id: str, session: Session = Depends(get_session)) -> TuningDatasetRead:
    dataset = tuning.get_dataset(session, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return TuningDatasetRead.model_validate(dataset, from_attributes=True)


# === adapter registry ======================================================
@router.get("/adapters", response_model=list[TuningAdapterRead])
def list_adapters(session: Session = Depends(get_session)) -> list[TuningAdapterRead]:
    return [TuningAdapterRead.model_validate(r, from_attributes=True)
            for r in tuning.list_adapters(session)]


@router.post("/adapters", response_model=TuningAdapterRead, status_code=201)
def register_adapter(
    body: AdapterRegisterRequest, session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TuningAdapterRead:
    try:
        adapter = tuning.register_adapter(
            session, name=body.name, base_model=body.base_model,
            dataset_version=body.dataset_version, training_parameters=body.training_parameters,
            licence=body.licence, artifact_ref=body.artifact_ref, created_by_id=user.id,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session.commit()
    session.refresh(adapter)
    _audit("register_adapter", user, adapter_id=adapter.id, name=adapter.name)
    return TuningAdapterRead.model_validate(adapter, from_attributes=True)


def _load_adapter(session: Session, adapter_id: str):
    adapter = tuning.get_adapter(session, adapter_id)
    if adapter is None:
        raise HTTPException(status_code=404, detail="Adapter not found")
    return adapter


@router.get("/adapters/{adapter_id}", response_model=TuningAdapterRead)
def get_adapter(adapter_id: str, session: Session = Depends(get_session)) -> TuningAdapterRead:
    return TuningAdapterRead.model_validate(_load_adapter(session, adapter_id), from_attributes=True)


@router.post("/adapters/{adapter_id}/evaluate", response_model=TuningAdapterRead)
def evaluate_adapter(
    adapter_id: str, body: AdapterEvaluateRequest = AdapterEvaluateRequest(),
    session: Session = Depends(get_session), user: User = Depends(get_current_user),
) -> TuningAdapterRead:
    adapter = _load_adapter(session, adapter_id)
    if body.base_aggregate is not None and body.adapter_aggregate is not None:
        tuning.record_evaluation(
            session, adapter, base_aggregate=body.base_aggregate,
            adapter_aggregate=body.adapter_aggregate, base_model_name=body.base_model_name,
            adapter_model_name=body.adapter_model_name,
        )
    else:
        # Run the project corpus against the configured provider for both sides
        # (offline this yields no improvement, keeping deployment safely blocked).
        tuning.evaluate_adapter(session, adapter)
    session.commit()
    session.refresh(adapter)
    _audit("evaluate_adapter", user, adapter_id=adapter_id, beats_base=adapter.beats_base)
    return TuningAdapterRead.model_validate(adapter, from_attributes=True)


@router.post("/adapters/{adapter_id}/approve", response_model=TuningAdapterRead)
def approve_adapter(
    adapter_id: str, session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TuningAdapterRead:
    adapter = _load_adapter(session, adapter_id)
    try:
        tuning.approve_adapter(session, adapter, approver_id=user.id)
    except TuningDeployBlocked as exc:
        raise HTTPException(status_code=409, detail={"deploy_blocked": exc.reason})
    session.commit()
    session.refresh(adapter)
    _audit("approve_adapter", user, adapter_id=adapter_id)
    return TuningAdapterRead.model_validate(adapter, from_attributes=True)


@router.post("/adapters/{adapter_id}/deploy", response_model=TuningAdapterRead)
def deploy_adapter(
    adapter_id: str, session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TuningAdapterRead:
    adapter = _load_adapter(session, adapter_id)
    try:
        tuning.deploy_adapter(session, adapter, actor_id=user.id)
    except TuningDeployBlocked as exc:
        raise HTTPException(status_code=409, detail={"deploy_blocked": exc.reason})
    session.commit()
    session.refresh(adapter)
    _audit("deploy_adapter", user, adapter_id=adapter_id)
    return TuningAdapterRead.model_validate(adapter, from_attributes=True)


@router.post("/adapters/{adapter_id}/rollback", response_model=TuningAdapterRead)
def rollback_adapter(
    adapter_id: str, session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TuningAdapterRead:
    adapter = _load_adapter(session, adapter_id)
    tuning.rollback_to_base(session, actor_id=user.id, adapter=adapter)
    session.commit()
    session.refresh(adapter)
    _audit("rollback_adapter", user, adapter_id=adapter_id)
    return TuningAdapterRead.model_validate(adapter, from_attributes=True)


@router.post("/adapters/{adapter_id}/reject", response_model=TuningAdapterRead)
def reject_adapter(
    adapter_id: str, body: AdapterActionRequest = AdapterActionRequest(),
    session: Session = Depends(get_session), user: User = Depends(get_current_user),
) -> TuningAdapterRead:
    adapter = _load_adapter(session, adapter_id)
    tuning.reject_adapter(session, adapter, actor_id=user.id, reason=body.reason or "")
    session.commit()
    session.refresh(adapter)
    _audit("reject_adapter", user, adapter_id=adapter_id)
    return TuningAdapterRead.model_validate(adapter, from_attributes=True)


@router.get("/adapters/{adapter_id}/vllm-config")
def adapter_vllm_config(adapter_id: str, session: Session = Depends(get_session)) -> dict:
    """The vLLM-compatible LoRA serving config for this adapter (not auto-applied)."""
    return tuning.vllm_lora_config(session, _load_adapter(session, adapter_id))


# === active serving selection ==============================================
@router.get("/active")
def active_serving(session: Session = Depends(get_session)) -> dict:
    """What is currently served — a deployed adapter, or the base model — plus the
    vLLM LoRA config to apply on the GPU host."""
    adapter = tuning.active_adapter(session)
    return {
        "adapter": (TuningAdapterRead.model_validate(adapter, from_attributes=True).model_dump()
                    if adapter is not None else None),
        "serving_base_model": adapter is None,
        "vllm_config": tuning.vllm_lora_config(session, adapter),
    }
