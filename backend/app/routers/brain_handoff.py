"""The Brain hand-off landing endpoint (root-mounted, token-authenticated).

A browser redirect lands here from "Ask the Brain". It consumes the signed,
short-lived, single-use token, binds the SUPERVOID conversation to the entity,
and redirects to the LibreChat (Brain) UI. The token is the ONLY credential here
(the redirect carries no SUPERVOID JWT), which is exactly why it is HMAC-signed,
short-lived and single-use.

We deliberately do NOT deep-link into a specific LibreChat conversation — that
would require forking upstream LibreChat. The normal Brain UI opens; the selected
context is the member's most-recent hand-off, surfaced via the MCP
``select_active_project`` / ``list_my_projects`` tools.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.config import settings
from app.db import get_session
from app.services.brain import handoff as handoff_svc
from app.utils.logging import get_logger

log = get_logger("app.brain.handoff")
router = APIRouter(tags=["brain-handoff"])


@router.get("/brain-handoff")
def brain_handoff_landing(
    token: str = Query(..., description="Signed, short-lived hand-off token."),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    try:
        handoff_svc.consume_handoff(session, token)
        session.commit()
    except Exception as exc:  # noqa: BLE001 - any failure → a safe error redirect
        detail = getattr(exc, "detail", "invalid")
        log.info("brain hand-off rejected: %s", detail)
        # Redirect back to the studio with a non-sensitive error marker.
        return RedirectResponse(url="/?brain_handoff=error", status_code=303)
    # Success: open the normal Brain UI. The active context is the member's most
    # recent hand-off (resolved via the MCP select_active_project tool).
    return RedirectResponse(url=settings.librechat_public_url, status_code=303)
