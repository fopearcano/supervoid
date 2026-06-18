from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session, select

from app.auth import ADMIN_ONLY, AUTHED
from app.db import get_session
from app.models import GraphicNovelProduction, Work
from app.schemas import (
    GraphicNovelProductionCreate,
    GraphicNovelProductionRead,
    GraphicNovelProductionUpdate,
)
from app.utils import (
    Page,
    PageParams,
    apply_patch,
    ensure_exists,
    get_or_404,
    page_params,
    paginate,
)

router = APIRouter(
    prefix="/graphic-novel-productions", tags=["graphic_novel_productions"]
)


@router.get("", response_model=Page[GraphicNovelProductionRead])
def list_graphic_novel_productions(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    work_id: Optional[str] = Query(default=None, description="Filter by work id"),
) -> Page[GraphicNovelProductionRead]:
    stmt = select(GraphicNovelProduction)
    if work_id is not None:
        stmt = stmt.where(GraphicNovelProduction.work_id == work_id)
    stmt = stmt.order_by(GraphicNovelProduction.created_at.desc())

    items, total = paginate(session, stmt, params)
    return Page[GraphicNovelProductionRead](
        items=[GraphicNovelProductionRead.model_validate(i) for i in items],
        total=total,
        skip=params.skip,
        limit=params.limit,
    )


@router.get("/{production_id}", response_model=GraphicNovelProductionRead)
def get_graphic_novel_production(
    production_id: str, session: Session = Depends(get_session)
) -> GraphicNovelProduction:
    return get_or_404(
        session, GraphicNovelProduction, production_id, name="GraphicNovelProduction"
    )


@router.post(
    "",
    response_model=GraphicNovelProductionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=AUTHED,
)
def create_graphic_novel_production(
    payload: GraphicNovelProductionCreate, session: Session = Depends(get_session)
) -> GraphicNovelProduction:
    ensure_exists(session, Work, payload.work_id, name="Work")
    production = GraphicNovelProduction(**payload.model_dump())
    session.add(production)
    session.commit()
    session.refresh(production)
    return production


@router.patch(
    "/{production_id}",
    response_model=GraphicNovelProductionRead,
    dependencies=AUTHED,
)
def update_graphic_novel_production(
    production_id: str,
    payload: GraphicNovelProductionUpdate,
    session: Session = Depends(get_session),
) -> GraphicNovelProduction:
    production = get_or_404(
        session, GraphicNovelProduction, production_id, name="GraphicNovelProduction"
    )
    apply_patch(production, payload)
    session.add(production)
    session.commit()
    session.refresh(production)
    return production


@router.delete(
    "/{production_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=ADMIN_ONLY,
)
def delete_graphic_novel_production(
    production_id: str, session: Session = Depends(get_session)
):
    production = get_or_404(
        session, GraphicNovelProduction, production_id, name="GraphicNovelProduction"
    )
    session.delete(production)
    session.commit()
