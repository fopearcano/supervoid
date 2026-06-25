"""The operational command centre API (private, authenticated).

Cross-domain roll-ups for the studio dashboard. Each section is its own endpoint
so the one-person workflow can load the overview cheaply and disclose the rest
progressively. All read-only; the heavy lifting lives in
``app/services/command_centre.py``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.auth import AUTHED, get_current_user
from app.db import get_session
from app.models import User
from app.schemas.command_centre import (
    AgentInbox,
    AssetHealth,
    BusinessAlerts,
    DivisionView,
    MyWork,
    StudioOverview,
    WorkCommand,
)
from app.services import command_centre as cc

router = APIRouter(prefix="/command-centre", tags=["command-centre"], dependencies=AUTHED)


@router.get("/overview", response_model=StudioOverview, summary="Studio overview")
def overview(session: Session = Depends(get_session)) -> StudioOverview:
    return cc.studio_overview(session)


@router.get("/my-work", response_model=MyWork, summary="The current user's work")
def my_work(
    session: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> MyWork:
    return cc.my_work(session, user)


@router.get("/agent-inbox", response_model=AgentInbox, summary="Agent inbox")
def agent_inbox(session: Session = Depends(get_session)) -> AgentInbox:
    return cc.agent_inbox(session)


@router.get("/asset-health", response_model=AssetHealth, summary="Asset health")
def asset_health(session: Session = Depends(get_session)) -> AssetHealth:
    return cc.asset_health(session)


@router.get("/business-alerts", response_model=BusinessAlerts, summary="Business alerts")
def business_alerts(session: Session = Depends(get_session)) -> BusinessAlerts:
    return cc.business_alerts(session)


@router.get("/divisions", response_model=list[DivisionView], summary="Division views")
def divisions(session: Session = Depends(get_session)) -> list[DivisionView]:
    return cc.division_views(session)


@router.get(
    "/works/{work_id}/command",
    response_model=WorkCommand,
    summary="The command page for a single Work",
)
def work_command(work_id: str, session: Session = Depends(get_session)) -> WorkCommand:
    return cc.work_command(session, work_id)
