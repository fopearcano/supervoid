"""Graphic-novel hierarchy logic: status roll-up into the high-level
``GraphicNovelProduction`` summary, completion percentages, page/spread
validation, print/digital readiness, duplication, reordering, storyboard↔final
comparison, and the deliberate public-reader curation hand-off.

The public reader is never written here — the hand-off only proposes / marks
curation state; an editor performs the actual publish separately.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlmodel import Session, select

from app.models import (
    AssetApprovalStatus,
    AssetVersion,
    CurationStatus,
    GNStatus,
    GraphicNovelChapter,
    GraphicNovelPage,
    GraphicNovelPageEntityLink,
    GraphicNovelPanel,
    GraphicNovelPanelElement,
    GraphicNovelProduction,
    GraphicNovelSequence,
    GraphicNovelVolume,
    PageSide,
    StreamStatus,
)

_EPS = 1e-6


# --- traversal helpers -----------------------------------------------------


def pages_for_production(session: Session, production_id: str) -> list[GraphicNovelPage]:
    stmt = (
        select(GraphicNovelPage)
        .join(GraphicNovelSequence, GraphicNovelPage.sequence_id == GraphicNovelSequence.id)
        .join(GraphicNovelChapter, GraphicNovelSequence.chapter_id == GraphicNovelChapter.id)
        .join(GraphicNovelVolume, GraphicNovelChapter.volume_id == GraphicNovelVolume.id)
        .where(GraphicNovelVolume.production_id == production_id)
    )
    return list(session.exec(stmt).all())


def panels_for_pages(
    session: Session, page_ids: list[str]
) -> list[GraphicNovelPanel]:
    if not page_ids:
        return []
    return list(
        session.exec(
            select(GraphicNovelPanel).where(GraphicNovelPanel.page_id.in_(page_ids))
        ).all()
    )


# --- status roll-up --------------------------------------------------------


def _aggregate_stream(values: list[StreamStatus]) -> StreamStatus:
    """Aggregate child stream statuses into a parent status."""
    if not values:
        return StreamStatus.NOT_PLANNED
    if any(v == StreamStatus.BLOCKED for v in values):
        return StreamStatus.BLOCKED
    if all(v == StreamStatus.COMPLETE for v in values):
        return StreamStatus.COMPLETE
    if all(v == StreamStatus.NOT_PLANNED for v in values):
        return StreamStatus.NOT_PLANNED
    if any(v in (StreamStatus.IN_PROGRESS, StreamStatus.COMPLETE) for v in values):
        return StreamStatus.IN_PROGRESS
    return StreamStatus.PENDING


def _presence_stream(present: list[bool]) -> StreamStatus:
    if not present:
        return StreamStatus.NOT_PLANNED
    if all(present):
        return StreamStatus.COMPLETE
    if any(present):
        return StreamStatus.IN_PROGRESS
    return StreamStatus.PENDING


def recalculate_production(
    session: Session, production: GraphicNovelProduction
) -> GraphicNovelProduction:
    """Roll detailed page/panel statuses up into the summary's stream fields.

    Caller commits.
    """
    pages = pages_for_production(session, production.id)
    panels = panels_for_pages(session, [p.id for p in pages])

    production.lettering_status = _aggregate_stream([p.lettering_status for p in pages])
    production.coloring_status = _aggregate_stream([p.colour_status for p in pages])
    production.final_files_status = _aggregate_stream([p.final_status for p in pages])
    production.script_status = _presence_stream(
        [bool(p.script and p.script.strip()) for p in pages]
    )
    production.page_layout_status = _presence_stream(
        [p.status == GNStatus.COMPLETE for p in pages]
    )
    production.storyboard_status = _presence_stream(
        [panel.storyboard_asset_version_id is not None for panel in panels]
    )
    session.add(production)
    return production


# --- completion percentages ------------------------------------------------


@dataclass
class ProductionProgress:
    pages_total: int = 0
    pages_complete: int = 0
    panels_total: int = 0
    panels_approved: int = 0
    lettering_complete: int = 0
    colour_complete: int = 0
    final_complete: int = 0
    overall_pct: float = 0.0
    panel_approval_pct: float = 0.0


def production_progress(
    session: Session, production: GraphicNovelProduction
) -> ProductionProgress:
    pages = pages_for_production(session, production.id)
    panels = panels_for_pages(session, [p.id for p in pages])

    prog = ProductionProgress()
    prog.pages_total = len(pages)
    prog.panels_total = len(panels)
    prog.panels_approved = sum(
        1 for p in panels if p.approval_status == AssetApprovalStatus.APPROVED
    )
    prog.lettering_complete = sum(
        1 for p in pages if p.lettering_status == StreamStatus.COMPLETE
    )
    prog.colour_complete = sum(
        1 for p in pages if p.colour_status == StreamStatus.COMPLETE
    )
    prog.final_complete = sum(
        1 for p in pages if p.final_status == StreamStatus.COMPLETE
    )
    prog.pages_complete = prog.final_complete

    # Overall = mean of each page's three-stream completion fraction.
    if pages:
        per_page = []
        for p in pages:
            done = sum(
                1
                for s in (p.lettering_status, p.colour_status, p.final_status)
                if s == StreamStatus.COMPLETE
            )
            per_page.append(done / 3)
        prog.overall_pct = round(100 * sum(per_page) / len(per_page), 1)
    if panels:
        prog.panel_approval_pct = round(100 * prog.panels_approved / len(panels), 1)
    return prog


# --- validation ------------------------------------------------------------


@dataclass
class ValidationIssue:
    level: str  # "page" | "panel" | "spread"
    target_id: str
    message: str


def validate_panels(page: GraphicNovelPage) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen_numbers: set[int] = set()
    for panel in page.panels:
        if panel.width <= 0 or panel.height <= 0:
            issues.append(ValidationIssue("panel", panel.id, "Panel has zero area."))
        if panel.x < -_EPS or panel.y < -_EPS:
            issues.append(ValidationIssue("panel", panel.id, "Panel origin is off-page."))
        if panel.x + panel.width > 1 + _EPS or panel.y + panel.height > 1 + _EPS:
            issues.append(
                ValidationIssue("panel", panel.id, "Panel extends beyond page bounds.")
            )
        if panel.panel_number in seen_numbers:
            issues.append(
                ValidationIssue(
                    "panel", panel.id, f"Duplicate panel number {panel.panel_number}."
                )
            )
        seen_numbers.add(panel.panel_number)
    return issues


def validate_production(
    session: Session, production: GraphicNovelProduction
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    pages = pages_for_production(session, production.id)

    # Panel-level checks (load panels via relationship).
    for page in pages:
        issues.extend(validate_panels(page))

    # Page-number duplicates within a sequence.
    by_sequence: dict[str, list[GraphicNovelPage]] = {}
    for page in pages:
        by_sequence.setdefault(page.sequence_id, []).append(page)
    for seq_pages in by_sequence.values():
        seen: set[int] = set()
        for page in seq_pages:
            if page.page_number in seen:
                issues.append(
                    ValidationIssue(
                        "page", page.id, f"Duplicate page number {page.page_number}."
                    )
                )
            seen.add(page.page_number)

    # Spread integrity: a spread must have exactly two pages, one LEFT + one RIGHT.
    by_spread: dict[str, list[GraphicNovelPage]] = {}
    for page in pages:
        if page.spread_id:
            by_spread.setdefault(page.spread_id, []).append(page)
        elif page.page_side != PageSide.SINGLE:
            issues.append(
                ValidationIssue(
                    "page", page.id, "Page has a side but no spread membership."
                )
            )
    for spread_id, members in by_spread.items():
        if len(members) != 2:
            issues.append(
                ValidationIssue(
                    "spread", spread_id, f"Spread has {len(members)} page(s); expected 2."
                )
            )
        sides = {m.page_side for m in members}
        if sides != {PageSide.LEFT, PageSide.RIGHT}:
            issues.append(
                ValidationIssue(
                    "spread", spread_id, "Spread pages must be one LEFT and one RIGHT."
                )
            )
    return issues


# --- print / digital readiness ---------------------------------------------


@dataclass
class Readiness:
    print_ready: bool = False
    digital_ready: bool = False
    print_issues: list[str] = field(default_factory=list)
    digital_issues: list[str] = field(default_factory=list)


def readiness(session: Session, production: GraphicNovelProduction) -> Readiness:
    pages = pages_for_production(session, production.id)
    out = Readiness()
    if not pages:
        out.print_issues.append("No pages in production.")
        out.digital_issues.append("No pages in production.")
        return out

    for page in pages:
        ref = f"page {page.page_number}"
        if page.final_status != StreamStatus.COMPLETE:
            out.print_issues.append(f"{ref}: final art not complete.")
            out.digital_issues.append(f"{ref}: final art not complete.")
        if page.master_asset_id is None:
            out.print_issues.append(f"{ref}: no master asset.")
            out.digital_issues.append(f"{ref}: no master asset.")
        if page.colour_status != StreamStatus.COMPLETE:
            out.print_issues.append(f"{ref}: colour not complete.")
        if None in (
            page.print_width_mm,
            page.print_height_mm,
            page.bleed_mm,
            page.safe_area_mm,
        ):
            out.print_issues.append(f"{ref}: print geometry incomplete.")

    out.print_ready = not out.print_issues
    out.digital_ready = not out.digital_issues
    return out


# --- duplication -----------------------------------------------------------


def _next_number_and_position(items, number_attr: str) -> tuple[int, int]:
    if not items:
        return 1, 0
    max_number = max(getattr(i, number_attr) for i in items)
    max_position = max(i.position for i in items)
    return max_number + 1, max_position + 1


def duplicate_panel(
    session: Session, panel: GraphicNovelPanel, *, page: Optional[GraphicNovelPage] = None
) -> GraphicNovelPanel:
    page = page or session.get(GraphicNovelPage, panel.page_id)
    number, position = _next_number_and_position(page.panels, "panel_number")
    clone = GraphicNovelPanel(
        page_id=page.id,
        panel_number=number,
        position=position,
        status=GNStatus.PLANNED,
        x=panel.x,
        y=panel.y,
        width=panel.width,
        height=panel.height,
        script_beat=panel.script_beat,
        dialogue=panel.dialogue,
        captions=panel.captions,
        sound_effects=panel.sound_effects,
        camera_framing=panel.camera_framing,
        camera_angle=panel.camera_angle,
        lens_metadata=panel.lens_metadata,
        continuity_notes=panel.continuity_notes,
        approval_status=AssetApprovalStatus.DRAFT,
    )
    session.add(clone)
    session.flush()
    for el in panel.elements:
        session.add(
            GraphicNovelPanelElement(
                panel_id=clone.id,
                element_type=el.element_type,
                position=el.position,
                entity_id=el.entity_id,
                text_content=el.text_content,
                asset_version_id=el.asset_version_id,
                label=el.label,
                x=el.x,
                y=el.y,
                width=el.width,
                height=el.height,
            )
        )
    return clone


def duplicate_page(session: Session, page: GraphicNovelPage) -> GraphicNovelPage:
    sequence = session.get(GraphicNovelSequence, page.sequence_id)
    number, position = _next_number_and_position(sequence.pages, "page_number")
    clone = GraphicNovelPage(
        sequence_id=page.sequence_id,
        page_number=number,
        position=position,
        status=GNStatus.PLANNED,
        page_side=PageSide.SINGLE,  # a copy is not part of the original spread
        script=page.script,
        visual_brief=page.visual_brief,
        dialogue_summary=page.dialogue_summary,
        print_width_mm=page.print_width_mm,
        print_height_mm=page.print_height_mm,
        bleed_mm=page.bleed_mm,
        safe_area_mm=page.safe_area_mm,
        # Reset production progress and curation/public mapping on the copy.
        lettering_status=StreamStatus.NOT_PLANNED,
        colour_status=StreamStatus.NOT_PLANNED,
        final_status=StreamStatus.NOT_PLANNED,
        master_asset_id=page.master_asset_id,
        curation_status=CurationStatus.NOT_READY,
        published_page_id=None,
    )
    session.add(clone)
    session.flush()
    for panel in page.panels:
        duplicate_panel(session, panel, page=clone)
    for link in page.entity_links:
        session.add(
            GraphicNovelPageEntityLink(
                page_id=clone.id,
                entity_id=link.entity_id,
                role=link.role,
                position=link.position,
            )
        )
    return clone


# --- reordering ------------------------------------------------------------


def apply_order(items, ordered_ids: list[str]) -> int:
    """Assign ``position`` by the index of each id in ``ordered_ids``. Items not
    listed keep a position after the listed ones. Returns the number reordered."""
    index = {oid: i for i, oid in enumerate(ordered_ids)}
    tail = len(ordered_ids)
    reordered = 0
    for item in items:
        if item.id in index:
            item.position = index[item.id]
            reordered += 1
        else:
            item.position = tail
            tail += 1
    return reordered


# --- storyboard ↔ final comparison ----------------------------------------


def _version_brief(session: Session, version_id: Optional[str]) -> Optional[dict]:
    if not version_id:
        return None
    version = session.get(AssetVersion, version_id)
    if version is None:
        return None
    return {
        "id": version.id,
        "asset_id": version.asset_id,
        "version_number": version.version_number,
        "mime_type": version.mime_type,
        "approval_status": version.approval_status.value,
        "storage_key": version.storage_key,
    }


def page_comparison(session: Session, page: GraphicNovelPage) -> list[dict]:
    rows: list[dict] = []
    for panel in sorted(page.panels, key=lambda p: (p.position, p.panel_number)):
        rows.append(
            {
                "panel_id": panel.id,
                "panel_number": panel.panel_number,
                "storyboard": _version_brief(session, panel.storyboard_asset_version_id),
                "final": _version_brief(session, panel.final_asset_version_id),
            }
        )
    return rows


# --- curation hand-off (never writes the public reader) --------------------


@dataclass
class CurationHandoff:
    committed: bool = False
    eligible: list[dict] = field(default_factory=list)
    ineligible: list[dict] = field(default_factory=list)


def curation_handoff(
    session: Session,
    production: GraphicNovelProduction,
    *,
    commit: bool = False,
) -> CurationHandoff:
    """Propose which pages are ready for public-reader curation. This NEVER
    creates public records; with ``commit`` it only marks eligible pages
    ``READY_FOR_CURATION`` so an editor can pick them up."""
    pages = sorted(
        pages_for_production(session, production.id),
        key=lambda p: (p.position, p.page_number),
    )
    out = CurationHandoff(committed=commit)
    for page in pages:
        reasons: list[str] = []
        if page.final_status != StreamStatus.COMPLETE:
            reasons.append("final art not complete")
        if page.master_asset_id is None:
            reasons.append("no master asset")
        entry = {"page_id": page.id, "page_number": page.page_number}
        if reasons:
            out.ineligible.append({**entry, "reasons": reasons})
        else:
            out.eligible.append(entry)
            if commit and page.curation_status in (
                CurationStatus.NOT_READY,
                CurationStatus.READY_FOR_CURATION,
            ):
                page.curation_status = CurationStatus.READY_FOR_CURATION
                session.add(page)
    return out
