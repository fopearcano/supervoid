"""Shared types for distribution-package generators.

A generator turns an :class:`EditionContext` into a :class:`PackageResult` — a
JSON-safe ``manifest`` plus a ``checklist`` of validations. Generators prepare
and validate; they never upload.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from app.models.enums import ChecklistStatus

if TYPE_CHECKING:
    from app.models import Edition, Work


@dataclass
class ChecklistItem:
    key: str
    label: str
    status: ChecklistStatus
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status.value,
            "detail": self.detail,
        }


# --- checklist builders ----------------------------------------------------


def passed(key: str, label: str, detail: str = "") -> ChecklistItem:
    return ChecklistItem(key, label, ChecklistStatus.PASS, detail)


def failed(key: str, label: str, detail: str = "") -> ChecklistItem:
    return ChecklistItem(key, label, ChecklistStatus.FAIL, detail)


def warned(key: str, label: str, detail: str = "") -> ChecklistItem:
    return ChecklistItem(key, label, ChecklistStatus.WARN, detail)


def na(key: str, label: str, detail: str = "") -> ChecklistItem:
    return ChecklistItem(key, label, ChecklistStatus.NA, detail)


def require(key: str, label: str, ok: bool, *, fail_detail: str = "", ok_detail: str = "") -> ChecklistItem:
    """PASS when ``ok`` else FAIL — for required items."""
    return passed(key, label, ok_detail) if ok else failed(key, label, fail_detail)


def prefer(key: str, label: str, ok: bool, *, warn_detail: str = "", ok_detail: str = "") -> ChecklistItem:
    """PASS when ``ok`` else WARN — for recommended-but-optional items."""
    return passed(key, label, ok_detail) if ok else warned(key, label, warn_detail)


@dataclass
class EditionContext:
    """Everything a generator needs, materialised once by the service."""

    edition: "Edition"
    work: Optional["Work"]
    author_name: Optional[str]

    # --- convenience accessors ---
    def file(self, *roles: str) -> Optional[dict]:
        for f in self.edition.files or []:
            if isinstance(f, dict) and f.get("role") in roles:
                return f
        return None

    def has_file(self, *roles: str) -> bool:
        return self.file(*roles) is not None

    def meta(self, key: str, default=None):
        return (self.edition.edition_metadata or {}).get(key, default)

    @property
    def title(self) -> str:
        return self.edition.title or (self.work.title if self.work else "") or ""

    @property
    def subtitle(self) -> Optional[str]:
        return self.work.subtitle if self.work else None

    @property
    def synopsis(self) -> Optional[str]:
        meta = self.meta("description")
        if meta:
            return meta
        return self.work.synopsis if self.work else None

    @property
    def money(self) -> dict:
        price = self.edition.price
        return {
            "amount": str(price) if price is not None else None,
            "currency": self.edition.currency,
        }

    @property
    def pub_date(self) -> Optional[str]:
        d = self.edition.publication_date
        return d.isoformat() if d else None


@dataclass
class PackageResult:
    channel: str
    manifest: dict
    checklist: list[ChecklistItem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(c.status == ChecklistStatus.FAIL for c in self.checklist)

    @property
    def errors(self) -> list[str]:
        return [
            f"{c.label}: {c.detail}".strip(": ").strip()
            for c in self.checklist
            if c.status == ChecklistStatus.FAIL
        ]

    @property
    def warnings(self) -> list[str]:
        return [
            f"{c.label}: {c.detail}".strip(": ").strip()
            for c in self.checklist
            if c.status == ChecklistStatus.WARN
        ]

    def validation(self) -> dict:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "passed": sum(1 for c in self.checklist if c.status == ChecklistStatus.PASS),
            "failed": sum(1 for c in self.checklist if c.status == ChecklistStatus.FAIL),
            "warned": sum(1 for c in self.checklist if c.status == ChecklistStatus.WARN),
        }
