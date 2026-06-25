"""The operational business layer: rights depth, CRM, editions & distribution.

Covers Part A (term windows, options, chain of title, evidence, status history,
reminders/expiry warnings, contract depth), Part B (organizations, contacts with
roles/tags, interactions, opportunities, consent) and Part C (editions and the
six validated distribution-package generators).
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient


# --- helpers ---------------------------------------------------------------


def _author(client: TestClient, name: str = "Author") -> str:
    return client.post("/api/authors", json={"full_name": name}).json()["id"]


def _work(client: TestClient, **over) -> dict:
    payload = {"title": "W", "author_id": _author(client)}
    payload.update(over)
    r = client.post("/api/works", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _rights(client: TestClient, work_id: str, **over) -> dict:
    payload = {"work_id": work_id}
    payload.update(over)
    r = client.post("/api/rights", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _edition(client: TestClient, work_id: str, **over) -> dict:
    payload = {"work_id": work_id}
    payload.update(over)
    r = client.post("/api/editions", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _iso(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


# === Part A — rights depth =================================================


def test_rights_depth_fields_persist(client: TestClient) -> None:
    w = _work(client)
    r = _rights(
        client, w["id"], exclusivity="exclusive", sublicensable=True,
        rights_holder="SUPERVOID", reversion_conditions="OOP 18 months",
        territory_coverage=["World"], language_coverage=["English", "French"],
    )
    assert r["exclusivity"] == "exclusive"
    assert r["sublicensable"] is True
    assert r["language_coverage"] == ["English", "French"]


def test_rights_child_resources_and_detail(client: TestClient) -> None:
    w = _work(client)
    r = _rights(client, w["id"])
    rid = r["id"]

    window = client.post(
        f"/api/rights/{rid}/windows",
        json={"scope": "print", "territory": "World", "starts_on": _iso(-10),
              "ends_on": _iso(365), "status": "active"},
    )
    assert window.status_code == 201, window.text

    option = client.post(
        f"/api/rights/{rid}/options",
        json={"label": "Film option", "scope": "film",
              "exercise_deadline": _iso(60), "fee": 5000, "currency": "EUR"},
    )
    assert option.status_code == 201

    chain = client.post(
        f"/api/rights/{rid}/chain-of-title",
        json={"position": 0, "entry_type": "creation",
              "from_party": "Author", "to_party": "Studio"},
    )
    assert chain.status_code == 201

    evidence = client.post(
        f"/api/rights/{rid}/evidence",
        json={"kind": "contract", "title": "Signed agreement",
              "document_ref": "contracts/x.pdf"},
    )
    assert evidence.status_code == 201

    detail = client.get(f"/api/rights/{rid}/detail").json()
    assert len(detail["windows"]) == 1
    assert len(detail["options"]) == 1
    assert len(detail["chain_of_title"]) == 1
    assert len(detail["evidence"]) == 1


def test_rights_status_history_records_and_applies(client: TestClient) -> None:
    w = _work(client)
    r = _rights(client, w["id"])  # print_rights defaults to available
    rid = r["id"]
    entry = client.post(
        f"/api/rights/{rid}/status-history",
        json={"scope": "print", "from_status": "available", "to_status": "licensed",
              "note": "Print licensed."},
    )
    assert entry.status_code == 201
    assert entry.json()["changed_by_id"] is not None  # actor recorded

    # The change is applied to the matching profile column.
    assert client.get(f"/api/rights/{rid}").json()["print_rights"] == "licensed"
    history = client.get(f"/api/rights/{rid}/status-history").json()
    assert len(history) == 1


def test_rights_warnings_sorted_by_urgency(client: TestClient) -> None:
    w = _work(client)
    # An expiry due soon …
    r = _rights(client, w["id"], expiration_date=_iso(10))
    # … and an overdue option deadline.
    client.post(
        f"/api/rights/{r['id']}/options",
        json={"label": "Lapsed option", "scope": "film", "exercise_deadline": _iso(-5)},
    )
    warnings = client.get(f"/api/rights/warnings?work_id={w['id']}").json()
    kinds = {x["kind"] for x in warnings}
    assert "expiry" in kinds
    assert "option_deadline" in kinds
    # Overdue items sort before merely-upcoming ones.
    assert warnings[0]["status"] == "overdue"


def test_contract_depth_fields_persist(client: TestClient) -> None:
    w = _work(client)
    author_id = w["author_id"]
    ms = client.post(
        "/api/manuscripts", json={"title": "MS", "author_id": author_id}
    ).json()
    contract = client.post(
        "/api/contracts",
        json={
            "manuscript_id": ms["id"], "author_id": author_id, "work_id": w["id"],
            "exclusivity": "sole", "term_end_date": _iso(365),
            "option_end_date": _iso(30), "sublicensable": True,
            "territory_coverage": ["World"], "reversion_conditions": "OOP 24 months",
        },
    )
    assert contract.status_code == 201, contract.text
    body = contract.json()
    assert body["exclusivity"] == "sole"
    assert body["sublicensable"] is True
    assert body["territory_coverage"] == ["World"]

    # Contract term/option ends surface in the rights warnings feed.
    warnings = client.get(f"/api/rights/warnings?work_id={w['id']}").json()
    assert any(x["source"] == "contract" for x in warnings)


# === Part B — relationship memory (CRM) ====================================


def test_organization_and_contact_with_org(client: TestClient) -> None:
    org = client.post(
        "/api/organizations",
        json={"name": "Éditions du Phare", "kind": "publisher", "country": "France"},
    )
    assert org.status_code == 201, org.text
    org_id = org.json()["id"]
    contact = client.post(
        "/api/contacts",
        json={"full_name": "Camille Lefevre", "organization_id": org_id,
              "consent_status": "granted", "interests": ["maps"]},
    )
    assert contact.status_code == 201, contact.text
    body = contact.json()
    assert body["consent_status"] == "granted"
    assert body["organization"]["name"] == "Éditions du Phare"


def test_contact_roles_tags_and_filters(client: TestClient) -> None:
    contact = client.post("/api/contacts", json={"full_name": "Reviewer One"}).json()
    cid = contact["id"]

    role = client.post(
        f"/api/contacts/{cid}/roles", json={"role": "reviewer", "is_primary": True}
    )
    assert role.status_code == 201

    tag = client.post("/api/contact-tags", json={"name": "VIP"}).json()
    detail = client.post(f"/api/contacts/{cid}/tags", json={"tag_id": tag["id"]}).json()
    assert detail["tags"][0]["name"] == "VIP"
    assert detail["roles"][0]["role"] == "reviewer"

    # Filters by role and tag.
    by_role = client.get("/api/contacts?role=reviewer").json()
    assert any(c["id"] == cid for c in by_role["items"])
    by_tag = client.get(f"/api/contacts?tag_id={tag['id']}").json()
    assert any(c["id"] == cid for c in by_tag["items"])


def test_interaction_is_logged_with_actor(client: TestClient) -> None:
    contact = client.post("/api/contacts", json={"full_name": "Journo"}).json()
    interaction = client.post(
        "/api/interactions",
        json={"contact_id": contact["id"], "kind": "email", "direction": "outbound",
              "subject": "Hello", "body": "ARC offer."},
    )
    assert interaction.status_code == 201, interaction.text
    assert interaction.json()["created_by_id"] is not None  # who logged it
    listed = client.get(f"/api/interactions?contact_id={contact['id']}").json()
    assert listed["total"] == 1


def test_consent_do_not_contact_is_recorded(client: TestClient) -> None:
    contact = client.post(
        "/api/contacts",
        json={"full_name": "No Mail", "do_not_contact": True,
              "consent_status": "declined"},
    ).json()
    assert contact["do_not_contact"] is True
    assert contact["consent_status"] == "declined"


def test_opportunity_pipeline(client: TestClient) -> None:
    w = _work(client)
    opp = client.post(
        "/api/opportunities",
        json={"title": "Co-edition", "kind": "co_edition", "status": "qualified",
              "work_id": w["id"], "value": 8000, "currency": "EUR"},
    )
    assert opp.status_code == 201, opp.text
    assert opp.json()["owner_id"] is not None  # owner recorded
    qualified = client.get("/api/opportunities?status=qualified").json()
    assert any(o["id"] == opp.json()["id"] for o in qualified["items"])


# === Part C — editions & distribution ======================================


def test_edition_crud_and_detail(client: TestClient) -> None:
    w = _work(client)
    e = _edition(
        client, w["id"], format="trade_paperback", identifier="9780306406157",
        identifier_type="isbn_13", page_count=288, price=24.0,
    )
    assert e["format"] == "trade_paperback"
    detail = client.get(f"/api/editions/{e['id']}/detail").json()
    assert detail["packages"] == []


def test_distribution_channels_endpoint(client: TestClient) -> None:
    channels = set(client.get("/api/distribution/channels").json())
    assert {"onix", "kdp", "ingram", "globalcomix", "press_kit", "arc"} == channels


def test_onix_validates_with_isbn_invalid_without(client: TestClient) -> None:
    w = _work(client, title="The Salt Atlases")
    # No identifier -> ONIX invalid.
    bare = _edition(client, w["id"])
    pkg = client.post(f"/api/editions/{bare['id']}/packages/onix").json()
    assert pkg["status"] == "invalid"
    assert pkg["validation"]["ok"] is False
    assert any("identifier" in e.lower() for e in pkg["validation"]["errors"])

    # Valid ISBN-13 -> validated.
    good = _edition(
        client, w["id"], identifier="9780306406157", identifier_type="isbn_13",
        price=24.0, publication_date=_iso(-30),
    )
    pkg2 = client.post(f"/api/editions/{good['id']}/packages/onix").json()
    assert pkg2["status"] == "validated"
    assert pkg2["manifest"]["ProductIdentifier"]["value"] == "9780306406157"


def test_all_generators_produce_checklists(client: TestClient) -> None:
    w = _work(client)
    e = _edition(
        client, w["id"], identifier="9780306406157", identifier_type="isbn_13",
        trim_size="6x9in", page_count=288, price=19.99, publication_date=_iso(-1),
        files=[{"role": "cover"}, {"role": "interior"}, {"role": "arc"}, {"role": "page"}],
        edition_metadata={"description": "x", "keywords": ["a"], "author_bio": "b",
                          "press_contact": "p@x", "review_guidelines": "g"},
    )
    for channel in ("onix", "kdp", "ingram", "globalcomix", "press_kit", "arc"):
        pkg = client.post(f"/api/editions/{e['id']}/packages/{channel}")
        assert pkg.status_code == 201, f"{channel}: {pkg.text}"
        body = pkg.json()
        assert body["channel"] == channel
        assert len(body["checklist"]) > 0
        # Generators prepare/validate; they never claim to upload.
        assert body["manifest"].get("note", "").lower().find("upload") == -1 or "not" in body["manifest"]["note"].lower()

    listed = client.get(f"/api/editions/{e['id']}/packages").json()
    assert len(listed) == 6


def test_kdp_requires_cover_and_description(client: TestClient) -> None:
    w = _work(client)
    e = _edition(client, w["id"], format="ebook")  # no files, no description
    pkg = client.post(f"/api/editions/{e['id']}/packages/kdp").json()
    assert pkg["status"] == "invalid"
    failed = {c["key"] for c in pkg["checklist"] if c["status"] == "fail"}
    assert "cover" in failed
    assert "description" in failed


# === auth ==================================================================


def test_business_layer_requires_auth(anon_client: TestClient, client: TestClient) -> None:
    w = _work(client)
    assert anon_client.post("/api/rights", json={"work_id": w["id"]}).status_code == 401
    assert anon_client.post("/api/contacts", json={"full_name": "x"}).status_code == 401
    assert anon_client.post("/api/editions", json={"work_id": w["id"]}).status_code == 401
    e = _edition(client, w["id"])
    assert anon_client.post(f"/api/editions/{e['id']}/packages/onix").status_code == 401
