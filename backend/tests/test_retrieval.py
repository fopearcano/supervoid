"""Cold-detail retrieval with pgvector (Prompt 14).

Exercises the SQLite path end to end (the in-process cosine + keyword fallback;
the pgvector ANN / ts_rank accelerators activate only on PostgreSQL). Proves:

* indexing re-embeds ONLY changed content,
* no binary image data ever enters the vector store,
* hybrid retrieval ranks relevant material and returns citations + section refs,
* permission filtering happens BEFORE content is returned (strict for rights),
* project-private material never leaks across projects,
* diagnostics (query / filters / candidates / reranked / sources used) are recorded,
* material already in the compiled state is excluded,
* retrieval is trigger-gated, and indexing runs asynchronously off domain events.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.security import hash_password
from app.models import (
    Asset,
    AssetVersion,
    Author,
    BrainMemoryItem,
    DecisionRecord,
    EmbeddingRecord,
    KnowledgeChunk,
    KnowledgeDocument,
    Manuscript,
    ProjectMembership,
    Rights,
    RetrievalHit,
    User,
    Work,
)
from app.models.enums import (
    BrainMemoryKind,
    BrainMemoryVerification,
    BrainScope,
    DecisionStatus,
    KnowledgeSourceType,
    MembershipStatus,
    ProjectRole,
    RetrievalTrigger,
    UserRole,
)
from app.services import brain
from app.services.brain.retrieval import indexer, search

ST = KnowledgeSourceType


# --- helpers ---------------------------------------------------------------
def _user(session: Session, email: str, role: UserRole = UserRole.EDITOR) -> User:
    u = User(email=email, full_name=email.split("@")[0], role=role,
             hashed_password=hash_password("pw"))
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _work(session: Session, title: str = "Work") -> Work:
    a = Author(full_name="A")
    session.add(a)
    session.commit()
    session.refresh(a)
    w = Work(title=title, author_id=a.id)
    session.add(w)
    session.commit()
    session.refresh(w)
    w._author_id = a.id  # type: ignore[attr-defined]
    return w


def _manuscript(session: Session, work: Work, synopsis: str, title: str = "MS") -> Manuscript:
    m = Manuscript(title=title, author_id=work._author_id, work_id=work.id, synopsis=synopsis)  # type: ignore[attr-defined]
    session.add(m)
    session.commit()
    session.refresh(m)
    return m


def _member(session: Session, user: User, work: Work, role: ProjectRole) -> None:
    session.add(ProjectMembership(
        user_id=user.id, work_id=work.id, role=role, status=MembershipStatus.ACTIVE,
    ))
    session.commit()


def _index(session: Session, source_type, source_id) -> dict:
    res = indexer.reindex_source(session, source_type, source_id)
    session.commit()
    return res


# === indexing + re-embed only changed ======================================
def test_index_and_reembed_only_changed(session: Session) -> None:
    w = _work(session)
    m = _manuscript(session, w, "A detective hunts an arsonist in a flooded city.")
    first = _index(session, ST.MANUSCRIPT, m.id)
    assert first["status"] == "indexed" and first["embedded"] >= 1

    again = _index(session, ST.MANUSCRIPT, m.id)
    assert again["status"] == "unchanged"  # nothing re-embedded

    m.synopsis = "A detective hunts an arsonist in a flooded city, aided by a rookie."
    session.add(m)
    session.commit()
    changed = _index(session, ST.MANUSCRIPT, m.id)
    assert changed["status"] == "indexed"
    assert changed["embedded"] == 1 and changed["reused"] >= 1  # only the changed chunk


# === no binary image data in the vector store ==============================
def test_no_binary_data_indexed(session: Session) -> None:
    w = _work(session)
    asset = Asset(title="Cover art", description="Moody teal cover, rain-soaked street",
                  tags=["cover", "noir"], work_id=w.id)
    session.add(asset)
    session.commit()
    session.refresh(asset)
    version = AssetVersion(
        asset_id=asset.id, storage_key="s3://supervoid-private/SECRET_BINARY.png",
        notes="final approved cover",
        technical_metadata={"resolution": "4096x4096", "checksum": "DEADBEEFSHA"},
    )
    session.add(version)
    session.commit()
    session.refresh(version)
    asset.current_version_id = version.id
    session.add(asset)
    session.commit()

    _index(session, ST.ASSET_METADATA, asset.id)
    chunks = session.exec(select(KnowledgeChunk)).all()
    blob = "\n".join(c.content for c in chunks)
    # binary references are NEVER indexed
    assert "s3://" not in blob and "SECRET_BINARY" not in blob
    assert "DEADBEEFSHA" not in blob  # checksum skipped
    # but text metadata IS
    assert "Cover art" in blob and "final approved cover" in blob and "4096x4096" in blob
    # embeddings are plain float vectors, never bytes
    for er in session.exec(select(EmbeddingRecord)).all():
        assert isinstance(er.embedding, list)
        assert all(isinstance(x, (int, float)) for x in er.embedding)


# === hybrid retrieval + citations ==========================================
def test_hybrid_retrieval_ranks_and_cites(session: Session) -> None:
    admin = _user(session, "admin@s.test", UserRole.ADMIN)
    w = _work(session)
    m1 = _manuscript(session, w, "The arsonist sets fire to the cathedral district.", title="A")
    m2 = _manuscript(session, w, "A romance blossoms in a quiet seaside town.", title="B")
    _index(session, ST.MANUSCRIPT, m1.id)
    _index(session, ST.MANUSCRIPT, m2.id)

    res = search.retrieve(
        session, admin, query="who is the arsonist in the cathedral district",
        trigger=RetrievalTrigger.HISTORICAL_JUSTIFICATION, work_id=w.id,
    )
    session.commit()
    assert res.returned_count >= 1
    top = res.hits[0]
    assert "arsonist" in top.snippet.lower()  # the relevant manuscript ranks first
    # citation is a stable internal reference with a section anchor
    assert top.citation.startswith("[manuscript:") and top.section_ref
    assert top.citation in res.sources_used
    assert "<<<EVIDENCE" in res.evidence_block and top.citation in res.evidence_block


# === permission filtering (strict for rights) ==============================
def test_retrieval_permission_filtered_strict_rights(session: Session) -> None:
    admin = _user(session, "admin2@s.test", UserRole.ADMIN)
    editor = _user(session, "editor@s.test", UserRole.EDITOR)
    owner = _user(session, "owner@s.test", UserRole.EDITOR)
    w = _work(session)
    _member(session, editor, w, ProjectRole.EDITOR)   # VIEW, no MANAGE_RIGHTS
    _member(session, owner, w, ProjectRole.OWNER)     # has MANAGE_RIGHTS

    m = _manuscript(session, w, "The reversion clause haunts the arsonist saga.")
    rights = Rights(work_id=w.id,
                    notes="The reversion clause returns film rights to the author in 2030.")
    session.add(rights)
    session.commit()
    session.refresh(rights)
    _index(session, ST.MANUSCRIPT, m.id)
    _index(session, ST.RIGHTS_EXTRACT, rights.id)

    q = "reversion clause film rights"

    def types(user):
        r = search.retrieve(session, user, query=q,
                            trigger=RetrievalTrigger.DETAILED_SOURCE, work_id=w.id)
        return {h.source_type for h in r.hits}

    # editor sees the manuscript but NOT the rights extract (manage_rights gated)
    ed_types = types(editor)
    assert "manuscript" in ed_types and "rights_extract" not in ed_types
    # owner + admin see the rights extract
    assert "rights_extract" in types(owner)
    assert "rights_extract" in types(admin)


def test_retrieval_does_not_leak_across_projects(session: Session) -> None:
    editor = _user(session, "ed2@s.test", UserRole.EDITOR)
    work_a = _work(session, "Alpha")
    work_b = _work(session, "Beta")
    _member(session, editor, work_a, ProjectRole.EDITOR)  # member of A only
    ma = _manuscript(session, work_a, "Alpha arsonist secret plot", title="A")
    mb = _manuscript(session, work_b, "Beta arsonist secret plot", title="B")
    _index(session, ST.MANUSCRIPT, ma.id)
    _index(session, ST.MANUSCRIPT, mb.id)

    # unscoped query: the editor only gets work A's material, never work B's.
    res = search.retrieve(session, editor, query="arsonist secret plot",
                          trigger=RetrievalTrigger.DETAILED_SOURCE)
    session.commit()
    source_ids = {h.source_id for h in res.hits}
    assert ma.id in source_ids and mb.id not in source_ids


# === diagnostics ===========================================================
def test_diagnostics_recorded(session: Session) -> None:
    admin = _user(session, "admin3@s.test", UserRole.ADMIN)
    w = _work(session)
    m = _manuscript(session, w, "The arsonist confesses under the burning bridge.")
    _index(session, ST.MANUSCRIPT, m.id)
    res = search.retrieve(session, admin, query="arsonist burning bridge confession",
                          trigger=RetrievalTrigger.AGENT_REQUEST, work_id=w.id)
    session.commit()

    from app.models import RetrievalRun

    run = session.get(RetrievalRun, res.run_id)
    assert run is not None
    assert run.query == "arsonist burning bridge confession"
    assert run.trigger == RetrievalTrigger.AGENT_REQUEST
    assert run.candidate_count >= 1 and run.returned_count >= 1
    assert run.filters.get("work_id") == w.id
    assert run.sources_used  # citations used
    hits = session.exec(select(RetrievalHit).where(RetrievalHit.run_id == run.id)).all()
    assert hits and any(h.returned for h in hits)


# === exclude material already in the compiled state ========================
def test_exclude_in_state(session: Session) -> None:
    admin = _user(session, "admin4@s.test", UserRole.ADMIN)
    w = _work(session)
    d = DecisionRecord(scope=BrainScope.PROJECT, work_id=w.id, status=DecisionStatus.APPROVED,
                       subject="Arsonist identity", decision="The arsonist is the mayor.",
                       rationale="Foreshadowed by the cigar motif throughout act two.")
    session.add(d)
    session.commit()
    session.refresh(d)
    brain.compile_project(session, work_id=w.id, full=True)  # decision enters canon_facts
    session.commit()
    _index(session, ST.DECISION_RATIONALE, d.id)

    q = "why is the mayor the arsonist cigar motif"
    incl = search.retrieve(session, admin, query=q, trigger=RetrievalTrigger.HISTORICAL_JUSTIFICATION,
                           work_id=w.id, exclude_in_state=False)
    excl = search.retrieve(session, admin, query=q, trigger=RetrievalTrigger.HISTORICAL_JUSTIFICATION,
                           work_id=w.id, exclude_in_state=True)
    session.commit()
    assert any(h.source_id == d.id for h in incl.hits)       # present when not excluding
    assert all(h.source_id != d.id for h in excl.hits)       # excluded (already in state)


# === only APPROVED conversation summaries are indexed ======================
def test_only_approved_conversation_summaries_indexed(session: Session) -> None:
    w = _work(session)
    approved = brain.create_memory(
        session, scope=BrainScope.CONVERSATION, kind=BrainMemoryKind.PROCEDURE,
        content="The team agreed the arsonist arc resolves in chapter nine.",
        work_id=w.id, structured_data={"kind": "conversation_compaction"},
    )
    approved.verification = BrainMemoryVerification.VERIFIED
    pending = brain.create_memory(
        session, scope=BrainScope.CONVERSATION, kind=BrainMemoryKind.PROCEDURE,
        content="Unreviewed draft summary.", work_id=w.id,
        structured_data={"kind": "conversation_compaction"},
    )
    session.commit()

    assert _index(session, ST.CONVERSATION_SUMMARY, approved.id)["status"] == "indexed"
    assert _index(session, ST.CONVERSATION_SUMMARY, pending.id)["status"] == "skipped"


# === async indexing after a domain event ===================================
def test_async_indexing_after_event(session: Session) -> None:
    w = _work(session)
    m = _manuscript(session, w, "The arsonist is unmasked at the harbour.")
    # No document yet.
    assert session.exec(select(KnowledgeDocument)).first() is None
    brain.emit(session, event_type=brain.BrainEventType.MANUSCRIPT_UPDATED,
               aggregate_type="manuscript", aggregate_id=m.id, work_id=w.id)
    session.commit()
    brain.drain(session)  # the consumer indexes asynchronously
    doc = session.exec(
        select(KnowledgeDocument).where(KnowledgeDocument.source_id == m.id)
    ).first()
    assert doc is not None and doc.source_type == ST.MANUSCRIPT


# === trigger-gated HTTP endpoint ===========================================
def test_search_endpoint_requires_valid_trigger(client: TestClient, session: Session) -> None:
    w = _work(session)
    m = _manuscript(session, w, "The arsonist leaves a calling card.")
    _index(session, ST.MANUSCRIPT, m.id)
    # an invalid trigger is rejected (retrieval is trigger-gated)
    bad = client.post("/api/brain/retrieval/search",
                      json={"query": "calling card", "trigger": "because_i_said_so"})
    assert bad.status_code == 422
    # a valid trigger works and returns citations
    ok = client.post("/api/brain/retrieval/search", json={
        "query": "arsonist calling card", "trigger": "detailed_source", "work_id": w.id,
    })
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["run_id"] and body["returned_count"] >= 1
    assert body["hits"][0]["citation"].startswith("[manuscript:")
    # the run is auditable via diagnostics
    detail = client.get(f"/api/brain/retrieval/runs/{body['run_id']}")
    assert detail.status_code == 200 and detail.json()["hits"]


def test_mcp_retrieve_evidence_permission_filtered(session: Session) -> None:
    """The MCP tool returns only authorised records (mirrors the service)."""
    from types import SimpleNamespace

    from app.services.mcp.tools import retrieve_evidence

    editor = _user(session, "mcped@s.test", UserRole.EDITOR)
    w = _work(session)
    _member(session, editor, w, ProjectRole.EDITOR)
    m = _manuscript(session, w, "The arsonist torches the archive.")
    rights = Rights(work_id=w.id, notes="Confidential reversion of the archive rights.")
    session.add(rights)
    session.commit()
    session.refresh(rights)
    _index(session, ST.MANUSCRIPT, m.id)
    _index(session, ST.RIGHTS_EXTRACT, rights.id)

    principal = SimpleNamespace(user=editor)
    out = retrieve_evidence(session, principal, {"q": "arsonist archive reversion rights", "work_id": w.id})
    session.commit()
    kinds = {r["citation"].split(":")[0] for r in out["results"]}
    assert "[manuscript" in kinds and "[rights_extract" not in kinds
