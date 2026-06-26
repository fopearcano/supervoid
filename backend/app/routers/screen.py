"""SUPERVOID Pictures — the operational screen-production API.

Entered via AdaptationDossier; structured ScreenProject → Unit → Sequence →
Scene → Shot. Reuses graphic-novel panels as storyboard references, maps panels
to shots, carries knowledge entities / rights / provenance, and exports an
adaptation package as JSON or Markdown. Prefixed ``/screen`` so the whole
context stays extractable.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlmodel import Session, func, select

from app.auth import ADMIN_ONLY, AUTHED
from app.db import get_session
from app.models import (
    AdaptationDossier,
    AssetVersion,
    GraphicNovelPanel,
    GraphicNovelProduction,
    KnowledgeEntity,
    Scene,
    SceneCharacterLink,
    ScreenFormat,
    ScreenProject,
    ScreenProjectStatus,
    ScreenSequence,
    ScreenShotAssetLink,
    ScreenShotPanelLink,
    ScreenUnit,
    Shot,
    StudioDivision,
    Work,
)
from app.schemas.adaptation_dossier import AdaptationDossierRead
from app.schemas.screen import (
    DossierPromoteRequest,
    ProjectFromDossierRequest,
    ReferencesRead,
    SceneCharacterCreate,
    SceneCharacterRead,
    SceneCreate,
    SceneDetail,
    SceneRead,
    SceneUpdate,
    ScreenProjectRead,
    ScreenProjectUpdate,
    ScreenSequenceCreate,
    ScreenSequenceRead,
    ScreenSequenceUpdate,
    ScreenUnitCreate,
    ScreenUnitRead,
    ScreenUnitUpdate,
    ShotAssetLinkCreate,
    ShotCreate,
    ShotPanelLinkCreate,
    ShotRead,
    ShotUpdate,
    StoryboardRef,
)
from app.models.enums import AssetApprovalStatus
from app.services import brain
from app.services import graphic_novel as gn
from app.services import screen as screen_service
from app.utils import (
    Page,
    PageParams,
    apply_patch,
    ensure_exists,
    get_or_404,
    page_params,
    paginate,
)

router = APIRouter(prefix="/screen", tags=["screen"])


# --- brain scope resolvers (best-effort; never break the mutation) ---------


def _project_scope(project: ScreenProject) -> tuple[Optional[str], Optional[str]]:
    return (project.source_work_id, project.story_world_id)


def _scene_scope(
    session: Session, scene: Scene
) -> tuple[Optional[str], Optional[str]]:
    seq = session.get(ScreenSequence, scene.sequence_id)
    unit = session.get(ScreenUnit, seq.unit_id) if seq else None
    project = (
        session.get(ScreenProject, unit.screen_project_id) if unit else None
    )
    return _project_scope(project) if project else (None, None)


def _shot_scope(
    session: Session, shot: Shot
) -> tuple[Optional[str], Optional[str]]:
    scene = session.get(Scene, shot.scene_id)
    return _scene_scope(session, scene) if scene else (None, None)


# --- read builders ---------------------------------------------------------


def _shot_read(shot: Shot) -> ShotRead:
    read = ShotRead.model_validate(shot)
    read.mapped_panel_ids = [pl.panel_id for pl in shot.panel_links]
    read.asset_version_ids = [al.asset_version_id for al in shot.asset_links]
    return read


def _scene_read(session: Session, scene: Scene) -> SceneRead:
    read = SceneRead.model_validate(scene)
    read.shot_count = session.exec(
        select(func.count()).select_from(Shot).where(Shot.scene_id == scene.id)
    ).one()
    return read


def _scene_detail(scene: Scene) -> SceneDetail:
    detail = SceneDetail.model_validate(scene)
    detail.shot_count = len(scene.shots)
    detail.shots = [
        _shot_read(s) for s in sorted(scene.shots, key=lambda x: (x.position, x.shot_number))
    ]
    detail.characters = [
        SceneCharacterRead.model_validate(c)
        for c in sorted(scene.character_links, key=lambda x: x.position)
    ]
    return detail


def _child_or_404(child, parent_id: str, attr: str, name: str):
    if getattr(child, attr) != parent_id:
        raise HTTPException(status_code=404, detail=f"{name} not found on this parent")
    return child


# --- promotion + project creation (the seam) -------------------------------


@router.post(
    "/dossiers/promote",
    response_model=AdaptationDossierRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=AUTHED,
    summary="Promote a Work / graphic novel into a Pictures adaptation dossier",
)
def promote_to_dossier(
    payload: DossierPromoteRequest, session: Session = Depends(get_session)
) -> AdaptationDossier:
    ensure_exists(session, Work, payload.source_work_id, name="Work")
    dossier = AdaptationDossier(
        source_work_id=payload.source_work_id,
        target_medium=payload.target_medium,
        target_division=StudioDivision.PICTURES,
        status=payload.status,
        logline=payload.logline,
        format=payload.format,
        intended_scope=payload.intended_scope,
    )
    session.add(dossier)
    session.commit()
    session.refresh(dossier)
    return dossier


@router.post(
    "/projects/from-dossier/{dossier_id}",
    response_model=ScreenProjectRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=AUTHED,
    summary="Create a ScreenProject from an approved dossier",
)
def create_project_from_dossier(
    dossier_id: str,
    payload: ProjectFromDossierRequest,
    session: Session = Depends(get_session),
) -> ScreenProject:
    dossier = get_or_404(session, AdaptationDossier, dossier_id, name="AdaptationDossier")
    project = screen_service.create_project_from_dossier(
        session, dossier, fmt=payload.format, title=payload.title
    )
    work_id, story_world_id = _project_scope(project)
    brain.emit(
        session, event_type=brain.BrainEventType.SCREEN_PROJECT_CREATED,
        aggregate_type="screen_project", aggregate_id=project.id,
        work_id=work_id, story_world_id=story_world_id,
        changes={"title": project.title, "format": project.format.value},
    )
    session.commit()
    session.refresh(project)
    return project


# --- projects --------------------------------------------------------------


@router.get("/projects", response_model=Page[ScreenProjectRead])
def list_projects(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    fmt: Optional[ScreenFormat] = Query(default=None, alias="format"),
    status_: Optional[ScreenProjectStatus] = Query(default=None, alias="status"),
    source_work_id: Optional[str] = Query(default=None),
) -> Page[ScreenProjectRead]:
    stmt = select(ScreenProject)
    if fmt is not None:
        stmt = stmt.where(ScreenProject.format == fmt)
    if status_ is not None:
        stmt = stmt.where(ScreenProject.status == status_)
    if source_work_id is not None:
        stmt = stmt.where(ScreenProject.source_work_id == source_work_id)
    stmt = stmt.order_by(ScreenProject.created_at.desc())
    items, total = paginate(session, stmt, params)
    return Page[ScreenProjectRead](
        items=[ScreenProjectRead.model_validate(p) for p in items],
        total=total, skip=params.skip, limit=params.limit,
    )


@router.get("/projects/{project_id}", response_model=ScreenProjectRead)
def get_project(project_id: str, session: Session = Depends(get_session)) -> ScreenProject:
    return get_or_404(session, ScreenProject, project_id, name="ScreenProject")


@router.patch("/projects/{project_id}", response_model=ScreenProjectRead, dependencies=AUTHED)
def update_project(
    project_id: str, payload: ScreenProjectUpdate, session: Session = Depends(get_session)
) -> ScreenProject:
    project = get_or_404(session, ScreenProject, project_id, name="ScreenProject")
    apply_patch(project, payload)
    session.add(project)
    work_id, story_world_id = _project_scope(project)
    brain.emit(
        session, event_type=brain.BrainEventType.SCREEN_PROJECT_UPDATED,
        aggregate_type="screen_project", aggregate_id=project.id,
        work_id=work_id, story_world_id=story_world_id,
        changes=payload.model_dump(exclude_unset=True),
    )
    session.commit()
    session.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=ADMIN_ONLY)
def delete_project(project_id: str, session: Session = Depends(get_session)):
    project = get_or_404(session, ScreenProject, project_id, name="ScreenProject")
    work_id, story_world_id = _project_scope(project)
    session.delete(project)
    brain.emit(
        session, event_type=brain.BrainEventType.SCREEN_PROJECT_UPDATED,
        aggregate_type="screen_project", aggregate_id=project_id,
        work_id=work_id, story_world_id=story_world_id,
        changes={"deleted": True},
    )
    session.commit()


# --- units -----------------------------------------------------------------


@router.get("/projects/{project_id}/units", response_model=list[ScreenUnitRead])
def list_units(project_id: str, session: Session = Depends(get_session)) -> list[ScreenUnitRead]:
    get_or_404(session, ScreenProject, project_id, name="ScreenProject")
    stmt = (
        select(ScreenUnit).where(ScreenUnit.screen_project_id == project_id)
        .order_by(ScreenUnit.position, ScreenUnit.number)
    )
    return [ScreenUnitRead.model_validate(u) for u in session.exec(stmt).all()]


@router.post("/projects/{project_id}/units", response_model=ScreenUnitRead, status_code=201, dependencies=AUTHED)
def create_unit(
    project_id: str, payload: ScreenUnitCreate, session: Session = Depends(get_session)
) -> ScreenUnitRead:
    get_or_404(session, ScreenProject, project_id, name="ScreenProject")
    unit = ScreenUnit(screen_project_id=project_id, **payload.model_dump())
    session.add(unit)
    session.commit()
    session.refresh(unit)
    return ScreenUnitRead.model_validate(unit)


@router.patch("/units/{unit_id}", response_model=ScreenUnitRead, dependencies=AUTHED)
def update_unit(unit_id: str, payload: ScreenUnitUpdate, session: Session = Depends(get_session)) -> ScreenUnitRead:
    unit = get_or_404(session, ScreenUnit, unit_id, name="ScreenUnit")
    apply_patch(unit, payload)
    session.add(unit)
    session.commit()
    session.refresh(unit)
    return ScreenUnitRead.model_validate(unit)


@router.delete("/units/{unit_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=AUTHED)
def delete_unit(unit_id: str, session: Session = Depends(get_session)):
    unit = get_or_404(session, ScreenUnit, unit_id, name="ScreenUnit")
    session.delete(unit)
    session.commit()


# --- sequences -------------------------------------------------------------


@router.get("/units/{unit_id}/sequences", response_model=list[ScreenSequenceRead])
def list_sequences(unit_id: str, session: Session = Depends(get_session)) -> list[ScreenSequenceRead]:
    get_or_404(session, ScreenUnit, unit_id, name="ScreenUnit")
    stmt = (
        select(ScreenSequence).where(ScreenSequence.unit_id == unit_id)
        .order_by(ScreenSequence.position, ScreenSequence.sequence_number)
    )
    return [ScreenSequenceRead.model_validate(s) for s in session.exec(stmt).all()]


@router.post("/units/{unit_id}/sequences", response_model=ScreenSequenceRead, status_code=201, dependencies=AUTHED)
def create_sequence(
    unit_id: str, payload: ScreenSequenceCreate, session: Session = Depends(get_session)
) -> ScreenSequenceRead:
    get_or_404(session, ScreenUnit, unit_id, name="ScreenUnit")
    seq = ScreenSequence(unit_id=unit_id, **payload.model_dump())
    session.add(seq)
    session.commit()
    session.refresh(seq)
    return ScreenSequenceRead.model_validate(seq)


@router.patch("/sequences/{sequence_id}", response_model=ScreenSequenceRead, dependencies=AUTHED)
def update_sequence(sequence_id: str, payload: ScreenSequenceUpdate, session: Session = Depends(get_session)) -> ScreenSequenceRead:
    seq = get_or_404(session, ScreenSequence, sequence_id, name="ScreenSequence")
    apply_patch(seq, payload)
    session.add(seq)
    session.commit()
    session.refresh(seq)
    return ScreenSequenceRead.model_validate(seq)


@router.delete("/sequences/{sequence_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=AUTHED)
def delete_sequence(sequence_id: str, session: Session = Depends(get_session)):
    seq = get_or_404(session, ScreenSequence, sequence_id, name="ScreenSequence")
    session.delete(seq)
    session.commit()


# --- scenes ----------------------------------------------------------------


@router.get("/sequences/{sequence_id}/scenes", response_model=list[SceneRead])
def list_scenes(sequence_id: str, session: Session = Depends(get_session)) -> list[SceneRead]:
    get_or_404(session, ScreenSequence, sequence_id, name="ScreenSequence")
    stmt = (
        select(Scene).where(Scene.sequence_id == sequence_id)
        .order_by(Scene.position, Scene.scene_number)
    )
    return [_scene_read(session, s) for s in session.exec(stmt).all()]


@router.post("/sequences/{sequence_id}/scenes", response_model=SceneDetail, status_code=201, dependencies=AUTHED)
def create_scene(sequence_id: str, payload: SceneCreate, session: Session = Depends(get_session)) -> SceneDetail:
    get_or_404(session, ScreenSequence, sequence_id, name="ScreenSequence")
    scene = Scene(sequence_id=sequence_id, **payload.model_dump())
    session.add(scene)
    session.flush()
    work_id, story_world_id = _scene_scope(session, scene)
    brain.emit(
        session, event_type=brain.BrainEventType.SCENE_CREATED,
        aggregate_type="scene", aggregate_id=scene.id,
        work_id=work_id, story_world_id=story_world_id,
    )
    session.commit()
    session.refresh(scene)
    return _scene_detail(scene)


@router.get("/scenes/{scene_id}", response_model=SceneDetail)
def get_scene(scene_id: str, session: Session = Depends(get_session)) -> SceneDetail:
    scene = get_or_404(session, Scene, scene_id, name="Scene")
    return _scene_detail(scene)


@router.patch("/scenes/{scene_id}", response_model=SceneDetail, dependencies=AUTHED)
def update_scene(scene_id: str, payload: SceneUpdate, session: Session = Depends(get_session)) -> SceneDetail:
    scene = get_or_404(session, Scene, scene_id, name="Scene")
    apply_patch(scene, payload)
    session.add(scene)
    work_id, story_world_id = _scene_scope(session, scene)
    brain.emit(
        session, event_type=brain.BrainEventType.SCENE_UPDATED,
        aggregate_type="scene", aggregate_id=scene.id,
        work_id=work_id, story_world_id=story_world_id,
        changes=payload.model_dump(exclude_unset=True),
    )
    session.commit()
    session.refresh(scene)
    return _scene_detail(scene)


@router.delete("/scenes/{scene_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=AUTHED)
def delete_scene(scene_id: str, session: Session = Depends(get_session)):
    scene = get_or_404(session, Scene, scene_id, name="Scene")
    work_id, story_world_id = _scene_scope(session, scene)
    session.delete(scene)
    brain.emit(
        session, event_type=brain.BrainEventType.SCENE_UPDATED,
        aggregate_type="scene", aggregate_id=scene_id,
        work_id=work_id, story_world_id=story_world_id,
        changes={"deleted": True},
    )
    session.commit()


@router.get("/scenes/{scene_id}/characters", response_model=list[SceneCharacterRead])
def list_scene_characters(scene_id: str, session: Session = Depends(get_session)) -> list[SceneCharacterRead]:
    scene = get_or_404(session, Scene, scene_id, name="Scene")
    return [SceneCharacterRead.model_validate(c) for c in sorted(scene.character_links, key=lambda x: x.position)]


@router.post("/scenes/{scene_id}/characters", response_model=SceneCharacterRead, status_code=201, dependencies=AUTHED)
def add_scene_character(scene_id: str, payload: SceneCharacterCreate, session: Session = Depends(get_session)) -> SceneCharacterRead:
    get_or_404(session, Scene, scene_id, name="Scene")
    ensure_exists(session, KnowledgeEntity, payload.entity_id, name="KnowledgeEntity")
    link = SceneCharacterLink(scene_id=scene_id, **payload.model_dump())
    session.add(link)
    session.commit()
    session.refresh(link)
    return SceneCharacterRead.model_validate(link)


@router.delete("/scenes/{scene_id}/characters/{link_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=AUTHED)
def remove_scene_character(scene_id: str, link_id: str, session: Session = Depends(get_session)):
    link = get_or_404(session, SceneCharacterLink, link_id, name="SceneCharacterLink")
    _child_or_404(link, scene_id, "scene_id", "Character link")
    session.delete(link)
    session.commit()


# --- shots -----------------------------------------------------------------


@router.get("/scenes/{scene_id}/shots", response_model=list[ShotRead])
def list_shots(scene_id: str, session: Session = Depends(get_session)) -> list[ShotRead]:
    scene = get_or_404(session, Scene, scene_id, name="Scene")
    return [_shot_read(s) for s in sorted(scene.shots, key=lambda x: (x.position, x.shot_number))]


@router.post("/scenes/{scene_id}/shots", response_model=ShotRead, status_code=201, dependencies=AUTHED)
def create_shot(scene_id: str, payload: ShotCreate, session: Session = Depends(get_session)) -> ShotRead:
    get_or_404(session, Scene, scene_id, name="Scene")
    if payload.source_storyboard_panel_id is not None:
        ensure_exists(session, GraphicNovelPanel, payload.source_storyboard_panel_id, name="GraphicNovelPanel")
    shot = Shot(scene_id=scene_id, **payload.model_dump())
    session.add(shot)
    session.flush()
    work_id, story_world_id = _shot_scope(session, shot)
    brain.emit(
        session, event_type=brain.BrainEventType.SHOT_CREATED,
        aggregate_type="shot", aggregate_id=shot.id,
        work_id=work_id, story_world_id=story_world_id,
    )
    session.commit()
    session.refresh(shot)
    return _shot_read(shot)


@router.get("/shots/{shot_id}", response_model=ShotRead)
def get_shot(shot_id: str, session: Session = Depends(get_session)) -> ShotRead:
    shot = get_or_404(session, Shot, shot_id, name="Shot")
    return _shot_read(shot)


@router.patch("/shots/{shot_id}", response_model=ShotRead, dependencies=AUTHED)
def update_shot(shot_id: str, payload: ShotUpdate, session: Session = Depends(get_session)) -> ShotRead:
    shot = get_or_404(session, Shot, shot_id, name="Shot")
    if payload.source_storyboard_panel_id is not None:
        ensure_exists(session, GraphicNovelPanel, payload.source_storyboard_panel_id, name="GraphicNovelPanel")
    prev_approval = shot.approval
    apply_patch(shot, payload)
    session.add(shot)
    work_id, story_world_id = _shot_scope(session, shot)
    brain.emit(
        session, event_type=brain.BrainEventType.SHOT_UPDATED,
        aggregate_type="shot", aggregate_id=shot.id,
        work_id=work_id, story_world_id=story_world_id,
        changes=payload.model_dump(exclude_unset=True),
    )
    if (
        shot.approval == AssetApprovalStatus.APPROVED
        and prev_approval != AssetApprovalStatus.APPROVED
    ):
        brain.emit(
            session, event_type=brain.BrainEventType.SHOT_APPROVED,
            aggregate_type="shot", aggregate_id=shot.id,
            work_id=work_id, story_world_id=story_world_id,
        )
    session.commit()
    session.refresh(shot)
    return _shot_read(shot)


@router.delete("/shots/{shot_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=AUTHED)
def delete_shot(shot_id: str, session: Session = Depends(get_session)):
    shot = get_or_404(session, Shot, shot_id, name="Shot")
    work_id, story_world_id = _shot_scope(session, shot)
    session.delete(shot)
    brain.emit(
        session, event_type=brain.BrainEventType.SHOT_UPDATED,
        aggregate_type="shot", aggregate_id=shot_id,
        work_id=work_id, story_world_id=story_world_id,
        changes={"deleted": True},
    )
    session.commit()


# --- panel ↔ shot mapping & asset links ------------------------------------


@router.post("/shots/{shot_id}/panels", response_model=ShotRead, status_code=201, dependencies=AUTHED)
def map_panel_to_shot(shot_id: str, payload: ShotPanelLinkCreate, session: Session = Depends(get_session)) -> ShotRead:
    shot = get_or_404(session, Shot, shot_id, name="Shot")
    ensure_exists(session, GraphicNovelPanel, payload.panel_id, name="GraphicNovelPanel")
    existing = session.exec(
        select(ScreenShotPanelLink).where(
            ScreenShotPanelLink.shot_id == shot_id,
            ScreenShotPanelLink.panel_id == payload.panel_id,
        )
    ).first()
    if existing is None:
        session.add(ScreenShotPanelLink(shot_id=shot_id, panel_id=payload.panel_id, role=payload.role))
        session.commit()
        session.refresh(shot)
    return _shot_read(shot)


@router.delete("/shots/{shot_id}/panels/{link_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=AUTHED)
def unmap_panel(shot_id: str, link_id: str, session: Session = Depends(get_session)):
    link = get_or_404(session, ScreenShotPanelLink, link_id, name="ScreenShotPanelLink")
    _child_or_404(link, shot_id, "shot_id", "Panel link")
    session.delete(link)
    session.commit()


@router.post("/shots/{shot_id}/assets", response_model=ShotRead, status_code=201, dependencies=AUTHED)
def link_asset_to_shot(shot_id: str, payload: ShotAssetLinkCreate, session: Session = Depends(get_session)) -> ShotRead:
    shot = get_or_404(session, Shot, shot_id, name="Shot")
    ensure_exists(session, AssetVersion, payload.asset_version_id, name="AssetVersion")
    session.add(ScreenShotAssetLink(shot_id=shot_id, asset_version_id=payload.asset_version_id, role=payload.role))
    session.commit()
    session.refresh(shot)
    return _shot_read(shot)


@router.delete("/shots/{shot_id}/assets/{link_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=AUTHED)
def unlink_asset(shot_id: str, link_id: str, session: Session = Depends(get_session)):
    link = get_or_404(session, ScreenShotAssetLink, link_id, name="ScreenShotAssetLink")
    _child_or_404(link, shot_id, "shot_id", "Asset link")
    session.delete(link)
    session.commit()


# --- storyboard references / shot list / breakdown / references / export ----


@router.get("/projects/{project_id}/storyboard", response_model=list[StoryboardRef])
def project_storyboard(project_id: str, session: Session = Depends(get_session)) -> list[StoryboardRef]:
    """Graphic-novel pages/panels of the source work, offered as storyboard
    references to map onto shots."""
    project = get_or_404(session, ScreenProject, project_id, name="ScreenProject")
    refs: list[StoryboardRef] = []
    if project.source_work_id is None:
        return refs
    production = session.exec(
        select(GraphicNovelProduction).where(
            GraphicNovelProduction.work_id == project.source_work_id
        )
    ).first()
    if production is None:
        return refs
    pages = sorted(
        gn.pages_for_production(session, production.id),
        key=lambda p: (p.position, p.page_number),
    )
    for page in pages:
        for panel in sorted(page.panels, key=lambda x: (x.position, x.panel_number)):
            refs.append(
                StoryboardRef(
                    page_id=page.id, page_number=page.page_number,
                    panel_id=panel.id, panel_number=panel.panel_number,
                )
            )
    return refs


@router.get("/projects/{project_id}/shot-list", response_model=list[dict])
def shot_list(project_id: str, session: Session = Depends(get_session)) -> list[dict]:
    project = get_or_404(session, ScreenProject, project_id, name="ScreenProject")
    return screen_service.shot_list(session, project)


@router.get("/projects/{project_id}/breakdown", response_model=dict)
def breakdown(project_id: str, session: Session = Depends(get_session)) -> dict:
    project = get_or_404(session, ScreenProject, project_id, name="ScreenProject")
    return screen_service.production_breakdown(session, project)


@router.get("/projects/{project_id}/references", response_model=ReferencesRead)
def project_references(project_id: str, session: Session = Depends(get_session)) -> ReferencesRead:
    project = get_or_404(session, ScreenProject, project_id, name="ScreenProject")
    return ReferencesRead(**screen_service.references(session, project))


@router.get("/projects/{project_id}/export", summary="Export the adaptation package (JSON or Markdown)")
def export_package(
    project_id: str,
    session: Session = Depends(get_session),
    fmt: Literal["json", "markdown"] = Query(default="json", alias="format"),
):
    project = get_or_404(session, ScreenProject, project_id, name="ScreenProject")
    package = screen_service.export_package(session, project)
    if fmt == "markdown":
        return PlainTextResponse(
            screen_service.package_to_markdown(package), media_type="text/markdown"
        )
    return package
