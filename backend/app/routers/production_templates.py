"""Work-level production templates: list the starter templates and apply one to
a Work, instantiating its milestones, tasks and dependencies."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.auth import AUTHED, get_current_user
from app.db import get_session
from app.models import User, Work
from app.schemas.production_template import (
    ApplyTemplateRequest,
    ApplyTemplateResult,
    ProductionTemplateRead,
    TemplateMilestoneRead,
    TemplateTaskRead,
)
from app.services import production_templates
from app.utils import get_or_404

# No router prefix: this serves both /production-templates and the work-scoped
# apply endpoint so each path reads naturally.
router = APIRouter(tags=["production_templates"])


def _template_read(tpl) -> ProductionTemplateRead:
    return ProductionTemplateRead(
        key=tpl.key,
        name=tpl.name,
        division=tpl.division,
        description=tpl.description,
        milestones=[
            TemplateMilestoneRead(key=m.key, title=m.title, offset_days=m.offset_days)
            for m in tpl.milestones
        ],
        tasks=[
            TemplateTaskRead(
                key=t.key,
                title=t.title,
                track=t.track,
                task_type=t.task_type,
                priority=t.priority,
                offset_days=t.offset_days,
                milestone=t.milestone,
                depends_on=list(t.depends_on),
                acceptance_criteria=t.acceptance_criteria,
            )
            for t in tpl.tasks
        ],
    )


@router.get("/production-templates", response_model=list[ProductionTemplateRead])
def list_production_templates() -> list[ProductionTemplateRead]:
    return [_template_read(t) for t in production_templates.list_templates()]


@router.get("/production-templates/{key}", response_model=ProductionTemplateRead)
def get_production_template(key: str) -> ProductionTemplateRead:
    tpl = production_templates.get_template(key)
    if tpl is None:
        raise HTTPException(status_code=404, detail="Production template not found")
    return _template_read(tpl)


@router.post(
    "/works/{work_id}/production-template",
    response_model=ApplyTemplateResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=AUTHED,
)
def apply_production_template(
    work_id: str,
    payload: ApplyTemplateRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ApplyTemplateResult:
    work = get_or_404(session, Work, work_id, name="Work")
    tpl = production_templates.get_template(payload.template_key)
    if tpl is None:
        raise HTTPException(status_code=404, detail="Production template not found")

    result = production_templates.instantiate_template(
        session,
        tpl,
        work_id=work.id,
        actor_id=user.id,
        base_date=payload.base_date,
        story_world_id=payload.story_world_id or work.story_world_id,
    )
    session.commit()
    return ApplyTemplateResult(
        template_key=result.template_key,
        work_id=work.id,
        milestone_ids=result.milestone_ids,
        task_ids=result.task_ids,
        dependency_ids=result.dependency_ids,
    )
