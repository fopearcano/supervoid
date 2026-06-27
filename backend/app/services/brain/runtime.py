"""In-process Brain runtime state: operational control flags + live gauges.

This holds the operator switches (disable new model requests, drain, disable MCP,
maintenance note) and the live request gauge the Ops view reports. Like the
gateway's rate/concurrency limiters, this state is **per process (per uvicorn
worker)** — not shared across replicas. A shared control plane (Redis, a DB flag)
is a later concern; the flags here are the simple, robust first version.

Nothing sensitive lives here; ``snapshot()`` is safe for the admin Ops view.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.config import settings


@dataclass
class _Runtime:
    model_requests_disabled: bool = False
    draining: bool = False
    mcp_disabled: bool = False
    maintenance_note: Optional[str] = None
    active_requests: int = 0
    request_total: int = 0
    rejected_total: int = 0


_state = _Runtime()


def reset() -> None:
    """Reset all flags + counters (tests)."""
    global _state
    _state = _Runtime()


# --- gates -----------------------------------------------------------------
def model_requests_allowed() -> bool:
    """False when an operator disabled new model requests or is draining."""
    return not (_state.model_requests_disabled or _state.draining)

def mcp_allowed() -> bool:
    return not _state.mcp_disabled


# --- live request gauge ----------------------------------------------------
def acquire_request() -> None:
    _state.active_requests += 1
    _state.request_total += 1

def release_request() -> None:
    if _state.active_requests > 0:
        _state.active_requests -= 1

def note_rejected() -> None:
    _state.rejected_total += 1


# --- operator controls -----------------------------------------------------
def set_model_requests(*, enabled: bool) -> None:
    _state.model_requests_disabled = not enabled

def set_drain(*, draining: bool) -> None:
    _state.draining = draining

def set_mcp(*, enabled: bool) -> None:
    _state.mcp_disabled = not enabled

def set_maintenance(note: Optional[str]) -> None:
    _state.maintenance_note = (note or None)


def capacity() -> int:
    return settings.brain_gateway_max_concurrency


def in_maintenance() -> bool:
    return bool(
        _state.model_requests_disabled or _state.draining or _state.mcp_disabled
    )


def snapshot() -> dict:
    """A safe-to-display snapshot of flags + the live request gauge."""
    cap = capacity()
    active = _state.active_requests
    return {
        "active_requests": active,
        "in_flight": min(active, cap),
        "queue_depth": max(0, active - cap),
        "capacity": cap,
        "request_total": _state.request_total,
        "rejected_total": _state.rejected_total,
        "model_requests_disabled": _state.model_requests_disabled,
        "draining": _state.draining,
        "mcp_disabled": _state.mcp_disabled,
        "maintenance_note": _state.maintenance_note,
    }
