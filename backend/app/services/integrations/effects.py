"""Internal side effects performed by adapters once an operation is approved.

These are the *real* local mutations the hub is allowed to make: creating asset
versions and provenance from a generation backend, recording provenance from a
workflow, linking external objects to production tasks, and writing desktop
file-exchange packages to local storage. Each raises ``ValueError`` on bad
input so the service layer records the run as FAILED rather than half-applying.
"""
from __future__ import annotations

import io
import json
from typing import Optional

from sqlmodel import Session, func, select

from app.config import settings
from app.models import (
    Asset,
    AssetApprovalStatus,
    AssetType,
    AssetVersion,
    AssetVisibility,
    CommercialUseReviewStatus,
    IntegrationLink,
    IntegrationLinkKind,
    IntegrationPoint,
    ProductionItem,
    ProvenanceKind,
    ProvenanceRecord,
)
from app.models.base import utcnow
from app.services.storage import get_storage


def _int(value) -> Optional[int]:
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _asset_type(value) -> AssetType:
    if isinstance(value, AssetType):
        return value
    try:
        return AssetType(value)
    except (ValueError, TypeError):
        return AssetType.OTHER


def _provenance_kind(value, default: ProvenanceKind) -> ProvenanceKind:
    if isinstance(value, ProvenanceKind):
        return value
    try:
        return ProvenanceKind(value)
    except (ValueError, TypeError):
        return default


def _next_version_number(session: Session, asset_id: str) -> int:
    current = session.exec(
        select(func.max(AssetVersion.version_number)).where(
            AssetVersion.asset_id == asset_id
        )
    ).one()
    return (current or 0) + 1


def _build_provenance(
    asset_version_id: str,
    data: dict,
    owner_id: Optional[str],
    *,
    default_kind: ProvenanceKind,
) -> ProvenanceRecord:
    return ProvenanceRecord(
        asset_version_id=asset_version_id,
        kind=_provenance_kind(data.get("kind"), default_kind),
        provider=data.get("provider"),
        base_model=data.get("base_model"),
        base_model_version=data.get("base_model_version"),
        adapter_identifiers=data.get("adapter_identifiers"),
        prompt=data.get("prompt"),
        negative_prompt=data.get("negative_prompt"),
        seed=_int(data.get("seed")),
        sampler=data.get("sampler"),
        settings=data.get("settings") or {},
        source_references=data.get("source_references"),
        controlnet_inputs=data.get("controlnet_inputs"),
        generating_workflow=data.get("generating_workflow"),
        human_modifications=data.get("human_modifications"),
        generation_date=utcnow(),
        responsible_user_id=owner_id,
        commercial_use_review=CommercialUseReviewStatus.NOT_REVIEWED,
    )


def attach_asset_version(
    session: Session,
    *,
    asset_id: Optional[str] = None,
    new_asset: Optional[dict] = None,
    owner_id: Optional[str] = None,
    storage_key: str,
    mime_type: str = "application/octet-stream",
    technical_metadata: Optional[dict] = None,
    provenance: Optional[dict] = None,
    default_provenance_kind: ProvenanceKind = ProvenanceKind.AI_GENERATED,
) -> dict:
    """Create a new version on an existing/new Asset, with optional provenance.

    Bytes typically live in the external backend (ComfyUI) or a desktop app, so
    ``storage_key`` is usually a ``placeholder:`` reference. The first version
    becomes the asset's current version; later versions do not auto-promote.
    """
    if asset_id:
        asset = session.get(Asset, asset_id)
        if asset is None:
            raise ValueError(f"Asset {asset_id} not found.")
    else:
        na = new_asset or {}
        title = na.get("title")
        if not title:
            raise ValueError("A title is required to create a new asset.")
        asset = Asset(
            title=title,
            asset_type=_asset_type(na.get("asset_type")),
            work_id=na.get("work_id"),
            story_world_id=na.get("story_world_id"),
            visibility=AssetVisibility.PRIVATE,
            owner_id=owner_id,
        )
        session.add(asset)
        session.flush()

    version_number = _next_version_number(session, asset.id)
    version = AssetVersion(
        asset_id=asset.id,
        version_number=version_number,
        storage_key=storage_key,
        mime_type=mime_type,
        size_bytes=0,
        approval_status=AssetApprovalStatus.DRAFT,
        creator_id=owner_id,
        technical_metadata=technical_metadata or {},
    )
    session.add(version)
    session.flush()

    if asset.current_version_id is None:
        asset.current_version_id = version.id
        session.add(asset)

    provenance_id = None
    if provenance is not None:
        record = _build_provenance(
            version.id, provenance, owner_id, default_kind=default_provenance_kind
        )
        session.add(record)
        session.flush()
        provenance_id = record.id

    return {
        "asset_id": asset.id,
        "asset_version_id": version.id,
        "version_number": version_number,
        "provenance_id": provenance_id,
    }


def record_provenance(
    session: Session,
    *,
    asset_version_id: str,
    data: dict,
    owner_id: Optional[str],
    default_kind: ProvenanceKind = ProvenanceKind.AI_GENERATED,
) -> dict:
    """Attach a provenance record to an existing asset version."""
    version = session.get(AssetVersion, asset_version_id)
    if version is None:
        raise ValueError(f"Asset version {asset_version_id} not found.")
    record = _build_provenance(
        asset_version_id, data, owner_id, default_kind=default_kind
    )
    session.add(record)
    session.flush()
    return {"asset_version_id": asset_version_id, "provenance_id": record.id}


def create_task_link(
    session: Session,
    point: IntegrationPoint,
    *,
    external_kind: IntegrationLinkKind,
    external_ref: str,
    target_id: str,
    external_url: Optional[str] = None,
    title: Optional[str] = None,
    extra: Optional[dict] = None,
) -> dict:
    """Link an external object (commit/issue/PR) to a production task."""
    if not external_ref:
        raise ValueError("An external reference is required.")
    if not target_id:
        raise ValueError("A target production task id is required.")
    if session.get(ProductionItem, target_id) is None:
        raise ValueError(f"Production task {target_id} not found.")
    link = IntegrationLink(
        integration_point_id=point.id,
        external_kind=external_kind,
        external_ref=str(external_ref),
        external_url=external_url,
        title=title,
        target_type="production_task",
        target_id=target_id,
        extra=extra or {},
    )
    session.add(link)
    session.flush()
    return {
        "link_id": link.id,
        "external_kind": external_kind.value,
        "external_ref": link.external_ref,
        "target_id": target_id,
    }


def write_exchange_package(
    *,
    app_key: str,
    manifest: dict,
    correlation_id: str,
) -> dict:
    """Write a desktop file-exchange package manifest to local storage."""
    storage = get_storage()
    key = f"{settings.integrations_exchange_subdir}/{app_key}/{correlation_id}.json"
    data = json.dumps(manifest, indent=2, ensure_ascii=False, default=str).encode("utf-8")
    stored = storage.write(key, io.BytesIO(data))
    return {
        "package_key": stored.storage_key,
        "size_bytes": stored.size_bytes,
        "checksum": stored.sha256,
    }
