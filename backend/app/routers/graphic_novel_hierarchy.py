"""The detailed graphic-novel production hierarchy API.

CRUD for Volume → Chapter → Sequence → Page → Panel → element, plus reorder,
duplication, validation, roll-up/progress, print/digital readiness,
storyboard↔final comparison, knowledge-entity links and the deliberate
public-reader curation hand-off. ``GraphicNovelProduction`` stays the high-level
summary and is kept fresh by rolling detailed statuses up into it.

No router prefix: each level reads naturally (``/gn-pages/{id}/panels`` etc.).
The public reader is never written from here.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.auth import AUTHED
from app.db import get_session
from app.models import (
    GraphicNovelChapter,
    GraphicNovelPage,
    GraphicNovelPageEntityLink,
    GraphicNovelPanel,
    GraphicNovelPanelElement,
    GraphicNovelProduction,
    GraphicNovelSequence,
    GraphicNovelVolume,
    KnowledgeEntity,
)
from app.schemas.graphic_novel_hierarchy import (
    ChapterCreate,
    ChapterRead,
    ChapterUpdate,
    ComparisonRow,
    CurationHandoffRead,
    PageCreate,
    PageDetail,
    PageEntityLinkCreate,
    PageEntityLinkRead,
    PageRead,
    PageUpdate,
    PanelCreate,
    PanelDetail,
    PanelElementCreate,
    PanelElementRead,
    PanelElementUpdate,
    PanelUpdate,
    ProductionProgressRead,
    ReadinessRead,
    ReorderRequest,
    SequenceCreate,
    SequenceRead,
    SequenceUpdate,
    TreeNode,
    ValidationIssueRead,
    VolumeCreate,
    VolumeRead,
    VolumeUpdate,
)
from app.services import graphic_novel as gn
from app.utils import apply_patch, ensure_exists, get_or_404

router = APIRouter(tags=["graphic_novel_hierarchy"])


# --- read builders ---------------------------------------------------------


def _panel_detail(panel: GraphicNovelPanel) -> PanelDetail:
    detail = PanelDetail.model_validate(panel)
    detail.elements = [
        PanelElementRead.model_validate(e)
        for e in sorted(panel.elements, key=lambda x: (x.position, x.created_at))
    ]
    return detail


def _page_read(page: GraphicNovelPage) -> PageRead:
    read = PageRead.model_validate(page)
    read.panel_count = len(page.panels)
    return read


def _page_detail(page: GraphicNovelPage) -> PageDetail:
    detail = PageDetail.model_validate(page)
    detail.panel_count = len(page.panels)
    detail.panels = [
        _panel_detail(p)
        for p in sorted(page.panels, key=lambda x: (x.position, x.panel_number))
    ]
    detail.entity_links = [
        PageEntityLinkRead.model_validate(link)
        for link in sorted(page.entity_links, key=lambda x: x.position)
    ]
    return detail


def _production_for_page(session: Session, page: GraphicNovelPage) -> Optional[GraphicNovelProduction]:
    seq = session.get(GraphicNovelSequence, page.sequence_id)
    if seq is None:
        return None
    chapter = session.get(GraphicNovelChapter, seq.chapter_id)
    if chapter is None:
        return None
    volume = session.get(GraphicNovelVolume, chapter.volume_id)
    if volume is None:
        return None
    return session.get(GraphicNovelProduction, volume.production_id)


def _recalc_for_page(session: Session, page: GraphicNovelPage) -> None:
    production = _production_for_page(session, page)
    if production is not None:
        gn.recalculate_production(session, production)


def _child_or_404(child, parent_id: str, parent_attr: str, name: str):
    if getattr(child, parent_attr) != parent_id:
        raise HTTPException(status_code=404, detail=f"{name} not found on this parent")
    return child


# --- Volumes ---------------------------------------------------------------


@router.get(
    "/graphic-novel-productions/{production_id}/volumes",
    response_model=list[VolumeRead],
)
def list_volumes(
    production_id: str, session: Session = Depends(get_session)
) -> list[VolumeRead]:
    get_or_404(session, GraphicNovelProduction, production_id, name="GraphicNovelProduction")
    stmt = (
        select(GraphicNovelVolume)
        .where(GraphicNovelVolume.production_id == production_id)
        .order_by(GraphicNovelVolume.position, GraphicNovelVolume.volume_number)
    )
    return [VolumeRead.model_validate(v) for v in session.exec(stmt).all()]


@router.post(
    "/graphic-novel-productions/{production_id}/volumes",
    response_model=VolumeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=AUTHED,
)
def create_volume(
    production_id: str, payload: VolumeCreate, session: Session = Depends(get_session)
) -> VolumeRead:
    get_or_404(session, GraphicNovelProduction, production_id, name="GraphicNovelProduction")
    volume = GraphicNovelVolume(production_id=production_id, **payload.model_dump())
    session.add(volume)
    session.commit()
    session.refresh(volume)
    return VolumeRead.model_validate(volume)


@router.patch("/gn-volumes/{volume_id}", response_model=VolumeRead, dependencies=AUTHED)
def update_volume(
    volume_id: str, payload: VolumeUpdate, session: Session = Depends(get_session)
) -> VolumeRead:
    volume = get_or_404(session, GraphicNovelVolume, volume_id, name="GraphicNovelVolume")
    apply_patch(volume, payload)
    session.add(volume)
    session.commit()
    session.refresh(volume)
    return VolumeRead.model_validate(volume)


@router.delete("/gn-volumes/{volume_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=AUTHED)
def delete_volume(volume_id: str, session: Session = Depends(get_session)):
    volume = get_or_404(session, GraphicNovelVolume, volume_id, name="GraphicNovelVolume")
    session.delete(volume)
    session.commit()


@router.post(
    "/graphic-novel-productions/{production_id}/volumes/reorder",
    response_model=list[VolumeRead],
    dependencies=AUTHED,
)
def reorder_volumes(
    production_id: str, payload: ReorderRequest, session: Session = Depends(get_session)
) -> list[VolumeRead]:
    volumes = list(
        session.exec(
            select(GraphicNovelVolume).where(
                GraphicNovelVolume.production_id == production_id
            )
        ).all()
    )
    gn.apply_order(volumes, payload.ordered_ids)
    for v in volumes:
        session.add(v)
    session.commit()
    return list_volumes(production_id, session)


# --- Chapters --------------------------------------------------------------


@router.get("/gn-volumes/{volume_id}/chapters", response_model=list[ChapterRead])
def list_chapters(volume_id: str, session: Session = Depends(get_session)) -> list[ChapterRead]:
    get_or_404(session, GraphicNovelVolume, volume_id, name="GraphicNovelVolume")
    stmt = (
        select(GraphicNovelChapter)
        .where(GraphicNovelChapter.volume_id == volume_id)
        .order_by(GraphicNovelChapter.position, GraphicNovelChapter.chapter_number)
    )
    return [ChapterRead.model_validate(c) for c in session.exec(stmt).all()]


@router.post(
    "/gn-volumes/{volume_id}/chapters",
    response_model=ChapterRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=AUTHED,
)
def create_chapter(
    volume_id: str, payload: ChapterCreate, session: Session = Depends(get_session)
) -> ChapterRead:
    get_or_404(session, GraphicNovelVolume, volume_id, name="GraphicNovelVolume")
    chapter = GraphicNovelChapter(volume_id=volume_id, **payload.model_dump())
    session.add(chapter)
    session.commit()
    session.refresh(chapter)
    return ChapterRead.model_validate(chapter)


@router.patch("/gn-chapters/{chapter_id}", response_model=ChapterRead, dependencies=AUTHED)
def update_chapter(
    chapter_id: str, payload: ChapterUpdate, session: Session = Depends(get_session)
) -> ChapterRead:
    chapter = get_or_404(session, GraphicNovelChapter, chapter_id, name="GraphicNovelChapter")
    apply_patch(chapter, payload)
    session.add(chapter)
    session.commit()
    session.refresh(chapter)
    return ChapterRead.model_validate(chapter)


@router.delete("/gn-chapters/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=AUTHED)
def delete_chapter(chapter_id: str, session: Session = Depends(get_session)):
    chapter = get_or_404(session, GraphicNovelChapter, chapter_id, name="GraphicNovelChapter")
    session.delete(chapter)
    session.commit()


@router.post(
    "/gn-volumes/{volume_id}/chapters/reorder",
    response_model=list[ChapterRead],
    dependencies=AUTHED,
)
def reorder_chapters(
    volume_id: str, payload: ReorderRequest, session: Session = Depends(get_session)
) -> list[ChapterRead]:
    chapters = list(
        session.exec(
            select(GraphicNovelChapter).where(GraphicNovelChapter.volume_id == volume_id)
        ).all()
    )
    gn.apply_order(chapters, payload.ordered_ids)
    for c in chapters:
        session.add(c)
    session.commit()
    return list_chapters(volume_id, session)


# --- Sequences -------------------------------------------------------------


@router.get("/gn-chapters/{chapter_id}/sequences", response_model=list[SequenceRead])
def list_sequences(chapter_id: str, session: Session = Depends(get_session)) -> list[SequenceRead]:
    get_or_404(session, GraphicNovelChapter, chapter_id, name="GraphicNovelChapter")
    stmt = (
        select(GraphicNovelSequence)
        .where(GraphicNovelSequence.chapter_id == chapter_id)
        .order_by(GraphicNovelSequence.position, GraphicNovelSequence.sequence_number)
    )
    return [SequenceRead.model_validate(s) for s in session.exec(stmt).all()]


@router.post(
    "/gn-chapters/{chapter_id}/sequences",
    response_model=SequenceRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=AUTHED,
)
def create_sequence(
    chapter_id: str, payload: SequenceCreate, session: Session = Depends(get_session)
) -> SequenceRead:
    get_or_404(session, GraphicNovelChapter, chapter_id, name="GraphicNovelChapter")
    seq = GraphicNovelSequence(chapter_id=chapter_id, **payload.model_dump())
    session.add(seq)
    session.commit()
    session.refresh(seq)
    return SequenceRead.model_validate(seq)


@router.patch("/gn-sequences/{sequence_id}", response_model=SequenceRead, dependencies=AUTHED)
def update_sequence(
    sequence_id: str, payload: SequenceUpdate, session: Session = Depends(get_session)
) -> SequenceRead:
    seq = get_or_404(session, GraphicNovelSequence, sequence_id, name="GraphicNovelSequence")
    apply_patch(seq, payload)
    session.add(seq)
    session.commit()
    session.refresh(seq)
    return SequenceRead.model_validate(seq)


@router.delete("/gn-sequences/{sequence_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=AUTHED)
def delete_sequence(sequence_id: str, session: Session = Depends(get_session)):
    seq = get_or_404(session, GraphicNovelSequence, sequence_id, name="GraphicNovelSequence")
    session.delete(seq)
    session.commit()


@router.post(
    "/gn-chapters/{chapter_id}/sequences/reorder",
    response_model=list[SequenceRead],
    dependencies=AUTHED,
)
def reorder_sequences(
    chapter_id: str, payload: ReorderRequest, session: Session = Depends(get_session)
) -> list[SequenceRead]:
    seqs = list(
        session.exec(
            select(GraphicNovelSequence).where(
                GraphicNovelSequence.chapter_id == chapter_id
            )
        ).all()
    )
    gn.apply_order(seqs, payload.ordered_ids)
    for s in seqs:
        session.add(s)
    session.commit()
    return list_sequences(chapter_id, session)


# --- Pages -----------------------------------------------------------------


@router.get("/gn-sequences/{sequence_id}/pages", response_model=list[PageRead])
def list_pages(sequence_id: str, session: Session = Depends(get_session)) -> list[PageRead]:
    get_or_404(session, GraphicNovelSequence, sequence_id, name="GraphicNovelSequence")
    stmt = (
        select(GraphicNovelPage)
        .where(GraphicNovelPage.sequence_id == sequence_id)
        .order_by(GraphicNovelPage.position, GraphicNovelPage.page_number)
    )
    return [_page_read(p) for p in session.exec(stmt).all()]


@router.post(
    "/gn-sequences/{sequence_id}/pages",
    response_model=PageDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=AUTHED,
)
def create_page(
    sequence_id: str, payload: PageCreate, session: Session = Depends(get_session)
) -> PageDetail:
    get_or_404(session, GraphicNovelSequence, sequence_id, name="GraphicNovelSequence")
    from app.models import Asset

    if payload.master_asset_id is not None:
        ensure_exists(session, Asset, payload.master_asset_id, name="Asset")
    page = GraphicNovelPage(sequence_id=sequence_id, **payload.model_dump())
    session.add(page)
    session.flush()
    _recalc_for_page(session, page)
    session.commit()
    session.refresh(page)
    return _page_detail(page)


@router.get("/gn-pages/{page_id}", response_model=PageDetail)
def get_page(page_id: str, session: Session = Depends(get_session)) -> PageDetail:
    page = get_or_404(session, GraphicNovelPage, page_id, name="GraphicNovelPage")
    return _page_detail(page)


@router.patch("/gn-pages/{page_id}", response_model=PageDetail, dependencies=AUTHED)
def update_page(
    page_id: str, payload: PageUpdate, session: Session = Depends(get_session)
) -> PageDetail:
    page = get_or_404(session, GraphicNovelPage, page_id, name="GraphicNovelPage")
    from app.models import Asset

    if payload.master_asset_id is not None:
        ensure_exists(session, Asset, payload.master_asset_id, name="Asset")
    apply_patch(page, payload)
    session.add(page)
    _recalc_for_page(session, page)
    session.commit()
    session.refresh(page)
    return _page_detail(page)


@router.delete("/gn-pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=AUTHED)
def delete_page(page_id: str, session: Session = Depends(get_session)):
    page = get_or_404(session, GraphicNovelPage, page_id, name="GraphicNovelPage")
    production = _production_for_page(session, page)
    session.delete(page)
    session.flush()
    if production is not None:
        gn.recalculate_production(session, production)
    session.commit()


@router.post(
    "/gn-sequences/{sequence_id}/pages/reorder",
    response_model=list[PageRead],
    dependencies=AUTHED,
)
def reorder_pages(
    sequence_id: str, payload: ReorderRequest, session: Session = Depends(get_session)
) -> list[PageRead]:
    pages = list(
        session.exec(
            select(GraphicNovelPage).where(GraphicNovelPage.sequence_id == sequence_id)
        ).all()
    )
    gn.apply_order(pages, payload.ordered_ids)
    for p in pages:
        session.add(p)
    session.commit()
    return list_pages(sequence_id, session)


@router.post("/gn-pages/{page_id}/duplicate", response_model=PageDetail, dependencies=AUTHED)
def duplicate_page(page_id: str, session: Session = Depends(get_session)) -> PageDetail:
    page = get_or_404(session, GraphicNovelPage, page_id, name="GraphicNovelPage")
    clone = gn.duplicate_page(session, page)
    _recalc_for_page(session, clone)
    session.commit()
    session.refresh(clone)
    return _page_detail(clone)


@router.get("/gn-pages/{page_id}/validate", response_model=list[ValidationIssueRead])
def validate_page(page_id: str, session: Session = Depends(get_session)) -> list[ValidationIssueRead]:
    page = get_or_404(session, GraphicNovelPage, page_id, name="GraphicNovelPage")
    return [ValidationIssueRead(**i.__dict__) for i in gn.validate_panels(page)]


@router.get("/gn-pages/{page_id}/comparison", response_model=list[ComparisonRow])
def page_comparison(page_id: str, session: Session = Depends(get_session)) -> list[ComparisonRow]:
    page = get_or_404(session, GraphicNovelPage, page_id, name="GraphicNovelPage")
    return [ComparisonRow(**row) for row in gn.page_comparison(session, page)]


# --- Page ↔ knowledge-entity links -----------------------------------------


@router.get("/gn-pages/{page_id}/entities", response_model=list[PageEntityLinkRead])
def list_page_entities(page_id: str, session: Session = Depends(get_session)) -> list[PageEntityLinkRead]:
    page = get_or_404(session, GraphicNovelPage, page_id, name="GraphicNovelPage")
    return [
        PageEntityLinkRead.model_validate(link)
        for link in sorted(page.entity_links, key=lambda x: x.position)
    ]


@router.post(
    "/gn-pages/{page_id}/entities",
    response_model=PageEntityLinkRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=AUTHED,
)
def add_page_entity(
    page_id: str, payload: PageEntityLinkCreate, session: Session = Depends(get_session)
) -> PageEntityLinkRead:
    get_or_404(session, GraphicNovelPage, page_id, name="GraphicNovelPage")
    ensure_exists(session, KnowledgeEntity, payload.entity_id, name="KnowledgeEntity")
    link = GraphicNovelPageEntityLink(page_id=page_id, **payload.model_dump())
    session.add(link)
    session.commit()
    session.refresh(link)
    return PageEntityLinkRead.model_validate(link)


@router.delete(
    "/gn-pages/{page_id}/entities/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=AUTHED,
)
def remove_page_entity(page_id: str, link_id: str, session: Session = Depends(get_session)):
    link = get_or_404(session, GraphicNovelPageEntityLink, link_id, name="GraphicNovelPageEntityLink")
    _child_or_404(link, page_id, "page_id", "Entity link")
    session.delete(link)
    session.commit()


# --- Panels ----------------------------------------------------------------


@router.get("/gn-pages/{page_id}/panels", response_model=list[PanelDetail])
def list_panels(page_id: str, session: Session = Depends(get_session)) -> list[PanelDetail]:
    page = get_or_404(session, GraphicNovelPage, page_id, name="GraphicNovelPage")
    return [
        _panel_detail(p)
        for p in sorted(page.panels, key=lambda x: (x.position, x.panel_number))
    ]


@router.post(
    "/gn-pages/{page_id}/panels",
    response_model=PanelDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=AUTHED,
)
def create_panel(
    page_id: str, payload: PanelCreate, session: Session = Depends(get_session)
) -> PanelDetail:
    page = get_or_404(session, GraphicNovelPage, page_id, name="GraphicNovelPage")
    panel = GraphicNovelPanel(page_id=page_id, **payload.model_dump())
    session.add(panel)
    session.flush()
    _recalc_for_page(session, page)
    session.commit()
    session.refresh(panel)
    return _panel_detail(panel)


@router.get("/gn-panels/{panel_id}", response_model=PanelDetail)
def get_panel(panel_id: str, session: Session = Depends(get_session)) -> PanelDetail:
    panel = get_or_404(session, GraphicNovelPanel, panel_id, name="GraphicNovelPanel")
    return _panel_detail(panel)


@router.patch("/gn-panels/{panel_id}", response_model=PanelDetail, dependencies=AUTHED)
def update_panel(
    panel_id: str, payload: PanelUpdate, session: Session = Depends(get_session)
) -> PanelDetail:
    panel = get_or_404(session, GraphicNovelPanel, panel_id, name="GraphicNovelPanel")
    apply_patch(panel, payload)
    session.add(panel)
    page = session.get(GraphicNovelPage, panel.page_id)
    if page is not None:
        _recalc_for_page(session, page)
    session.commit()
    session.refresh(panel)
    return _panel_detail(panel)


@router.delete("/gn-panels/{panel_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=AUTHED)
def delete_panel(panel_id: str, session: Session = Depends(get_session)):
    panel = get_or_404(session, GraphicNovelPanel, panel_id, name="GraphicNovelPanel")
    page = session.get(GraphicNovelPage, panel.page_id)
    session.delete(panel)
    session.flush()
    if page is not None:
        _recalc_for_page(session, page)
    session.commit()


@router.post(
    "/gn-pages/{page_id}/panels/reorder",
    response_model=list[PanelDetail],
    dependencies=AUTHED,
)
def reorder_panels(
    page_id: str, payload: ReorderRequest, session: Session = Depends(get_session)
) -> list[PanelDetail]:
    page = get_or_404(session, GraphicNovelPage, page_id, name="GraphicNovelPage")
    gn.apply_order(list(page.panels), payload.ordered_ids)
    for p in page.panels:
        session.add(p)
    session.commit()
    session.refresh(page)
    return [
        _panel_detail(p)
        for p in sorted(page.panels, key=lambda x: (x.position, x.panel_number))
    ]


@router.post("/gn-panels/{panel_id}/duplicate", response_model=PanelDetail, dependencies=AUTHED)
def duplicate_panel(panel_id: str, session: Session = Depends(get_session)) -> PanelDetail:
    panel = get_or_404(session, GraphicNovelPanel, panel_id, name="GraphicNovelPanel")
    clone = gn.duplicate_panel(session, panel)
    session.commit()
    session.refresh(clone)
    return _panel_detail(clone)


# --- Panel elements --------------------------------------------------------


@router.post(
    "/gn-panels/{panel_id}/elements",
    response_model=PanelElementRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=AUTHED,
)
def add_element(
    panel_id: str, payload: PanelElementCreate, session: Session = Depends(get_session)
) -> PanelElementRead:
    get_or_404(session, GraphicNovelPanel, panel_id, name="GraphicNovelPanel")
    if payload.entity_id is not None:
        ensure_exists(session, KnowledgeEntity, payload.entity_id, name="KnowledgeEntity")
    element = GraphicNovelPanelElement(panel_id=panel_id, **payload.model_dump())
    session.add(element)
    session.commit()
    session.refresh(element)
    return PanelElementRead.model_validate(element)


@router.patch(
    "/gn-panels/{panel_id}/elements/{element_id}",
    response_model=PanelElementRead,
    dependencies=AUTHED,
)
def update_element(
    panel_id: str,
    element_id: str,
    payload: PanelElementUpdate,
    session: Session = Depends(get_session),
) -> PanelElementRead:
    element = get_or_404(session, GraphicNovelPanelElement, element_id, name="GraphicNovelPanelElement")
    _child_or_404(element, panel_id, "panel_id", "Element")
    if payload.entity_id is not None:
        ensure_exists(session, KnowledgeEntity, payload.entity_id, name="KnowledgeEntity")
    apply_patch(element, payload)
    session.add(element)
    session.commit()
    session.refresh(element)
    return PanelElementRead.model_validate(element)


@router.delete(
    "/gn-panels/{panel_id}/elements/{element_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=AUTHED,
)
def delete_element(panel_id: str, element_id: str, session: Session = Depends(get_session)):
    element = get_or_404(session, GraphicNovelPanelElement, element_id, name="GraphicNovelPanelElement")
    _child_or_404(element, panel_id, "panel_id", "Element")
    session.delete(element)
    session.commit()


# --- Production-level: progress / validate / readiness / recalc / tree -----


@router.get(
    "/graphic-novel-productions/{production_id}/progress",
    response_model=ProductionProgressRead,
)
def production_progress(production_id: str, session: Session = Depends(get_session)) -> ProductionProgressRead:
    production = get_or_404(session, GraphicNovelProduction, production_id, name="GraphicNovelProduction")
    return ProductionProgressRead(**gn.production_progress(session, production).__dict__)


@router.get(
    "/graphic-novel-productions/{production_id}/validate",
    response_model=list[ValidationIssueRead],
)
def validate_production(production_id: str, session: Session = Depends(get_session)) -> list[ValidationIssueRead]:
    production = get_or_404(session, GraphicNovelProduction, production_id, name="GraphicNovelProduction")
    return [ValidationIssueRead(**i.__dict__) for i in gn.validate_production(session, production)]


@router.get(
    "/graphic-novel-productions/{production_id}/readiness",
    response_model=ReadinessRead,
)
def production_readiness(production_id: str, session: Session = Depends(get_session)) -> ReadinessRead:
    production = get_or_404(session, GraphicNovelProduction, production_id, name="GraphicNovelProduction")
    return ReadinessRead(**gn.readiness(session, production).__dict__)


@router.post(
    "/graphic-novel-productions/{production_id}/recalculate",
    response_model=ProductionProgressRead,
    dependencies=AUTHED,
)
def recalculate(production_id: str, session: Session = Depends(get_session)) -> ProductionProgressRead:
    production = get_or_404(session, GraphicNovelProduction, production_id, name="GraphicNovelProduction")
    gn.recalculate_production(session, production)
    session.commit()
    session.refresh(production)
    return ProductionProgressRead(**gn.production_progress(session, production).__dict__)


@router.get(
    "/graphic-novel-productions/{production_id}/curation-handoff",
    response_model=CurationHandoffRead,
)
def curation_handoff(
    production_id: str,
    session: Session = Depends(get_session),
    commit: bool = Query(default=False, description="Mark eligible pages ready"),
) -> CurationHandoffRead:
    """Propose pages ready for public-reader curation. Never writes the public
    reader; with ``commit`` it only marks eligible pages READY_FOR_CURATION."""
    production = get_or_404(session, GraphicNovelProduction, production_id, name="GraphicNovelProduction")
    result = gn.curation_handoff(session, production, commit=commit)
    if commit:
        session.commit()
    return CurationHandoffRead(**result.__dict__)


@router.get(
    "/graphic-novel-productions/{production_id}/tree",
    response_model=list[TreeNode],
)
def production_tree(production_id: str, session: Session = Depends(get_session)) -> list[TreeNode]:
    get_or_404(session, GraphicNovelProduction, production_id, name="GraphicNovelProduction")
    volumes = sorted(
        session.exec(
            select(GraphicNovelVolume).where(
                GraphicNovelVolume.production_id == production_id
            )
        ).all(),
        key=lambda v: (v.position, v.volume_number),
    )
    tree: list[TreeNode] = []
    for v in volumes:
        v_node = TreeNode(
            id=v.id, label=v.title or f"Volume {v.volume_number}", kind="volume",
            status=v.status.value, position=v.position,
        )
        for c in sorted(v.chapters, key=lambda x: (x.position, x.chapter_number)):
            c_node = TreeNode(
                id=c.id, label=c.title or f"Chapter {c.chapter_number}", kind="chapter",
                status=c.status.value, position=c.position,
            )
            for s in sorted(c.sequences, key=lambda x: (x.position, x.sequence_number)):
                s_node = TreeNode(
                    id=s.id, label=s.title or f"Sequence {s.sequence_number}",
                    kind="sequence", status=s.status.value, position=s.position,
                )
                for p in sorted(s.pages, key=lambda x: (x.position, x.page_number)):
                    s_node.children.append(
                        TreeNode(
                            id=p.id, label=f"Page {p.page_number}", kind="page",
                            status=p.status.value, position=p.position,
                        )
                    )
                c_node.children.append(s_node)
            v_node.children.append(c_node)
        tree.append(v_node)
    return tree
