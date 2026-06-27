"""Backup/restore covers new records *and* stored assets (round-trip).

The dump is driven by ``SQLModel.metadata`` so it inherently covers every new
record type; this proves a representative connected graph (asset + version +
provenance, an agent run, a public projection) plus a real asset file survive a
backup → restore into a fresh database and storage path.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlmodel import Session, create_engine, select

from app.migrations import ensure_migrated
from app.models import (
    AgentRun,
    AssetVersion,
    Author,
    ProvenanceRecord,
    PublishedWork,
)
from app.models.enums import PublishedStatus
from app.services.integrations import effects

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backup_restore.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("backup_restore", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _populate(url: str, storage: Path) -> dict:
    ensure_migrated(url)
    engine = create_engine(url)
    ids: dict = {}
    try:
        with Session(engine) as s:
            author = Author(full_name="Backup Author")
            s.add(author)
            s.flush()
            res = effects.attach_asset_version(
                s,
                new_asset={"title": "Backup Cover", "asset_type": "cover"},
                owner_id=None,
                storage_key="assets/backup-cover.png",
                mime_type="image/png",
                provenance={"kind": "mixed", "provider": "hand"},
            )
            s.add(AgentRun(agent_key="manuscript_consistency", correlation_id="trace-backup"))
            s.add(PublishedWork(
                title="Backup Public", slug="backup-public", status=PublishedStatus.DRAFT
            ))
            s.commit()
            ids["asset_version_id"] = res["asset_version_id"]
    finally:
        engine.dispose()

    f = storage / "assets" / "backup-cover.png"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"\x89PNG\r\n\x1a\nDEMO-BYTES")
    return ids


def test_backup_restore_round_trip(tmp_path: Path) -> None:
    mod = _load_module()
    src_url = f"sqlite:///{tmp_path / 'src.db'}"
    src_storage = tmp_path / "src-storage"
    ids = _populate(src_url, src_storage)

    out = tmp_path / "backup"
    manifest = mod.backup(out, url=src_url, storage_path=str(src_storage))
    assert manifest["storage_files"] >= 1
    # New-domain tables are present in the dump with their rows.
    for table in ("assets", "asset_versions", "provenance_records", "agent_runs", "published_works"):
        assert manifest["row_counts"][table] == 1, table

    # Restore into a fresh database + storage path.
    dst_url = f"sqlite:///{tmp_path / 'dst.db'}"
    dst_storage = tmp_path / "dst-storage"
    stats = mod.restore(out, url=dst_url, storage_path=str(dst_storage))
    assert stats["total_rows"] == manifest["total_rows"]

    engine = create_engine(dst_url)
    try:
        with Session(engine) as s:
            assert s.exec(select(Author)).first().full_name == "Backup Author"
            av = s.exec(select(AssetVersion)).first()
            assert av.storage_key == "assets/backup-cover.png"
            prov = s.exec(select(ProvenanceRecord)).first()
            assert prov.asset_version_id == ids["asset_version_id"]
            assert s.exec(select(AgentRun)).first().correlation_id == "trace-backup"
            assert s.exec(select(PublishedWork)).first().slug == "backup-public"
    finally:
        engine.dispose()

    # The asset file came back byte-for-byte.
    restored = dst_storage / "assets" / "backup-cover.png"
    assert restored.is_file()
    assert restored.read_bytes() == (src_storage / "assets" / "backup-cover.png").read_bytes()


def _populate_brain(url: str) -> list:
    """Seed a connected graph of EVERY Brain-era record type (Prompts 5–18)."""
    from app.auth.security import generate_brain_token, hash_brain_token, hash_password
    from app.models import (
        BrainAccessToken,
        BrainConversation,
        BrainEvent,
        BrainMessage,
        BrainStateRevision,
        DecisionRecord,
        EmbeddingRecord,
        KnowledgeChunk,
        KnowledgeDocument,
        LibreChatIdentityLink,
        ProjectBrainState,
        SecurityEvent,
        StoryWorld,
        TuningAdapter,
        TuningExample,
        User,
        Work,
    )
    from app.models.enums import (
        BrainMessageRole,
        BrainScope,
        IdentityLinkStatus,
        KnowledgeDocStatus,
        KnowledgeSourceType,
        SecurityEventSeverity,
        SecurityEventType,
        TuningExampleKind,
        UserRole,
    )
    from app.services import brain
    from app.services.brain.events import BrainEventType as ET

    ensure_migrated(url)
    engine = create_engine(url)
    try:
        with Session(engine) as s:
            user = User(email="brain@backup.test", full_name="Brain Backup",
                        role=UserRole.EDITOR, hashed_password=hash_password("pw"))
            s.add(user)
            s.add(Author(full_name="BR Author"))
            s.commit()
            s.refresh(user)
            author = s.exec(select(Author)).first()
            world = StoryWorld(name="BR World", slug="br-world")
            s.add(world)
            s.commit()
            s.refresh(world)
            work = Work(title="BR Work", author_id=author.id, story_world_id=world.id)
            s.add(work)
            s.commit()
            s.refresh(work)

            conv = brain.create_conversation(s, owner_user_id=user.id, work_id=work.id,
                                             active_profile="studio-director")
            brain.append_message(s, conv, role=BrainMessageRole.USER, content="hello brain")
            brain.append_message(s, conv, role=BrainMessageRole.ASSISTANT, content="hi there",
                                 prompt_tokens=10, completion_tokens=5)
            brain.emit(s, event_type=ET.WORK_CREATED, aggregate_type="work",
                       aggregate_id=work.id, work_id=work.id, story_world_id=world.id)
            brain.set_project_state(s, structured_state={"identity": {"title": "BR Work"}},
                                    work_id=work.id)  # also snapshots a BrainStateRevision
            brain.create_decision(s, scope=BrainScope.PROJECT, subject="Antagonist",
                                  decision="The arsonist is the harbour-master.",
                                  work_id=work.id, proposer_id=user.id)
            s.add(BrainAccessToken(user_id=user.id, name="lc",
                                   token_hash=hash_brain_token(generate_brain_token())))
            doc = KnowledgeDocument(
                source_type=KnowledgeSourceType.DECISION_RATIONALE, source_id="dec-1",
                source_ref="Decision", work_id=work.id, permission_scope="view_project",
                title="Decision", status=KnowledgeDocStatus.ACTIVE, content_hash="h", chunk_count=1)
            s.add(doc)
            s.flush()
            chunk = KnowledgeChunk(document_id=doc.id, chunk_index=0, content="text", content_hash="h")
            s.add(chunk)
            s.flush()
            s.add(EmbeddingRecord(chunk_id=chunk.id, document_id=doc.id, provider="dry_run",
                                  model="m", dim=3, embedding=[0.1, 0.2, 0.3], content_hash="h"))
            s.add(LibreChatIdentityLink(supervoid_user_id=user.id, librechat_email="brain@backup.test",
                                        status=IdentityLinkStatus.ACTIVE))
            s.add(SecurityEvent(event_type=SecurityEventType.IDENTITY_LINKED,
                                severity=SecurityEventSeverity.INFO, source="api",
                                supervoid_user_id=user.id))
            s.add(TuningExample(kind=TuningExampleKind.TOOL_CHOICE,
                                messages=[{"role": "user", "content": "q"}], target_output="a"))
            s.add(TuningAdapter(name="cand", base_model="supervoid-brain",
                                training_parameters={"method": "lora"}, licence="proprietary"))
            s.commit()
    finally:
        engine.dispose()

    return [BrainConversation, BrainMessage, BrainEvent, ProjectBrainState, BrainStateRevision,
            BrainAccessToken, DecisionRecord, KnowledgeDocument, KnowledgeChunk, EmbeddingRecord,
            LibreChatIdentityLink, SecurityEvent, TuningExample, TuningAdapter]


def test_backup_restore_covers_all_brain_records(tmp_path: Path) -> None:
    """Every Brain-era record type survives a backup → restore round trip — proving
    backup/restore is real (not mocked) across the whole Brain domain."""
    from sqlmodel import func

    from app.models import ProjectBrainState, TuningAdapter

    mod = _load_module()
    src_url = f"sqlite:///{tmp_path / 'brain-src.db'}"
    brain_models = _populate_brain(src_url)

    out = tmp_path / "brain-backup"
    manifest = mod.backup(out, url=src_url, storage_path=str(tmp_path / "br-storage"))
    for m in brain_models:
        assert manifest["row_counts"].get(m.__tablename__, 0) >= 1, m.__tablename__

    dst_url = f"sqlite:///{tmp_path / 'brain-dst.db'}"
    mod.restore(out, url=dst_url, storage_path=str(tmp_path / "br-dst-storage"))

    engine = create_engine(dst_url)
    try:
        with Session(engine) as s:
            for m in brain_models:  # every Brain table restored row-for-row
                cnt = s.exec(select(func.count()).select_from(m)).one()
                assert cnt == manifest["row_counts"][m.__tablename__], m.__tablename__
            # JSON payloads survive intact.
            assert s.exec(select(ProjectBrainState)).first().structured_state["identity"]["title"] == "BR Work"
            assert s.exec(select(TuningAdapter)).first().training_parameters["method"] == "lora"
    finally:
        engine.dispose()


def test_restore_refuses_nonempty_without_reset(tmp_path: Path) -> None:
    mod = _load_module()
    src_url = f"sqlite:///{tmp_path / 'src.db'}"
    src_storage = tmp_path / "s"
    _populate(src_url, src_storage)
    out = tmp_path / "b"
    mod.backup(out, url=src_url, storage_path=str(src_storage))

    # Restoring back into the populated source refuses without reset...
    with pytest.raises(SystemExit):
        mod.restore(out, url=src_url, storage_path=str(src_storage))
    # ...but succeeds with reset (idempotent reload).
    stats = mod.restore(out, url=src_url, storage_path=str(src_storage), reset=True)
    assert stats["total_rows"] >= 5
