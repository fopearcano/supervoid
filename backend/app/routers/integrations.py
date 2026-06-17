"""Ecosystem integration endpoints.

Exposes the SUPERVOID ENTANGLED ecosystem map and the declared integration
points to sibling systems (LOGOSFORGE, SUPERVOID Movies). Read-only and
local-first — these describe the seams; they do not call out to anything.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.integrations import (
    ECOSYSTEM,
    Ecosystem,
    Integration,
    all_integrations,
    get_integration,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("", response_model=list[Integration], summary="Ecosystem integration points")
def list_integrations() -> list[Integration]:
    return all_integrations()


@router.get(
    "/ecosystem",
    response_model=Ecosystem,
    summary="SUPERVOID ENTANGLED ecosystem map",
)
def ecosystem() -> Ecosystem:
    return ECOSYSTEM


@router.get(
    "/{key}",
    response_model=Integration,
    summary="A single integration descriptor",
)
def get_one(key: str) -> Integration:
    integration = get_integration(key)
    if integration is None:
        raise HTTPException(status_code=404, detail="Integration not found.")
    return integration
