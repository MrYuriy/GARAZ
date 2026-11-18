from datetime import date, timedelta

import pytest

from app.core.time import local_today
from app.enums.user import RoleEnum
from app.services.permit_expiry import expire_due_permits, seconds_until_next_run

TODAY = local_today()
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def _iso(d: date) -> str:
    return d.isoformat()


@pytest.fixture
async def admin(auth_headers):
    return await auth_headers(RoleEnum.ADMIN)


@pytest.fixture
async def refs(client, admin):
    """A site, an employer, a permit category and two truck types."""

    async def add(kind: str, name: str) -> int:
        resp = await client.post(f"/api/dictionaries/{kind}", json={"name": name}, headers=admin)
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    return {
        "site": await add("sites", "Magazyn główny"),
        "ceva": await add("employers", "CEVA Logistics"),
        "cat": await add("permit-categories", "II WJO"),
        "reach": await add("truck-types", "Wózek wysokiego składowania"),
        "front": await add("truck-types", "Wózek czołowy"),
    }


async def _operator(client, admin, refs, name="Jan Kowalski", **extra) -> dict:
    resp = await client.post(
        "/api/operators", json={"full_name": name, "employer_id": refs["ceva"], **extra}, headers=admin
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _permit(client, admin, refs, operator_id, number="P-001", valid_until=None, **extra) -> dict:
    body = {
        "operator_id": operator_id,
        "number": number,
        "category_id": refs["cat"],
        "truck_type_ids": [refs["reach"]],
        "issued_on": _iso(TODAY - timedelta(days=365)),
        "valid_until": _iso(valid_until or TODAY + timedelta(days=365)),
        **extra,
    }
    resp = await client.post("/api/permits", json=body, headers=admin)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ----- operators -----


async def test_operator_gets_a_raw_qr_token_and_no_permits_yet(client, admin, refs):
    op = await _operator(client, admin, refs, "  Jan   Kowalski ", hyster_card_number="HT-123")
    assert op["full_name"] == "Jan Kowalski"
    assert op["employer"] == {"id": refs["ceva"], "name": "CEVA Logistics"}
    assert op["site"]["name"] == "Magazyn główny"
    assert op["is_active"] is True
    assert op["permits"] == [] and op["permit_status"] is None
    assert "qr_token" not in op

    png = await client.get(f"/api/operators/{op['id']}/qr.png", headers=admin)
    assert png.status_code == 200 and png.content.startswith(b"\x89PNG")


async def test_operator_name_is_not_written_to_the_audit_log(client, admin, refs):
    op = await _operator(client, admin, refs)
    await client.patch(f"/api/operators/{op['id']}", json={"full_name": "Jan Nowak"}, headers=admin)
    logs = (await client.get(f"/api/audit-logs?resource_type=operator&resource_id={op['id']}", headers=admin)).json()
    assert "Kowalski" not in str(logs) and "Nowak" not in str(logs)
    assert logs["items"][0]["payload"] == {"full_name_changed": True}


async def test_operator_edit_clears_and_deactivates(client, admin, refs):
    op = await _operator(client, admin, refs, hyster_card_number="HT-1")
    resp = await client.patch(
        f"/api/operators/{op['id']}",
        json={"employer_id": None, "hyster_card_number": "", "is_active": False},
        headers=admin,
    )
    body = resp.json()
    assert body["employer"] is None and body["hyster_card_number"] is None and body["is_active"] is False


async def test_switched_off_employer_is_refused(client, admin, refs):
    await client.patch(f"/api/dictionaries/employers/{refs['ceva']}", json={"is_active": False}, headers=admin)
    resp = await client.post("/api/operators", json={"full_name": "Anna", "employer_id": refs["ceva"]}, headers=admin)
    assert resp.status_code == 400


async def test_operator_search_and_reissue(client, admin, refs):
    a = await _operator(client, admin, refs, "Anna Nowak", hyster_card_number="HT-77")
    await _operator(client, admin, refs, "Piotr Zieliński")
    names = [o["full_name"] for o in (await client.get("/api/operators?query=ht-77", headers=admin)).json()["items"]]
    assert names == ["Anna Nowak"]

    before = await client.get(f"/api/operators/{a['id']}/qr.png", headers=admin)
    again = await client.post(f"/api/operators/{a['id']}/qr", headers=admin)
    assert again.status_code == 200 and again.json()["qr_issued_at"] >= a["qr_issued_at"]
    after = await client.get(f"/api/operators/{a['id']}/qr.png", headers=admin)
    assert after.content != before.content


async def test_cards_pdf(client, admin, refs):
    ids = [(await _operator(client, admin, refs, f"Operator {i}"))["id"] for i in range(3)]
    resp = await client.get("/api/operators/cards.pdf", params={"ids": ids}, headers=admin)
    assert resp.status_code == 200 and resp.content.startswith(b"%PDF")
    assert (await client.get("/api/operators/cards.pdf", params={"ids": [999]}, headers=admin)).status_code == 404


async def test_manager_reads_operators_and_permits_but_cannot_change(client, admin, auth_headers, refs):
    op = await _operator(client, admin, refs)
    permit = await _permit(client, admin, refs, op["id"])
    manager = await auth_headers(RoleEnum.MANAGER)
    assert (await client.get("/api/operators", headers=manager)).json()["total"] == 1
    assert (await client.get("/api/permits", headers=manager)).json()["total"] == 1
    assert (await client.post("/api/operators", json={"full_name": "X"}, headers=manager)).status_code == 403
    assert (
        await client.patch(f"/api/permits/{permit['id']}", json={"status": "SUSPENDED"}, headers=manager)
    ).status_code == 403
    assert (
        await client.put(f"/api/permits/{permit['id']}/document", files={"file": ("a.pdf", PDF)}, headers=manager)
    ).status_code == 403


# ----- permits -----


async def test_permit_shows_on_its_operator(client, admin, refs):
    op = await _operator(client, admin, refs)
    permit = await _permit(
        client, admin, refs, op["id"], truck_type_ids=[refs["front"], refs["reach"]], basis_name=" Zaświadczenie UDT "
    )
    assert permit["status"] == "ACTIVE"
    assert permit["days_left"] == 365
    assert permit["operator"]["full_name"] == "Jan Kowalski"
    assert {t["name"] for t in permit["truck_types"]} == {"Wózek czołowy", "Wózek wysokiego składowania"}
    assert permit["basis_name"] == "Zaświadczenie UDT"
    assert permit["document"] is None

    again = (await client.get(f"/api/operators/{op['id']}", headers=admin)).json()
    assert again["permit_status"] == "ACTIVE"
    assert [p["number"] for p in again["permits"]] == ["P-001"]


async def test_permit_number_unique_and_dates_checked(client, admin, refs):
    op = await _operator(client, admin, refs)
    await _permit(client, admin, refs, op["id"], "P-001")
    dup = await client.post(
        "/api/permits",
        json={
            "operator_id": op["id"],
            "number": "p-001",
            "category_id": refs["cat"],
            "truck_type_ids": [refs["reach"]],
            "issued_on": _iso(TODAY),
            "valid_until": _iso(TODAY),
        },
        headers=admin,
    )
    assert dup.status_code == 409
    backwards = await client.post(
        "/api/permits",
        json={
            "operator_id": op["id"],
            "number": "P-002",
            "category_id": refs["cat"],
            "truck_type_ids": [refs["reach"]],
            "issued_on": _iso(TODAY),
            "valid_until": _iso(TODAY - timedelta(days=1)),
        },
        headers=admin,
    )
    assert backwards.status_code == 422
    no_types = await client.post(
        "/api/permits",
        json={
            "operator_id": op["id"],
            "number": "P-003",
            "category_id": refs["cat"],
            "truck_type_ids": [],
            "issued_on": _iso(TODAY),
            "valid_until": _iso(TODAY),
        },
        headers=admin,
    )
    assert no_types.status_code == 422


async def test_permit_already_past_its_date_is_created_expired(client, admin, refs):
    op = await _operator(client, admin, refs)
    permit = await _permit(client, admin, refs, op["id"], valid_until=TODAY - timedelta(days=1))
    assert permit["status"] == "EXPIRED" and permit["days_left"] == -1
    last_day = await _permit(client, admin, refs, op["id"], "P-002", valid_until=TODAY)
    assert last_day["status"] == "ACTIVE" and last_day["days_left"] == 0


async def test_suspend_and_lift_with_comment(client, admin, refs):
    op = await _operator(client, admin, refs)
    permit = await _permit(client, admin, refs, op["id"])
    url = f"/api/permits/{permit['id']}"

    suspended = await client.patch(url, json={"status": "SUSPENDED", "comment": "do szkolenia"}, headers=admin)
    assert suspended.json()["status"] == "SUSPENDED"
    operator = (await client.get(f"/api/operators/{op['id']}", headers=admin)).json()
    assert operator["permit_status"] == "SUSPENDED"

    lifted = await client.patch(url, json={"status": "ACTIVE"}, headers=admin)
    assert lifted.json()["status"] == "ACTIVE"

    logs = (await client.get(f"/api/audit-logs?resource_type=permit&resource_id={permit['id']}", headers=admin)).json()
    assert logs["items"][1]["payload"] == {"status": "SUSPENDED", "comment": "do szkolenia"}


async def test_expired_cannot_be_set_by_hand(client, admin, refs):
    op = await _operator(client, admin, refs)
    permit = await _permit(client, admin, refs, op["id"])
    resp = await client.patch(f"/api/permits/{permit['id']}", json={"status": "EXPIRED"}, headers=admin)
    assert resp.status_code == 422


async def test_moving_the_date_forward_revives_an_expired_permit(client, admin, refs):
    op = await _operator(client, admin, refs)
    permit = await _permit(client, admin, refs, op["id"], valid_until=TODAY - timedelta(days=3))
    url = f"/api/permits/{permit['id']}"

    # Lifting nothing: still past its date, still expired.
    assert (await client.patch(url, json={"status": "ACTIVE"}, headers=admin)).json()["status"] == "EXPIRED"

    renewed = await client.patch(url, json={"valid_until": _iso(TODAY + timedelta(days=30))}, headers=admin)
    assert renewed.json()["status"] == "ACTIVE"

    shortened = await client.patch(url, json={"valid_until": _iso(TODAY - timedelta(days=1))}, headers=admin)
    assert shortened.json()["status"] == "EXPIRED"


async def test_suspended_permit_stays_suspended_past_its_date(client, admin, refs):
    op = await _operator(client, admin, refs)
    permit = await _permit(client, admin, refs, op["id"])
    url = f"/api/permits/{permit['id']}"
    await client.patch(url, json={"status": "SUSPENDED"}, headers=admin)
    moved = await client.patch(url, json={"valid_until": _iso(TODAY - timedelta(days=1))}, headers=admin)
    assert moved.json()["status"] == "SUSPENDED"


async def test_truck_types_switched_off_may_stay_but_not_be_added(client, admin, refs):
    op = await _operator(client, admin, refs)
    permit = await _permit(client, admin, refs, op["id"], truck_type_ids=[refs["reach"]])
    await client.patch(f"/api/dictionaries/truck-types/{refs['reach']}", json={"is_active": False}, headers=admin)
    await client.patch(f"/api/dictionaries/truck-types/{refs['front']}", json={"is_active": False}, headers=admin)
    url = f"/api/permits/{permit['id']}"

    added = await client.patch(url, json={"truck_type_ids": [refs["reach"], refs["front"]]}, headers=admin)
    assert added.status_code == 400
    kept = await client.patch(url, json={"truck_type_ids": [refs["reach"]], "basis_number": "UDT/1"}, headers=admin)
    assert kept.status_code == 200 and kept.json()["basis_number"] == "UDT/1"


async def test_permit_filters(client, admin, refs):
    jan = await _operator(client, admin, refs, "Jan Kowalski")
    anna = await _operator(client, admin, refs, "Anna Nowak")
    await _permit(client, admin, refs, jan["id"], "P-1", valid_until=TODAY + timedelta(days=200))
    await _permit(client, admin, refs, anna["id"], "P-2", valid_until=TODAY + timedelta(days=10))
    await _permit(
        client, admin, refs, anna["id"], "P-3", valid_until=TODAY - timedelta(days=5), truck_type_ids=[refs["front"]]
    )

    def numbers(resp):
        return [p["number"] for p in resp.json()["items"]]

    assert numbers(await client.get("/api/permits", headers=admin)) == ["P-3", "P-2", "P-1"]
    assert numbers(await client.get("/api/permits?query=nowak", headers=admin)) == ["P-3", "P-2"]
    assert numbers(await client.get("/api/permits?expiring_within_days=30&status=ACTIVE", headers=admin)) == ["P-2"]
    assert numbers(await client.get("/api/permits?status=EXPIRED", headers=admin)) == ["P-3"]
    assert numbers(await client.get(f"/api/permits?truck_type_id={refs['front']}", headers=admin)) == ["P-3"]
    assert numbers(await client.get(f"/api/permits?operator_id={jan['id']}", headers=admin)) == ["P-1"]


# ----- the scanned document -----


async def test_document_attach_read_replace_remove(client, admin, refs):
    op = await _operator(client, admin, refs)
    permit = await _permit(client, admin, refs, op["id"])
    url = f"/api/permits/{permit['id']}/document"

    attached = await client.put(url, files={"file": ("UDT skan.pdf", PDF, "application/pdf")}, headers=admin)
    assert attached.status_code == 200, attached.text
    assert attached.json()["document"] == {
        "filename": "UDT skan.pdf",
        "content_type": "application/pdf",
        "size": len(PDF),
    }

    got = await client.get(url, headers=admin)
    assert got.content == PDF
    assert got.headers["content-type"] == "application/pdf"
    assert got.headers["content-disposition"].startswith("inline")

    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
    # The name says .pdf, the bytes say PNG: the bytes win.
    replaced = await client.put(url, files={"file": ("zdjecie.pdf", png, "application/pdf")}, headers=admin)
    assert replaced.json()["document"]["content_type"] == "image/png"
    assert replaced.json()["document"]["filename"] == "zdjecie.png"
    assert (await client.get(url, headers=admin)).content == png

    removed = await client.delete(url, headers=admin)
    assert removed.json()["document"] is None
    assert (await client.get(url, headers=admin)).status_code == 404


async def test_document_must_be_pdf_or_image_and_not_too_big(client, admin, refs, monkeypatch):
    from app.core import settings

    op = await _operator(client, admin, refs)
    permit = await _permit(client, admin, refs, op["id"])
    url = f"/api/permits/{permit['id']}/document"
    html = await client.put(url, files={"file": ("x.pdf", b"<html><script>", "application/pdf")}, headers=admin)
    assert html.status_code == 400

    monkeypatch.setattr(settings.storage, "MAX_DOCUMENT_MB", 1)
    big = await client.put(url, files={"file": ("big.pdf", PDF + b"0" * (1024 * 1024))}, headers=admin)
    assert big.status_code == 400


# ----- the daily expiry -----


async def test_daily_pass_expires_due_active_permits_only(client, admin, refs, session):
    op = await _operator(client, admin, refs)
    due = await _permit(client, admin, refs, op["id"], "P-1", valid_until=TODAY)
    suspended = await _permit(client, admin, refs, op["id"], "P-2", valid_until=TODAY)
    await client.patch(f"/api/permits/{suspended['id']}", json={"status": "SUSPENDED"}, headers=admin)
    await _permit(client, admin, refs, op["id"], "P-3", valid_until=TODAY + timedelta(days=1))

    # Today is still a valid day.
    assert await expire_due_permits(session, today=TODAY) == 0
    # Tomorrow it is not; the pass is idempotent.
    assert await expire_due_permits(session, today=TODAY + timedelta(days=1)) == 1
    assert await expire_due_permits(session, today=TODAY + timedelta(days=1)) == 0

    statuses = {p["number"]: p["status"] for p in (await client.get("/api/permits", headers=admin)).json()["items"]}
    assert statuses == {"P-1": "EXPIRED", "P-2": "SUSPENDED", "P-3": "ACTIVE"}
    logs = (await client.get("/api/audit-logs?action=permit.expired", headers=admin)).json()
    assert logs["total"] == 1 and logs["items"][0]["user_id"] is None
    assert logs["items"][0]["resource_id"] == str(due["id"])


def test_next_run_is_shortly_after_local_midnight():
    from datetime import UTC, datetime

    # 22:00 UTC on a winter day is 23:00 in Warsaw: the 00:05 run is 65 minutes away.
    assert seconds_until_next_run(datetime(2026, 1, 15, 22, 0, tzinfo=UTC)) == 65 * 60
    # 23:30 UTC is already 00:30 local: next run is tomorrow's 00:05.
    assert seconds_until_next_run(datetime(2026, 1, 15, 23, 30, tzinfo=UTC)) == (23 * 60 + 35) * 60
