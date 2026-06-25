"""SUPERVOID Pictures logic: dossier → project promotion, shot lists,
production breakdowns, reference carrying (knowledge entities, rights,
provenance) and the adaptation-package export (JSON + Markdown).

This is the operational internal adapter behind the SUPERVOID Movies
integration descriptor. It references — never duplicates — characters,
storyboard panels, asset versions and rights from the rest of the system.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models import (
    AdaptationDossier,
    AdaptationStatus,
    AssetVersion,
    KnowledgeEntity,
    ProvenanceRecord,
    Rights,
    Scene,
    SceneCharacterLink,
    ScreenFormat,
    ScreenProject,
    ScreenProjectStatus,
    ScreenSequence,
    ScreenShotAssetLink,
    ScreenUnit,
    ScreenUnitType,
    Shot,
)

# A dossier must be past mere proposal (and not abandoned) before a screen
# project can be built from it.
APPROVED_DOSSIER_STATES = frozenset(
    {
        AdaptationStatus.OPTIONED,
        AdaptationStatus.IN_DEVELOPMENT,
        AdaptationStatus.IN_PRODUCTION,
        AdaptationStatus.RELEASED,
    }
)


def is_dossier_approved(dossier: AdaptationDossier) -> bool:
    return dossier.status in APPROVED_DOSSIER_STATES


def create_project_from_dossier(
    session: Session,
    dossier: AdaptationDossier,
    *,
    fmt: ScreenFormat,
    title: Optional[str] = None,
) -> ScreenProject:
    """Create a ScreenProject from an approved dossier and seed its first unit.

    Caller commits. Raises 409 if the dossier is not approved.
    """
    if not is_dossier_approved(dossier):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Dossier status '{dossier.status.value}' is not approved for a "
                "screen project (needs optioned / in development / in production)."
            ),
        )
    source = dossier.source_work
    project = ScreenProject(
        dossier_id=dossier.id,
        source_work_id=dossier.source_work_id,
        story_world_id=source.story_world_id if source is not None else None,
        title=title or (source.title if source is not None else "Untitled screen project"),
        format=fmt,
        status=ScreenProjectStatus.DEVELOPMENT,
        logline=dossier.logline,
    )
    session.add(project)
    session.flush()
    unit_type = (
        ScreenUnitType.EPISODE if fmt == ScreenFormat.SERIES else ScreenUnitType.REEL
    )
    session.add(
        ScreenUnit(
            screen_project_id=project.id, unit_type=unit_type, number=1, position=0,
            title="Reel 1" if unit_type == ScreenUnitType.REEL else "Episode 1",
        )
    )
    return project


# --- traversal -------------------------------------------------------------


def scenes_for_project(session: Session, project_id: str) -> list[Scene]:
    stmt = (
        select(Scene)
        .join(ScreenSequence, Scene.sequence_id == ScreenSequence.id)
        .join(ScreenUnit, ScreenSequence.unit_id == ScreenUnit.id)
        .where(ScreenUnit.screen_project_id == project_id)
    )
    return list(session.exec(stmt).all())


def _shots_for_scene(session: Session, scene_id: str) -> list[Shot]:
    return list(
        session.exec(
            select(Shot).where(Shot.scene_id == scene_id).order_by(
                Shot.position, Shot.shot_number
            )
        ).all()
    )


# --- shot list & breakdown -------------------------------------------------


def shot_list(session: Session, project: ScreenProject) -> list[dict]:
    scenes = sorted(
        scenes_for_project(session, project.id),
        key=lambda s: (s.position, s.scene_number),
    )
    rows: list[dict] = []
    for scene in scenes:
        for shot in _shots_for_scene(session, scene.id):
            rows.append(
                {
                    "scene_number": scene.scene_number,
                    "scene_heading": scene.heading,
                    "shot_id": shot.id,
                    "shot_number": shot.shot_number,
                    "framing": shot.framing.value if shot.framing else None,
                    "camera_angle": shot.camera_angle.value if shot.camera_angle else None,
                    "movement": shot.movement.value if shot.movement else None,
                    "lens": shot.lens,
                    "duration_seconds": shot.duration_seconds,
                    "vfx": shot.vfx,
                    "status": shot.status.value,
                    "approval": shot.approval.value,
                    "storyboard_panel_id": shot.source_storyboard_panel_id,
                }
            )
    return rows


def production_breakdown(session: Session, project: ScreenProject) -> dict:
    scenes = sorted(
        scenes_for_project(session, project.id),
        key=lambda s: (s.position, s.scene_number),
    )
    scene_rows: list[dict] = []
    locations: set[str] = set()
    character_names: set[str] = set()
    total_shots = 0
    vfx_shots = 0
    total_duration = 0.0

    for scene in scenes:
        shots = _shots_for_scene(session, scene.id)
        total_shots += len(shots)
        scene_vfx = sum(1 for sh in shots if sh.vfx and sh.vfx.strip())
        vfx_shots += scene_vfx
        if scene.estimated_duration_seconds:
            total_duration += scene.estimated_duration_seconds
        if scene.location:
            locations.add(scene.location)
        chars = [c.entity_name for c in scene.character_links if c.entity_name]
        character_names.update(chars)
        scene_rows.append(
            {
                "scene_id": scene.id,
                "scene_number": scene.scene_number,
                "heading": scene.heading,
                "location": scene.location,
                "environment": scene.environment.value,
                "time_of_day": scene.time_of_day.value,
                "characters": chars,
                "shot_count": len(shots),
                "vfx_shot_count": scene_vfx,
                "estimated_duration_seconds": scene.estimated_duration_seconds,
                "production_status": scene.production_status.value,
            }
        )

    return {
        "project_id": project.id,
        "scenes": scene_rows,
        "totals": {
            "scenes": len(scenes),
            "shots": total_shots,
            "vfx_shots": vfx_shots,
            "locations": sorted(locations),
            "characters": sorted(character_names),
            "estimated_duration_seconds": total_duration,
        },
    }


# --- references (knowledge entities, rights, provenance) --------------------


def references(session: Session, project: ScreenProject) -> dict:
    scenes = scenes_for_project(session, project.id)
    scene_ids = [s.id for s in scenes]

    # Knowledge entities via scene character links.
    entity_ids: set[str] = set()
    if scene_ids:
        for link in session.exec(
            select(SceneCharacterLink).where(
                SceneCharacterLink.scene_id.in_(scene_ids)
            )
        ).all():
            entity_ids.add(link.entity_id)
    entities = [
        {"id": e.id, "name": e.name, "kind": e.kind.value}
        for e in (session.get(KnowledgeEntity, eid) for eid in entity_ids)
        if e is not None
    ]

    # Rights carried from the source work.
    rights_rows: list[dict] = []
    if project.source_work_id:
        for r in session.exec(
            select(Rights).where(Rights.work_id == project.source_work_id)
        ).all():
            rights_rows.append(
                {
                    "id": r.id,
                    "territory": r.territory,
                    "language": r.language,
                    "film_rights": r.film_rights.value,
                    "adaptation_rights": r.adaptation_rights.value,
                    "holder": r.holder,
                    "expiration_date": r.expiration_date.isoformat()
                    if r.expiration_date
                    else None,
                }
            )

    # Provenance references via shot asset links → asset versions.
    shot_ids: list[str] = []
    for sid in scene_ids:
        shot_ids.extend(sh.id for sh in _shots_for_scene(session, sid))
    provenance_rows: list[dict] = []
    seen_versions: set[str] = set()
    if shot_ids:
        for link in session.exec(
            select(ScreenShotAssetLink).where(
                ScreenShotAssetLink.shot_id.in_(shot_ids)
            )
        ).all():
            if link.asset_version_id in seen_versions:
                continue
            seen_versions.add(link.asset_version_id)
            version = session.get(AssetVersion, link.asset_version_id)
            if version is None:
                continue
            prov = session.exec(
                select(ProvenanceRecord).where(
                    ProvenanceRecord.asset_version_id == version.id
                )
            ).first()
            provenance_rows.append(
                {
                    "asset_version_id": version.id,
                    "asset_id": version.asset_id,
                    "kind": prov.kind.value if prov else None,
                    "provider": prov.provider if prov else None,
                    "commercial_use_review": prov.commercial_use_review.value
                    if prov
                    else None,
                }
            )

    return {"entities": entities, "rights": rights_rows, "provenance": provenance_rows}


# --- adaptation-package export ---------------------------------------------


def export_package(session: Session, project: ScreenProject) -> dict:
    dossier = session.get(AdaptationDossier, project.dossier_id)
    units = sorted(project.units, key=lambda u: (u.position, u.number))
    unit_rows = []
    for unit in units:
        seq_rows = []
        for seq in sorted(unit.sequences, key=lambda s: (s.position, s.sequence_number)):
            scene_rows = []
            for scene in sorted(seq.scenes, key=lambda s: (s.position, s.scene_number)):
                shots = _shots_for_scene(session, scene.id)
                scene_rows.append(
                    {
                        "scene_number": scene.scene_number,
                        "heading": scene.heading,
                        "location": scene.location,
                        "environment": scene.environment.value,
                        "time_of_day": scene.time_of_day.value,
                        "synopsis": scene.synopsis,
                        "estimated_duration_seconds": scene.estimated_duration_seconds,
                        "production_status": scene.production_status.value,
                        "characters": [
                            c.entity_name for c in scene.character_links if c.entity_name
                        ],
                        "shots": [
                            {
                                "shot_number": sh.shot_number,
                                "framing": sh.framing.value if sh.framing else None,
                                "camera_angle": sh.camera_angle.value if sh.camera_angle else None,
                                "movement": sh.movement.value if sh.movement else None,
                                "lens": sh.lens,
                                "duration_seconds": sh.duration_seconds,
                                "dialogue": sh.dialogue,
                                "vfx": sh.vfx,
                                "status": sh.status.value,
                                "approval": sh.approval.value,
                                "storyboard_panel_id": sh.source_storyboard_panel_id,
                                "mapped_panel_ids": [pl.panel_id for pl in sh.panel_links],
                            }
                            for sh in shots
                        ],
                    }
                )
            seq_rows.append(
                {
                    "sequence_number": seq.sequence_number,
                    "title": seq.title,
                    "scenes": scene_rows,
                }
            )
        unit_rows.append(
            {
                "unit_type": unit.unit_type.value,
                "number": unit.number,
                "title": unit.title,
                "sequences": seq_rows,
            }
        )

    return {
        "project": {
            "id": project.id,
            "title": project.title,
            "format": project.format.value,
            "status": project.status.value,
            "logline": project.logline,
            "synopsis": project.synopsis,
            "source_work_id": project.source_work_id,
        },
        "dossier": {
            "id": dossier.id,
            "target_medium": dossier.target_medium.value,
            "status": dossier.status.value,
            "rights_clearance": dossier.rights_clearance.value,
        }
        if dossier is not None
        else None,
        "units": unit_rows,
        "breakdown_totals": production_breakdown(session, project)["totals"],
        "references": references(session, project),
    }


def package_to_markdown(package: dict) -> str:
    p = package["project"]
    lines: list[str] = [
        f"# {p['title']}",
        "",
        f"*Adaptation package — SUPERVOID Pictures · {p['format']} · {p['status']}*",
        "",
    ]
    if p.get("logline"):
        lines += [f"> {p['logline']}", ""]
    totals = package.get("breakdown_totals", {})
    lines += [
        "## Overview",
        "",
        f"- Scenes: {totals.get('scenes', 0)}",
        f"- Shots: {totals.get('shots', 0)} ({totals.get('vfx_shots', 0)} with VFX)",
        f"- Estimated duration: {totals.get('estimated_duration_seconds', 0)}s",
        f"- Locations: {', '.join(totals.get('locations', [])) or '—'}",
        f"- Characters: {', '.join(totals.get('characters', [])) or '—'}",
        "",
    ]
    for unit in package["units"]:
        lines.append(f"## {unit['unit_type'].title()} {unit['number']}: {unit['title'] or ''}".rstrip())
        lines.append("")
        for seq in unit["sequences"]:
            lines.append(f"### Sequence {seq['sequence_number']}: {seq['title'] or ''}".rstrip())
            lines.append("")
            for scene in seq["scenes"]:
                heading = scene["heading"] or (
                    f"{scene['environment'].upper()}. {scene['location'] or ''} — "
                    f"{scene['time_of_day'].upper()}"
                )
                lines.append(f"#### Scene {scene['scene_number']} — {heading}")
                lines.append("")
                if scene.get("synopsis"):
                    lines += [scene["synopsis"], ""]
                if scene.get("characters"):
                    lines += [f"*Characters:* {', '.join(scene['characters'])}", ""]
                for sh in scene["shots"]:
                    bits = [b for b in (sh["framing"], sh["camera_angle"], sh["movement"], sh["lens"]) if b]
                    detail = " · ".join(bits) if bits else "—"
                    lines.append(f"- **Shot {sh['shot_number']}** ({detail})")
                    if sh.get("dialogue"):
                        lines.append(f"  - Dialogue: {sh['dialogue']}")
                    if sh.get("vfx"):
                        lines.append(f"  - VFX: {sh['vfx']}")
                lines.append("")

    refs = package.get("references", {})
    if refs.get("rights"):
        lines += ["## Rights", ""]
        for r in refs["rights"]:
            lines.append(
                f"- {r['territory']} / {r['language']}: film {r['film_rights']}, "
                f"adaptation {r['adaptation_rights']}"
                + (f" (expires {r['expiration_date']})" if r.get("expiration_date") else "")
            )
        lines.append("")
    return "\n".join(lines)
