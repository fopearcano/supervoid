"""Generate and persist distribution packages.

Builds an :class:`EditionContext`, runs the channel generator, and persists a
``DistributionPackage`` recording the manifest, checklist and validation. The
package is prepared and validated — never uploaded.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session

from app.models import (
    DistributionPackage,
    Edition,
    PackageStatus,
    User,
    Work,
)
from app.models.enums import DistributionChannel
from app.services.distribution.base import EditionContext
from app.services.distribution.generators import GENERATORS


def build_context(session: Session, edition: Edition) -> EditionContext:
    work = session.get(Work, edition.work_id)
    author_name = work.author.full_name if (work and work.author) else None
    return EditionContext(edition=edition, work=work, author_name=author_name)


def available_channels() -> list[str]:
    return [c.value for c in GENERATORS]


def generate_package(
    session: Session,
    edition: Edition,
    channel: DistributionChannel,
    *,
    user: Optional[User] = None,
) -> DistributionPackage:
    generator = GENERATORS.get(channel)
    if generator is None:  # pragma: no cover - channel is enum-validated upstream
        raise HTTPException(status_code=400, detail=f"Unknown channel '{channel}'.")
    ctx = build_context(session, edition)
    result = generator(ctx)
    package = DistributionPackage(
        edition_id=edition.id,
        channel=channel,
        status=PackageStatus.VALIDATED if result.ok else PackageStatus.INVALID,
        manifest=result.manifest,
        checklist=[item.to_dict() for item in result.checklist],
        validation=result.validation(),
        generated_by_id=user.id if user else None,
    )
    session.add(package)
    return package
