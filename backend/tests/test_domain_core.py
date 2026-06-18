from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import hash_password
from app.models import User
from app.models.enums import UserRole


# --- helpers ---------------------------------------------------------------


def _author(client: TestClient, name: str = "A. Author") -> str:
    r = client.post("/api/authors", json={"full_name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _work(client: TestClient, author_id: str, **over) -> dict:
    payload = {"title": "A Work", "author_id": author_id}
    payload.update(over)
    r = client.post("/api/works", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _manuscript(client: TestClient, author_id: str, **over) -> dict:
    payload = {"title": "A Draft", "author_id": author_id}
    payload.update(over)
    r = client.post("/api/manuscripts", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _reviewer(session: Session) -> User:
    user = User(
        email="rev@supervoid.test",
        full_name="Rev Iewer",
        role=UserRole.REVIEWER,
        hashed_password=hash_password("password"),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


# --- Work (central entity) -------------------------------------------------


def test_work_crud_lifecycle(client: TestClient) -> None:
    author_id = _author(client, "Iris Aldoria")
    created = _work(
        client, author_id, title="The Salt Atlases", work_type="book", genre="Essays"
    )
    work_id = created["id"]
    assert created["work_type"] == "book"
    assert created["status"] == "concept"

    listed = client.get("/api/works").json()
    assert listed["total"] == 1

    fetched = client.get(f"/api/works/{work_id}")
    assert fetched.status_code == 200

    patched = client.patch(
        f"/api/works/{work_id}",
        json={"status": "published", "internal_pitch": "Lead title."},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "published"
    assert patched.json()["internal_pitch"] == "Lead title."

    assert client.delete(f"/api/works/{work_id}").status_code == 204
    assert client.get(f"/api/works/{work_id}").status_code == 404


def test_work_create_requires_existing_author(client: TestClient) -> None:
    r = client.post("/api/works", json={"title": "Orphan", "author_id": "nope"})
    assert r.status_code == 404
    assert r.json()["detail"] == "Author not found"


def test_work_filters(client: TestClient) -> None:
    a1 = _author(client, "One")
    a2 = _author(client, "Two")
    _work(client, a1, title="Book A", work_type="book", genre="Essays", status="concept")
    _work(
        client,
        a1,
        title="GN A",
        work_type="graphic_novel",
        genre="Comics",
        status="in_production",
    )
    _work(client, a2, title="Book B", work_type="book", genre="Essays", status="published")

    assert client.get("/api/works?work_type=graphic_novel").json()["total"] == 1
    assert client.get("/api/works?genre=Essays").json()["total"] == 2
    assert client.get("/api/works?status=published").json()["total"] == 1
    assert client.get(f"/api/works?author_id={a2}").json()["total"] == 1


# --- Manuscript ↔ Work link + draft metadata -------------------------------


def test_manuscript_links_to_work_and_validates(client: TestClient) -> None:
    author_id = _author(client)
    work = _work(client, author_id)
    ms = _manuscript(
        client,
        author_id,
        work_id=work["id"],
        version="2",
        draft_status="revised_draft",
        submission_date="2026-01-15",
        file_name="draft.docx",
        file_format="docx",
    )
    assert ms["work_id"] == work["id"]
    assert ms["version"] == "2"
    assert ms["draft_status"] == "revised_draft"
    assert ms["submission_date"] == "2026-01-15"
    assert ms["file_name"] == "draft.docx"

    by_work = client.get(f"/api/manuscripts?work_id={work['id']}").json()
    assert by_work["total"] == 1

    bad = client.post(
        "/api/manuscripts",
        json={"title": "X", "author_id": author_id, "work_id": "no-such"},
    )
    assert bad.status_code == 404
    assert bad.json()["detail"] == "Work not found"


# --- Rights ----------------------------------------------------------------


def test_rights_crud_and_filters(client: TestClient) -> None:
    author_id = _author(client)
    work = _work(client, author_id)

    created = client.post(
        "/api/rights",
        json={
            "work_id": work["id"],
            "territory": "World",
            "language": "English",
            "film_rights": "reserved",
        },
    )
    assert created.status_code == 201, created.text
    rights_id = created.json()["id"]
    assert created.json()["film_rights"] == "reserved"
    assert created.json()["print_rights"] == "available"  # default

    assert client.get(f"/api/rights?work_id={work['id']}").json()["total"] == 1
    assert client.get("/api/rights?territory=World").json()["total"] == 1
    assert client.get("/api/rights?language=French").json()["total"] == 0

    patched = client.patch(f"/api/rights/{rights_id}", json={"film_rights": "licensed"})
    assert patched.json()["film_rights"] == "licensed"

    assert client.delete(f"/api/rights/{rights_id}").status_code == 204

    bad = client.post("/api/rights", json={"work_id": "no-such"})
    assert bad.status_code == 404
    assert bad.json()["detail"] == "Work not found"


# --- GraphicNovelProduction ------------------------------------------------


def test_graphic_novel_production_crud(client: TestClient) -> None:
    author_id = _author(client)
    work = _work(client, author_id, work_type="graphic_novel")

    created = client.post(
        "/api/graphic-novel-productions",
        json={
            "work_id": work["id"],
            "volume_number": 1,
            "script_status": "complete",
            "coloring_status": "in_progress",
        },
    )
    assert created.status_code == 201, created.text
    prod_id = created.json()["id"]
    assert created.json()["script_status"] == "complete"
    assert created.json()["lettering_status"] == "not_planned"  # default

    assert (
        client.get(f"/api/graphic-novel-productions?work_id={work['id']}").json()[
            "total"
        ]
        == 1
    )

    patched = client.patch(
        f"/api/graphic-novel-productions/{prod_id}",
        json={"page_layout_status": "blocked"},
    )
    assert patched.json()["page_layout_status"] == "blocked"

    assert (
        client.delete(f"/api/graphic-novel-productions/{prod_id}").status_code == 204
    )

    bad = client.post("/api/graphic-novel-productions", json={"work_id": "no-such"})
    assert bad.status_code == 404


# --- PublishingCalendarEvent -----------------------------------------------


def test_calendar_events_crud_and_date_range(client: TestClient) -> None:
    author_id = _author(client)
    work = _work(client, author_id)

    def ev(title: str, date_: str, etype: str, work_id=work["id"]):
        body = {"title": title, "date": date_, "event_type": etype}
        if work_id is not None:
            body["work_id"] = work_id
        r = client.post("/api/calendar-events", json=body)
        assert r.status_code == 201, r.text
        return r.json()

    ev("Reveal", "2026-03-01", "cover_reveal")
    ev("Release", "2026-06-01", "release")
    ev("House deadline", "2026-09-01", "other", work_id=None)  # no work

    assert client.get("/api/calendar-events").json()["total"] == 3
    assert client.get("/api/calendar-events?event_type=release").json()["total"] == 1
    windowed = client.get(
        "/api/calendar-events?date_from=2026-05-01&date_to=2026-07-01"
    ).json()
    assert windowed["total"] == 1
    assert windowed["items"][0]["title"] == "Release"
    assert client.get(f"/api/calendar-events?work_id={work['id']}").json()["total"] == 2


# --- IntegrationPoint registry + static descriptors coexist ----------------


def test_integration_points_crud_and_static_coexist(client: TestClient) -> None:
    # Static, code-defined descriptors still resolve.
    assert client.get("/api/integrations").status_code == 200
    assert client.get("/api/integrations/logosforge").status_code == 200

    created = client.post(
        "/api/integrations/points",
        json={
            "name": "LOGOSFORGE bridge",
            "type": "logosforge",
            "status": "planned",
            "endpoint": "logosforge://export",
        },
    )
    assert created.status_code == 201, created.text
    point_id = created.json()["id"]

    # The /points list is a paginated envelope, not swallowed by /{key}.
    listed = client.get("/api/integrations/points")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    assert (
        client.get("/api/integrations/points?type=logosforge").json()["total"] == 1
    )
    assert (
        client.get("/api/integrations/points?type=supervoid_movies").json()["total"]
        == 0
    )

    patched = client.patch(
        f"/api/integrations/points/{point_id}", json={"status": "active"}
    )
    assert patched.json()["status"] == "active"

    assert client.delete(f"/api/integrations/points/{point_id}").status_code == 204


# --- Review rubric + HOLD verdict + work link ------------------------------


def test_review_rubric_scores_and_hold(client: TestClient, session: Session) -> None:
    reviewer = _reviewer(session)
    author_id = _author(client)
    work = _work(client, author_id)
    ms = _manuscript(client, author_id, work_id=work["id"])

    created = client.post(
        "/api/reviews",
        json={
            "manuscript_id": ms["id"],
            "work_id": work["id"],
            "reviewer_id": reviewer.id,
            "verdict": "hold",
            "summary": "Hold pending second read.",
            "written_report": "Long-form assessment.",
            "literary_quality_score": 4,
            "market_potential_score": 2,
            "originality_score": 5,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["verdict"] == "hold"
    assert body["literary_quality_score"] == 4
    assert body["written_report"] == "Long-form assessment."

    assert client.get(f"/api/reviews?work_id={work['id']}").json()["total"] == 1


# --- Contract work link + expiration ---------------------------------------


def test_contract_work_link_and_filter(client: TestClient) -> None:
    author_id = _author(client)
    work = _work(client, author_id)
    ms = _manuscript(client, author_id, work_id=work["id"])

    r = client.post(
        "/api/contracts",
        json={
            "manuscript_id": ms["id"],
            "work_id": work["id"],
            "author_id": author_id,
            "expiration_date": "2030-01-01",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["work_id"] == work["id"]
    assert r.json()["expiration_date"] == "2030-01-01"

    assert client.get(f"/api/contracts?work_id={work['id']}").json()["total"] == 1


# --- EditorialNote work + subject-author links -----------------------------


def test_editorial_note_work_and_author_links(
    client: TestClient, session: Session
) -> None:
    staff = User(
        email="ed@supervoid.test",
        full_name="Ed Itor",
        role=UserRole.EDITOR,
        hashed_password=hash_password("password"),
    )
    session.add(staff)
    session.commit()
    session.refresh(staff)

    author_id = _author(client)
    work = _work(client, author_id)
    ms = _manuscript(client, author_id, work_id=work["id"])

    r = client.post(
        "/api/editorial-notes",
        json={
            "manuscript_id": ms["id"],
            "work_id": work["id"],
            "author_id": author_id,
            "author_user_id": staff.id,
            "kind": "structural",
            "body": "Tighten the middle.",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["work_id"] == work["id"]
    assert r.json()["author_id"] == author_id

    assert client.get(f"/api/editorial-notes?work_id={work['id']}").json()["total"] == 1
    assert (
        client.get(f"/api/editorial-notes?author_id={author_id}").json()["total"] == 1
    )
