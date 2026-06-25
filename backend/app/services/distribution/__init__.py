"""Validated distribution-package generators (ONIX, KDP, Ingram, GlobalComix,
press kit, ARC). Packages and checklists are prepared and validated, never
uploaded — real uploads need a separate, tested adapter (the integration hub).
"""
from app.services.distribution.base import (
    ChecklistItem,
    EditionContext,
    PackageResult,
)
from app.services.distribution.generators import GENERATORS, is_isbn13
from app.services.distribution.service import (
    available_channels,
    build_context,
    generate_package,
)

__all__ = [
    "ChecklistItem",
    "EditionContext",
    "GENERATORS",
    "PackageResult",
    "available_channels",
    "build_context",
    "generate_package",
    "is_isbn13",
]
