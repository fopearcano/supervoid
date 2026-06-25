"""Work-level production templates.

A template is a reusable production breakdown — an ordered set of milestones and
tasks (with tracks, types, priorities, relative due dates and dependencies) for
a kind of project. Applying a template to a Work instantiates real
``ProductionItem`` tasks, ``ProductionMilestone``s and ``ProductionDependency``
edges, wired together.

Templates are declarative data (below); :func:`instantiate_template` turns one
into persisted rows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlmodel import Session

from app.models import (
    DependencyType,
    ProductionActivityType,
    ProductionDependency,
    ProductionItem,
    ProductionItemStatus,
    ProductionMilestone,
    ProductionPriority,
    ProductionTaskType,
    ProductionTrack,
    StudioDivision,
)
from app.services import production as production_service

_T = ProductionTrack
_P = ProductionPriority
_TY = ProductionTaskType


@dataclass(frozen=True)
class TemplateMilestone:
    key: str
    title: str
    offset_days: int = 0


@dataclass(frozen=True)
class TemplateTask:
    key: str
    title: str
    track: ProductionTrack
    task_type: ProductionTaskType = _TY.TASK
    priority: ProductionPriority = _P.MEDIUM
    offset_days: int = 0
    milestone: Optional[str] = None
    depends_on: tuple[str, ...] = ()
    acceptance_criteria: Optional[str] = None


@dataclass(frozen=True)
class ProductionTemplate:
    key: str
    name: str
    division: StudioDivision
    description: str
    milestones: tuple[TemplateMilestone, ...]
    tasks: tuple[TemplateTask, ...]


def _tpl(**kw) -> ProductionTemplate:
    return ProductionTemplate(**kw)


TEMPLATES: dict[str, ProductionTemplate] = {
    "graphic_novel_volume": _tpl(
        key="graphic_novel_volume",
        name="Graphic novel volume",
        division=StudioDivision.PUBLISHING,
        description="Script → art → letters/colour → prepress → print for one volume.",
        milestones=(
            TemplateMilestone("script_lock", "Script lock", 14),
            TemplateMilestone("art_complete", "Art complete", 70),
            TemplateMilestone("print_ready", "Print ready", 90),
        ),
        tasks=(
            TemplateTask("script", "Write script", _T.SCRIPT, priority=_P.HIGH,
                         offset_days=14, milestone="script_lock"),
            TemplateTask("thumbnails", "Thumbnails / layouts", _T.LAYOUT,
                         offset_days=28, depends_on=("script",)),
            TemplateTask("pencils", "Pencils", _T.ART, offset_days=49,
                         depends_on=("thumbnails",)),
            TemplateTask("inks", "Inks", _T.ART, offset_days=63,
                         depends_on=("pencils",), milestone="art_complete"),
            TemplateTask("letters", "Lettering", _T.LETTERING, offset_days=77,
                         depends_on=("inks",)),
            TemplateTask("colors", "Colouring", _T.COLOR, offset_days=77,
                         depends_on=("inks",)),
            TemplateTask("cover", "Cover art", _T.ART, offset_days=70),
            TemplateTask("prepress", "Prepress", _T.PREPRESS, offset_days=86,
                         depends_on=("letters", "colors", "cover"),
                         milestone="print_ready"),
            TemplateTask("print", "Print run", _T.PRINT, task_type=_TY.DELIVERABLE,
                         priority=_P.HIGH, offset_days=90, depends_on=("prepress",),
                         acceptance_criteria="Bound proof approved; files at printer."),
        ),
    ),
    "book_publication": _tpl(
        key="book_publication",
        name="Book publication",
        division=StudioDivision.PUBLISHING,
        description="Copyedit → proof → layout → cover → prepress → on sale.",
        milestones=(
            TemplateMilestone("manuscript_final", "Manuscript final", 30),
            TemplateMilestone("design_complete", "Design complete", 60),
            TemplateMilestone("on_sale", "On sale", 90),
        ),
        tasks=(
            TemplateTask("copyedit", "Copyedit", _T.EDITORIAL, priority=_P.HIGH,
                         offset_days=21),
            TemplateTask("proofread", "Proofread", _T.EDITORIAL, offset_days=30,
                         depends_on=("copyedit",), milestone="manuscript_final"),
            TemplateTask("layout", "Interior layout", _T.LAYOUT, offset_days=45,
                         depends_on=("proofread",)),
            TemplateTask("cover", "Cover design", _T.DESIGN, offset_days=45),
            TemplateTask("prepress", "Prepress", _T.PREPRESS, offset_days=60,
                         depends_on=("layout", "cover"), milestone="design_complete"),
            TemplateTask("print", "Print & bind", _T.PRINT, task_type=_TY.DELIVERABLE,
                         priority=_P.HIGH, offset_days=85, depends_on=("prepress",),
                         milestone="on_sale"),
            TemplateTask("marketing", "Launch marketing plan", _T.MARKETING,
                         offset_days=75),
        ),
    ),
    "short_film": _tpl(
        key="short_film",
        name="Short film",
        division=StudioDivision.PICTURES,
        description="Script → boards → shoot → edit → sound/colour → delivery.",
        milestones=(
            TemplateMilestone("pre_production", "Pre-production", 21),
            TemplateMilestone("wrap", "Wrap", 45),
            TemplateMilestone("delivery", "Delivery", 75),
        ),
        tasks=(
            TemplateTask("script", "Lock script", _T.SCRIPT, priority=_P.HIGH,
                         offset_days=14, milestone="pre_production"),
            TemplateTask("storyboard", "Storyboard / shot list", _T.STORYBOARD,
                         offset_days=21, depends_on=("script",)),
            TemplateTask("shoot", "Principal photography", _T.PRODUCTION,
                         priority=_P.HIGH, offset_days=45, depends_on=("storyboard",),
                         milestone="wrap"),
            TemplateTask("edit", "Picture edit", _T.EDITING, offset_days=58,
                         depends_on=("shoot",)),
            TemplateTask("sound", "Sound design", _T.SOUND, offset_days=68,
                         depends_on=("edit",)),
            TemplateTask("grade", "Colour grade", _T.COLOR, offset_days=68,
                         depends_on=("edit",)),
            TemplateTask("master", "Final master", _T.EDITING,
                         task_type=_TY.DELIVERABLE, priority=_P.HIGH, offset_days=75,
                         depends_on=("sound", "grade"), milestone="delivery",
                         acceptance_criteria="Approved master in delivery spec."),
        ),
    ),
    "feature_film": _tpl(
        key="feature_film",
        name="Feature film",
        division=StudioDivision.PICTURES,
        description="Development → photography → post (edit/VFX/sound/score) → delivery.",
        milestones=(
            TemplateMilestone("development", "Development", 60),
            TemplateMilestone("photography", "Principal photography", 150),
            TemplateMilestone("post", "Post-production", 240),
            TemplateMilestone("delivery", "Delivery", 300),
        ),
        tasks=(
            TemplateTask("screenplay", "Final screenplay", _T.SCRIPT, priority=_P.HIGH,
                         offset_days=45, milestone="development"),
            TemplateTask("boards", "Storyboards", _T.STORYBOARD, offset_days=90,
                         depends_on=("screenplay",)),
            TemplateTask("design", "Production design", _T.DESIGN, offset_days=90,
                         depends_on=("screenplay",)),
            TemplateTask("photography", "Principal photography", _T.PRODUCTION,
                         priority=_P.CRITICAL, offset_days=150,
                         depends_on=("boards", "design"), milestone="photography"),
            TemplateTask("editorial", "Editorial / picture lock", _T.EDITING,
                         priority=_P.HIGH, offset_days=210, depends_on=("photography",),
                         milestone="post"),
            TemplateTask("vfx", "Visual effects", _T.VFX, offset_days=255,
                         depends_on=("photography",)),
            TemplateTask("sound", "Sound design", _T.SOUND, offset_days=240,
                         depends_on=("editorial",)),
            TemplateTask("score", "Music score", _T.MUSIC, offset_days=240,
                         depends_on=("editorial",)),
            TemplateTask("grade", "Colour grade", _T.COLOR, offset_days=255,
                         depends_on=("editorial",)),
            TemplateTask("master", "Final mix & master", _T.SOUND,
                         task_type=_TY.DELIVERABLE, priority=_P.HIGH, offset_days=300,
                         depends_on=("vfx", "sound", "score", "grade"),
                         milestone="delivery"),
        ),
    ),
    "animated_sequence": _tpl(
        key="animated_sequence",
        name="Animated sequence",
        division=StudioDivision.PICTURES,
        description="Boards → design → layout → animation → lighting/VFX → final.",
        milestones=(
            TemplateMilestone("design_lock", "Design lock", 21),
            TemplateMilestone("animation_complete", "Animation complete", 60),
            TemplateMilestone("final", "Final", 80),
        ),
        tasks=(
            TemplateTask("boards", "Storyboard", _T.STORYBOARD, priority=_P.HIGH,
                         offset_days=10),
            TemplateTask("design", "Character / environment design", _T.DESIGN,
                         offset_days=21, depends_on=("boards",),
                         milestone="design_lock"),
            TemplateTask("animatic", "Animatic", _T.EDITING, offset_days=24,
                         depends_on=("boards",)),
            TemplateTask("layout", "Layout", _T.LAYOUT, offset_days=35,
                         depends_on=("design",)),
            TemplateTask("animation", "Animation", _T.ANIMATION, priority=_P.HIGH,
                         offset_days=60, depends_on=("layout", "animatic"),
                         milestone="animation_complete"),
            TemplateTask("lighting", "Lighting", _T.ART, offset_days=70,
                         depends_on=("animation",)),
            TemplateTask("comp", "VFX / compositing", _T.VFX, offset_days=74,
                         depends_on=("animation",)),
            TemplateTask("sound", "Sound", _T.SOUND, offset_days=70),
            TemplateTask("final", "Final comp & render", _T.VFX,
                         task_type=_TY.DELIVERABLE, priority=_P.HIGH, offset_days=80,
                         depends_on=("lighting", "comp", "sound"), milestone="final"),
        ),
    ),
    "promotional_launch": _tpl(
        key="promotional_launch",
        name="Promotional launch",
        division=StudioDivision.CROSS_MEDIA,
        description="Key art → trailer/press/social → landing → launch → report.",
        milestones=(
            TemplateMilestone("assets_ready", "Assets ready", 21),
            TemplateMilestone("campaign_live", "Campaign live", 35),
        ),
        tasks=(
            TemplateTask("key_art", "Key art", _T.DESIGN, priority=_P.HIGH,
                         offset_days=10),
            TemplateTask("trailer", "Trailer / teaser", _T.EDITING, offset_days=18),
            TemplateTask("press_kit", "Press kit", _T.MARKETING, offset_days=18,
                         depends_on=("key_art",)),
            TemplateTask("social", "Social assets", _T.DESIGN, offset_days=21,
                         depends_on=("key_art",), milestone="assets_ready"),
            TemplateTask("landing", "Landing page", _T.ENGINEERING, offset_days=28),
            TemplateTask("launch", "Launch event", _T.PRODUCTION, priority=_P.HIGH,
                         offset_days=35, depends_on=("press_kit", "social", "trailer"),
                         milestone="campaign_live"),
            TemplateTask("report", "Post-launch report", _T.MARKETING, offset_days=49,
                         depends_on=("launch",)),
        ),
    ),
}


def list_templates() -> list[ProductionTemplate]:
    return list(TEMPLATES.values())


def get_template(key: str) -> Optional[ProductionTemplate]:
    return TEMPLATES.get(key)


@dataclass
class InstantiationResult:
    template_key: str
    milestone_ids: list[str] = field(default_factory=list)
    task_ids: list[str] = field(default_factory=list)
    dependency_ids: list[str] = field(default_factory=list)


def instantiate_template(
    session: Session,
    template: ProductionTemplate,
    *,
    work_id: str,
    actor_id: Optional[str] = None,
    base_date: Optional[date] = None,
    story_world_id: Optional[str] = None,
) -> InstantiationResult:
    """Create the milestones, tasks and dependencies of ``template`` for a Work.

    Tasks start in ``TODO``. The caller commits.
    """
    base = base_date or date.today()
    result = InstantiationResult(template_key=template.key)

    milestone_ids: dict[str, str] = {}
    for ms in template.milestones:
        milestone = ProductionMilestone(
            title=ms.title,
            work_id=work_id,
            story_world_id=story_world_id,
            division=template.division,
            target_date=base + timedelta(days=ms.offset_days),
            sequence_order=len(milestone_ids),
        )
        session.add(milestone)
        session.flush()
        milestone_ids[ms.key] = milestone.id
        result.milestone_ids.append(milestone.id)

    task_ids: dict[str, str] = {}
    for t in template.tasks:
        task = ProductionItem(
            title=t.title,
            work_id=work_id,
            story_world_id=story_world_id,
            division=template.division,
            track=t.track,
            task_type=t.task_type,
            priority=t.priority,
            status=ProductionItemStatus.TODO,
            creator_id=actor_id,
            milestone_id=milestone_ids.get(t.milestone) if t.milestone else None,
            due_date=base + timedelta(days=t.offset_days),
            acceptance_criteria=t.acceptance_criteria,
        )
        session.add(task)
        session.flush()
        task_ids[t.key] = task.id
        result.task_ids.append(task.id)
        production_service.record_activity(
            session,
            task_id=task.id,
            type=ProductionActivityType.TEMPLATE_APPLIED,
            actor_id=actor_id,
            summary=f"Created from template “{template.name}”.",
        )

    for t in template.tasks:
        for dep_key in t.depends_on:
            if dep_key not in task_ids:
                continue
            dependency = ProductionDependency(
                task_id=task_ids[t.key],
                depends_on_id=task_ids[dep_key],
                type=DependencyType.FINISH_TO_START,
            )
            session.add(dependency)
            session.flush()
            result.dependency_ids.append(dependency.id)

    return result
