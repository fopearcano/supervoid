"""Per-source text extraction for the cold index.

Each extractor pulls ONLY human-readable text + text metadata from a source
entity and returns labelled segments. Binary image data, file bytes, storage
keys, checksums and pure geometry are never extracted — only the text around
them (e.g. an asset's title/description/tags/notes, not its pixels).

Every extractor also resolves the source's project scope (work_id /
story_world_id) and the PermissionScope a reader must hold, so retrieval can
filter by permission before returning anything. Rights and contract extracts are
gated on ``manage_rights`` (strict), everything else on ``view_project``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from sqlmodel import Session, select

from app.models import (
    Asset,
    AssetVersion,
    Contract,
    DecisionRecord,
    EditorialNote,
    KnowledgeEntity,
    Manuscript,
    ManuscriptEntityLink,
    Rights,
    Review,
)
from app.models.enums import (
    BrainMemoryVerification,
    DecisionStatus,
    KnowledgeSourceType,
)

VIEW = "view_project"
RIGHTS = "manage_rights"


@dataclass
class Segment:
    label: str
    text: str


@dataclass
class SourceContent:
    source_ref: str
    permission_scope: str
    segments: list[Segment]
    title: Optional[str] = None
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None
    meta: dict = field(default_factory=dict)


def _seg(label: str, *parts) -> Optional[Segment]:
    text = "\n".join(str(p).strip() for p in parts if p and str(p).strip())
    return Segment(label=label, text=text) if text.strip() else None


def _compact(segments: list[Optional[Segment]]) -> list[Segment]:
    return [s for s in segments if s is not None]


# --- scope resolvers -------------------------------------------------------
def _manuscript_work(session: Session, manuscript_id: Optional[str]) -> Optional[str]:
    if not manuscript_id:
        return None
    m = session.get(Manuscript, manuscript_id)
    return m.work_id if m else None


def _panel_work(session: Session, panel) -> Optional[str]:
    """gn_panel → page → sequence → chapter → volume → production → work."""
    from app.models import (
        GraphicNovelChapter,
        GraphicNovelPage,
        GraphicNovelProduction,
        GraphicNovelSequence,
        GraphicNovelVolume,
    )

    page = session.get(GraphicNovelPage, panel.page_id) if panel.page_id else None
    seq = session.get(GraphicNovelSequence, page.sequence_id) if page else None
    chapter = session.get(GraphicNovelChapter, seq.chapter_id) if seq else None
    volume = session.get(GraphicNovelVolume, chapter.volume_id) if chapter else None
    prod = session.get(GraphicNovelProduction, volume.production_id) if volume else None
    return prod.work_id if prod else None


def _scene_scope(session: Session, scene) -> tuple[Optional[str], Optional[str]]:
    """scene → sequence → unit → screen_project → (source_work_id, story_world_id)."""
    from app.models import ScreenProject, ScreenSequence, ScreenUnit

    seq = session.get(ScreenSequence, scene.sequence_id) if scene.sequence_id else None
    unit = session.get(ScreenUnit, seq.unit_id) if seq else None
    proj = session.get(ScreenProject, unit.screen_project_id) if unit else None
    if not proj:
        return (None, None)
    return (proj.source_work_id, proj.story_world_id)


def _entity_work(session: Session, entity_id: str) -> Optional[str]:
    """A knowledge entity is studio-wide; scope it to the first work it is linked
    to via a manuscript (its primary narrative association). None → not indexed
    (orphan/studio-wide entities stay in hot evidence, not the cold index)."""
    rows = session.exec(
        select(ManuscriptEntityLink.manuscript_id).where(
            ManuscriptEntityLink.entity_id == entity_id
        )
    ).all()
    for mid in rows:
        work_id = _manuscript_work(session, mid)
        if work_id:
            return work_id
    return None


# --- extractors ------------------------------------------------------------
def _extract_manuscript(session: Session, source_id: str) -> Optional[SourceContent]:
    m = session.get(Manuscript, source_id)
    if m is None:
        return None
    return SourceContent(
        source_ref=f"Manuscript · {m.title}",
        permission_scope=VIEW,
        title=m.title,
        work_id=m.work_id,
        segments=_compact([
            _seg("title", m.title, m.subtitle),
            _seg("synopsis", m.synopsis),
            _seg("genre", m.genre),
        ]),
        meta={"status": getattr(m.status, "value", None)},
    )


def _extract_editorial_note(session: Session, source_id: str) -> Optional[SourceContent]:
    n = session.get(EditorialNote, source_id)
    if n is None or not n.body:
        return None
    work_id = n.work_id or _manuscript_work(session, n.manuscript_id)
    return SourceContent(
        source_ref=f"Editorial note · {source_id[:8]}",
        permission_scope=VIEW,
        work_id=work_id,
        segments=_compact([_seg("note", n.body)]),
    )


def _extract_decision(session: Session, source_id: str) -> Optional[SourceContent]:
    d = session.get(DecisionRecord, source_id)
    if d is None or d.status == DecisionStatus.REJECTED:
        return None  # rejected decisions are not evidence
    alts = "\n".join(f"- {a}" for a in (d.alternatives or []) if a)
    return SourceContent(
        source_ref=f"Decision · {d.subject}",
        permission_scope=VIEW,
        title=d.subject,
        work_id=d.work_id,
        story_world_id=d.story_world_id,
        segments=_compact([
            _seg("subject", d.subject),
            _seg("decision", d.decision),
            _seg("rationale", d.rationale),
            _seg("alternatives", alts) if alts else None,
        ]),
        meta={"status": getattr(d.status, "value", None)},
    )


def _extract_project_doc(session: Session, source_id: str) -> Optional[SourceContent]:
    r = session.get(Review, source_id)
    if r is None:
        return None
    work_id = getattr(r, "work_id", None) or _manuscript_work(session, getattr(r, "manuscript_id", None))
    return SourceContent(
        source_ref=f"Review · {source_id[:8]}",
        permission_scope=VIEW,
        work_id=work_id,
        segments=_compact([
            _seg("summary", getattr(r, "summary", None)),
            _seg("report", getattr(r, "written_report", None)),
        ]),
    )


def _extract_knowledge_entity(session: Session, source_id: str) -> Optional[SourceContent]:
    e = session.get(KnowledgeEntity, source_id)
    if e is None:
        return None
    work_id = _entity_work(session, source_id)
    if not work_id:
        return None  # cannot scope safely → skip (avoid cross-project leakage)
    return SourceContent(
        source_ref=f"Entity · {e.name}",
        permission_scope=VIEW,
        title=e.name,
        work_id=work_id,
        segments=_compact([
            _seg("name", e.name),
            _seg("description", e.description),
        ]),
        meta={"slug": getattr(e, "slug", None), "kind": getattr(getattr(e, "kind", None), "value", None)},
    )


def _extract_asset_metadata(session: Session, source_id: str) -> Optional[SourceContent]:
    a = session.get(Asset, source_id)
    if a is None:
        return None
    tags = ", ".join(t for t in (a.tags or []) if t)
    # current version TEXT metadata only — never storage_key / checksum / bytes.
    notes = None
    tech_lines = ""
    if a.current_version_id:
        v = session.get(AssetVersion, a.current_version_id)
        if v is not None:
            notes = v.notes
            tech = v.technical_metadata or {}
            skip = ("checksum", "sha", "hash", "bytes", "size", "storage", "key")
            tech_lines = "\n".join(
                f"{k}: {val}"
                for k, val in tech.items()
                if isinstance(val, (str, int, float, bool))
                and not any(s in str(k).lower() for s in skip)
            )
    return SourceContent(
        source_ref=f"Asset · {a.title}",
        permission_scope=VIEW,
        title=a.title,
        work_id=a.work_id,
        story_world_id=a.story_world_id,
        segments=_compact([
            _seg("title", a.title),
            _seg("description", a.description),
            _seg("tags", tags) if tags else None,
            _seg("notes", notes),
            _seg("technical", tech_lines) if tech_lines else None,
        ]),
        meta={"asset_type": getattr(getattr(a, "asset_type", None), "value", None)},
    )


def _extract_panel(session: Session, source_id: str) -> Optional[SourceContent]:
    from app.models import GraphicNovelPanel

    p = session.get(GraphicNovelPanel, source_id)
    if p is None:
        return None
    work_id = _panel_work(session, p)
    return SourceContent(
        source_ref=f"Panel · {source_id[:8]}",
        permission_scope=VIEW,
        work_id=work_id,
        segments=_compact([
            _seg("script_beat", p.script_beat),
            _seg("dialogue", p.dialogue),
            _seg("captions", p.captions),
            _seg("sound_effects", p.sound_effects),
            _seg("continuity", p.continuity_notes),
        ]),
    )


def _extract_scene(session: Session, source_id: str) -> Optional[SourceContent]:
    from app.models import Scene

    s = session.get(Scene, source_id)
    if s is None:
        return None
    work_id, story_world_id = _scene_scope(session, s)
    return SourceContent(
        source_ref=f"Scene · {(s.heading or source_id[:8])}",
        permission_scope=VIEW,
        title=s.heading,
        work_id=work_id,
        story_world_id=story_world_id,
        segments=_compact([
            _seg("heading", s.heading, s.location),
            _seg("synopsis", s.synopsis),
            _seg("script", s.script_text),
            _seg("continuity", s.continuity_notes),
        ]),
    )


def _extract_conversation_summary(session: Session, source_id: str) -> Optional[SourceContent]:
    from app.models import BrainMemoryItem

    item = session.get(BrainMemoryItem, source_id)
    if item is None:
        return None
    sd = item.structured_data or {}
    # Only APPROVED (verified) conversation compactions are eligible.
    if sd.get("kind") != "conversation_compaction":
        return None
    if item.verification != BrainMemoryVerification.VERIFIED:
        return None
    if not (item.work_id or item.story_world_id):
        return None  # studio/private conversation → not cold-indexed
    return SourceContent(
        source_ref=f"Conversation summary · {source_id[:8]}",
        permission_scope=VIEW,
        work_id=item.work_id,
        story_world_id=item.story_world_id,
        segments=_compact([_seg("summary", item.content)]),
        meta={"conversation_id": item.conversation_id},
    )


def _extract_rights(session: Session, source_id: str) -> Optional[SourceContent]:
    r = session.get(Rights, source_id)
    if r is None:
        return None
    return SourceContent(
        source_ref=f"Rights · {source_id[:8]}",
        permission_scope=RIGHTS,  # strict
        work_id=r.work_id,
        segments=_compact([
            _seg("notes", r.notes),
            _seg("sublicense_terms", r.sublicense_terms),
            _seg("reversion_conditions", r.reversion_conditions),
            _seg("adaptation_constraints", r.adaptation_constraints),
            _seg("merchandising_constraints", r.merchandising_constraints),
        ]),
    )


def _extract_contract(session: Session, source_id: str) -> Optional[SourceContent]:
    c = session.get(Contract, source_id)
    if c is None:
        return None
    work_id = getattr(c, "work_id", None) or _manuscript_work(session, getattr(c, "manuscript_id", None))
    return SourceContent(
        source_ref=f"Contract · {source_id[:8]}",
        permission_scope=RIGHTS,  # strict
        work_id=work_id,
        segments=_compact([
            _seg("terms", c.terms),
            _seg("rights_holder", c.rights_holder),
            _seg("reversion_conditions", c.reversion_conditions),
        ]),
    )


EXTRACTORS: dict[KnowledgeSourceType, Callable[[Session, str], Optional[SourceContent]]] = {
    KnowledgeSourceType.MANUSCRIPT: _extract_manuscript,
    KnowledgeSourceType.EDITORIAL_NOTE: _extract_editorial_note,
    KnowledgeSourceType.DECISION_RATIONALE: _extract_decision,
    KnowledgeSourceType.PROJECT_DOC: _extract_project_doc,
    KnowledgeSourceType.KNOWLEDGE_ENTITY: _extract_knowledge_entity,
    KnowledgeSourceType.ASSET_METADATA: _extract_asset_metadata,
    KnowledgeSourceType.PANEL_DESCRIPTION: _extract_panel,
    KnowledgeSourceType.SCENE_DESCRIPTION: _extract_scene,
    KnowledgeSourceType.CONVERSATION_SUMMARY: _extract_conversation_summary,
    KnowledgeSourceType.RIGHTS_EXTRACT: _extract_rights,
    KnowledgeSourceType.CONTRACT_EXTRACT: _extract_contract,
}


# Domain-event aggregate_type → source type (for async indexing off the outbox).
EVENT_SOURCE_MAP: dict[str, KnowledgeSourceType] = {
    "manuscript": KnowledgeSourceType.MANUSCRIPT,
    "editorial_note": KnowledgeSourceType.EDITORIAL_NOTE,
    "decision": KnowledgeSourceType.DECISION_RATIONALE,
    "review": KnowledgeSourceType.PROJECT_DOC,
    "knowledge_entity": KnowledgeSourceType.KNOWLEDGE_ENTITY,
    "asset": KnowledgeSourceType.ASSET_METADATA,
    "panel": KnowledgeSourceType.PANEL_DESCRIPTION,
    "scene": KnowledgeSourceType.SCENE_DESCRIPTION,
    "rights": KnowledgeSourceType.RIGHTS_EXTRACT,
    "contract": KnowledgeSourceType.CONTRACT_EXTRACT,
    "brain_memory": KnowledgeSourceType.CONVERSATION_SUMMARY,
}


def extract(session: Session, source_type: KnowledgeSourceType, source_id: str) -> Optional[SourceContent]:
    fn = EXTRACTORS.get(source_type)
    if fn is None:
        return None
    content = fn(session, source_id)
    if content is None:
        return None
    # Drop empty extractions (nothing text-bearing to index).
    content.segments = [s for s in content.segments if s.text.strip()]
    return content if content.segments else None


def enumerate_sources(session: Session, source_type: KnowledgeSourceType) -> list[str]:
    """All source ids of a type (for backfill / admin reindex)."""
    if source_type == KnowledgeSourceType.MANUSCRIPT:
        return list(session.exec(select(Manuscript.id)).all())
    if source_type == KnowledgeSourceType.EDITORIAL_NOTE:
        return list(session.exec(select(EditorialNote.id)).all())
    if source_type == KnowledgeSourceType.DECISION_RATIONALE:
        return list(session.exec(
            select(DecisionRecord.id).where(DecisionRecord.status != DecisionStatus.REJECTED)
        ).all())
    if source_type == KnowledgeSourceType.PROJECT_DOC:
        return list(session.exec(select(Review.id)).all())
    if source_type == KnowledgeSourceType.KNOWLEDGE_ENTITY:
        return list(session.exec(select(KnowledgeEntity.id)).all())
    if source_type == KnowledgeSourceType.ASSET_METADATA:
        return list(session.exec(select(Asset.id)).all())
    if source_type == KnowledgeSourceType.PANEL_DESCRIPTION:
        from app.models import GraphicNovelPanel
        return list(session.exec(select(GraphicNovelPanel.id)).all())
    if source_type == KnowledgeSourceType.SCENE_DESCRIPTION:
        from app.models import Scene
        return list(session.exec(select(Scene.id)).all())
    if source_type == KnowledgeSourceType.CONVERSATION_SUMMARY:
        from app.models import BrainMemoryItem
        return list(session.exec(
            select(BrainMemoryItem.id).where(
                BrainMemoryItem.verification == BrainMemoryVerification.VERIFIED
            )
        ).all())
    if source_type == KnowledgeSourceType.RIGHTS_EXTRACT:
        return list(session.exec(select(Rights.id)).all())
    if source_type == KnowledgeSourceType.CONTRACT_EXTRACT:
        return list(session.exec(select(Contract.id)).all())
    return []
