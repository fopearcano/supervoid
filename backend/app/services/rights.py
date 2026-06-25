"""Rights reminders and expiry warnings.

Derives reminders from the rights/contract layer — profile expirations and
headline term ends, per-scope window ends, option deadlines, reversion dates,
explicit reminder dates, and contract term/option ends — and surfaces them
sorted by urgency. Pure read logic; it never mutates.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlmodel import Session, select

from app.models import (
    Contract,
    Rights,
    RightsOption,
    RightsWindow,
)


@dataclass
class RightsWarning:
    source: str  # "rights" | "rights_window" | "rights_option" | "contract"
    source_id: str
    work_id: Optional[str]
    kind: str  # "expiry" | "term_end" | "reversion" | "reminder" | …
    due_date: str
    days_remaining: int
    status: str  # "overdue" | "due_soon" | "upcoming"
    message: str
    scope: Optional[str] = None


def _status(days: int, soon: int) -> str:
    if days < 0:
        return "overdue"
    if days <= soon:
        return "due_soon"
    return "upcoming"


def rights_warnings(
    session: Session,
    *,
    within_days: int = 90,
    work_id: Optional[str] = None,
    soon_days: int = 30,
) -> list[RightsWarning]:
    """All reminders due on/before today+``within_days`` (plus anything overdue)."""
    today = date.today()
    horizon = today + timedelta(days=within_days)
    out: list[RightsWarning] = []

    def add(source, source_id, wid, kind, due, message, scope=None):
        if due is None or due > horizon:
            return
        days = (due - today).days
        out.append(
            RightsWarning(
                source=source, source_id=source_id, work_id=wid, kind=kind,
                due_date=due.isoformat(), days_remaining=days,
                status=_status(days, soon_days), message=message, scope=scope,
            )
        )

    rights_stmt = select(Rights)
    if work_id is not None:
        rights_stmt = rights_stmt.where(Rights.work_id == work_id)
    profiles = list(session.exec(rights_stmt).all())
    profile_ids = {r.id for r in profiles}

    for r in profiles:
        label = f"{r.territory}/{r.language}"
        add("rights", r.id, r.work_id, "expiry", r.expiration_date,
            f"Rights {label} expire", scope=None)
        add("rights", r.id, r.work_id, "term_end", r.term_end_date,
            f"Rights term ends ({label})")
        add("rights", r.id, r.work_id, "reversion", r.reversion_date,
            f"Rights reversion date ({label})")
        add("rights", r.id, r.work_id, "reminder", r.reminder_date,
            f"Rights reminder ({label})")

    if profile_ids:
        windows = session.exec(
            select(RightsWindow).where(RightsWindow.rights_id.in_(profile_ids))
        ).all()
        by_rights = {r.id: r for r in profiles}
        for w in windows:
            parent = by_rights.get(w.rights_id)
            add("rights_window", w.id, parent.work_id if parent else None,
                "window_end", w.ends_on,
                f"{w.scope.value} window ends ({w.territory}/{w.language})",
                scope=w.scope.value)
        options = session.exec(
            select(RightsOption).where(RightsOption.rights_id.in_(profile_ids))
        ).all()
        for o in options:
            parent = by_rights.get(o.rights_id)
            wid = parent.work_id if parent else None
            add("rights_option", o.id, wid, "option_deadline",
                o.exercise_deadline or o.option_end,
                f"Option '{o.label}' deadline", scope=o.scope.value)

    contract_stmt = select(Contract)
    if work_id is not None:
        contract_stmt = contract_stmt.where(Contract.work_id == work_id)
    for c in session.exec(contract_stmt).all():
        add("contract", c.id, c.work_id, "expiry", c.expiration_date,
            "Contract expires")
        add("contract", c.id, c.work_id, "term_end", c.term_end_date,
            "Contract term ends")
        if not c.option_exercised:
            add("contract", c.id, c.work_id, "option_deadline", c.option_end_date,
                "Contract option deadline")
        add("contract", c.id, c.work_id, "reversion", c.reversion_date,
            "Contract reversion date")

    severity = {"overdue": 0, "due_soon": 1, "upcoming": 2}
    out.sort(key=lambda w: (severity[w.status], w.days_remaining))
    return out
