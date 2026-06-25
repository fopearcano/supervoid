"""The demo seed demonstrates the full studio system.

Verifies the eight artefacts the integration brief calls for: a story world, a
graphic novel, a film adaptation, collaborators, assets + provenance, tasks +
approvals, agent findings, and public-reader content — all produced by a single
``seed.run()`` against a throwaway database.
"""
from __future__ import annotations

import pytest
from sqlalchemy import func
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.models import (
    AdaptationDossier,
    AgentFinding,
    ApprovalRequest,
    Asset,
    GraphicNovelProduction,
    ProductionItem,
    ProjectMembership,
    ProvenanceRecord,
    PublishedStatus,
    PublishedWork,
    StoryWorld,
)
from app.models.enums import Medium


@pytest.fixture()
def seeded(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Engine:
    """Run the demo seed against the in-memory test engine."""
    from app import seed as seed_module

    # The engine fixture already created the schema; redirect the seed at it.
    monkeypatch.setattr(seed_module, "engine", engine)
    monkeypatch.setattr(seed_module, "init_db", lambda: None)
    seed_module.run()
    return engine


def _count(session: Session, model) -> int:
    return session.exec(select(func.count()).select_from(model)).one()


def test_seed_demonstrates_required_artefacts(seeded: Engine) -> None:
    with Session(seeded) as s:
        # 1. one StoryWorld
        assert _count(s, StoryWorld) >= 1
        # 2. one graphic novel (production hierarchy)
        assert _count(s, GraphicNovelProduction) >= 1
        # 3. one film adaptation
        film = s.exec(
            select(AdaptationDossier).where(AdaptationDossier.target_medium == Medium.FILM)
        ).first()
        assert film is not None
        # 4. collaborators
        assert _count(s, ProjectMembership) >= 1
        # 5. assets and provenance
        assert _count(s, Asset) >= 1
        assert _count(s, ProvenanceRecord) >= 1
        # 6. tasks and approvals
        assert _count(s, ProductionItem) >= 1
        assert _count(s, ApprovalRequest) >= 1
        # 7. agent findings
        assert _count(s, AgentFinding) >= 1
        # 8. public-reader content (a published work)
        published = s.exec(
            select(PublishedWork).where(PublishedWork.status == PublishedStatus.PUBLISHED)
        ).first()
        assert published is not None
