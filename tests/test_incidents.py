import io
import json
import uuid
from datetime import date, timedelta

import pytest
from PIL import Image
from sqlalchemy import select

from app.core.time import utcnow
from app.enums.user import RoleEnum
from app.models import Operator


@pytest.fixture
async def admin(auth_headers):
    return await auth_headers(RoleEnum.ADMIN)


@pytest.fixture
async def world(client, admin, sessionmaker):
    """A truck, an operator with a permit for its type, and categories — as an admin sets them up."""

    async def post(path: str, body: dict) -> dict:
        resp = await client.post(path, json=body, headers=admin)
        assert resp.status_code == 201, resp.text
        return resp.json()

    await post("/api/dictionaries/sites", {"name": "Magazyn"})
    reach = await post("/api/dictionaries/truck-types", {"name": "Reach truck"})
    front = await post("/api/dictionaries/truck-types", {"name": "Czołowy"})
    battery = await post(
        "/api/dictionaries/incident-categories",
        {"name": "Bateria", "incident_types": ["AWARIA", "USZKODZENIE"], "default_out_of_service": True},
    )
    rack = await post(
        "/api/dictionaries/incident-categories", {"name": "Kolizja z regałem", "incident_types": ["KOLIZJA"]}
    )
    pcat = await post("/api/dictionaries/permit-categories", {"name": "II WJO"})
    truck = await post("/api/trucks", {"number": "W-01", "truck_type_id": reach["id"]})
    operator = await post("/api/operators", {"full_name": "Jan Kowalski"})
    await post(
        "/api/permits",
        {
            "operator_id": operator["id"],
            "number": "001/2026",
            "category_id": pcat["id"],
            "truck_type_ids": [reach["id"]],
            "issued_on": str(date.today() - timedelta(days=100)),
            "valid_until": str(date.today() + timedelta(days=300)),
        },
    )
    async with sessionmaker() as session:
        # The token is never sent by the API; read it the way the card printer does.
        op_token = (await session.execute(select(Operator.qr_token).where(Operator.id == operator["id"]))).scalar_one()
    return {
        "truck": truck,
        "truck_token": truck["qr_url"].rsplit("/", 1)[1],
        "operator": operator,
        "operator_token": op_token,
        "battery": battery["id"],
        "rack": rack["id"],
        "reach": reach["id"],
        "front": front["id"],
        "pcat": pcat["id"],
    }


def _jpeg(size=(1600, 1200), color="red", exif_gps=False) -> bytes:
    image = Image.new("RGB", size, color)
    out = io.BytesIO()
    kwargs = {}
    if exif_gps:
        exif = Image.Exif()
        exif[0x010F] = "Phone maker"  # Make
        kwargs["exif"] = exif
    image.save(out, "JPEG", **kwargs)
    return out.getvalue()


async def _report(client, world, photos=None, **fields) -> tuple[int, dict]:
    data = {
        "client_uuid": str(uuid.uuid4()),
        "truck_token": world["truck_token"],
        "operator_token": world["operator_token"],
        "incident_type": "AWARIA",
        "category_id": world["battery"],
        "description": "Bateria nie ładuje",
        **fields,
    }
    files = [("photos", (f"p{i}.jpg", p, "image/jpeg")) for i, p in enumerate(photos or [_jpeg()])]
    resp = await client.post("/api/public/incidents", data={"data": json.dumps(data)}, files=files)
    return resp.status_code, resp.json()


async def test_scanning_a_truck_shows_it_with_the_categories(client, world):
    resp = await client.get(f"/api/public/trucks/{world['truck_token']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["number"] == "W-01" and body["truck_type"] == "Reach truck" and body["last_mth"] is None
    assert {c["name"]: c["default_out_of_service"] for c in body["categories"]} == {
        "Bateria": True,
        "Kolizja z regałem": False,
    }
    assert (await client.get("/api/public/trucks/unknown-token-123")).status_code == 404


async def test_a_truck_out_of_the_fleet_cannot_be_reported(client, admin, world):
    await client.patch(f"/api/trucks/{world['truck']['id']}", json={"status": "INACTIVE"}, headers=admin)
    assert (await client.get(f"/api/public/trucks/{world['truck_token']}")).status_code == 404


async def test_an_operator_card_needs_a_truck_code(client, world):
    ok = await client.post(
        "/api/public/operators/check",
        json={"truck_token": world["truck_token"], "operator_token": world["operator_token"]},
    )
    assert ok.json() == {"display_name": "Jan K."}
    alone = await client.post(
        "/api/public/operators/check",
        json={"truck_token": "not-a-truck-123", "operator_token": world["operator_token"]},
    )
    assert alone.status_code == 404


async def test_a_report_is_saved_with_photos_history_and_audit(client, admin, world):
    status, body = await _report(client, world, photos=[_jpeg(exif_gps=True), _jpeg((800, 600), "blue")], mth="1234.5")
    assert status == 201, body
    assert body["created"] is True

    incident = (await client.get(f"/api/incidents/{body['id']}", headers=admin)).json()
    assert incident["status"] == "NEW"
    assert incident["flags"] == []  # a valid permit for this truck type
    assert incident["mth"] == 1234.5
    assert incident["truck"]["number"] == "W-01" and incident["operator"]["full_name"] == "Jan Kowalski"
    assert [e["to_status"] for e in incident["events"]] == ["NEW"] and incident["events"][0]["user"] is None
    assert len(incident["photos"]) == 2

    first = incident["photos"][0]
    full = await client.get(f"/api/incidents/{body['id']}/photos/{first['id']}", headers=admin)
    stored = Image.open(io.BytesIO(full.content))
    assert stored.format == "JPEG" and max(stored.size) <= 2048
    assert not stored.getexif()  # re-encoded: no EXIF goes into storage
    thumb = await client.get(f"/api/incidents/{body['id']}/photos/{first['id']}?thumb=true", headers=admin)
    assert max(Image.open(io.BytesIO(thumb.content)).size) <= 320

    logs = (await client.get("/api/audit-logs?action=incident.created", headers=admin)).json()
    assert logs["items"][0]["user_id"] is None and logs["items"][0]["payload"]["photos"] == 2


async def test_sending_the_same_report_again_files_it_once(client, admin, world):
    client_uuid = str(uuid.uuid4())
    _, first = await _report(client, world, client_uuid=client_uuid)
    status, again = await _report(client, world, client_uuid=client_uuid)
    assert status == 201 and again == {**first, "created": False}
    assert (await client.get("/api/incidents", headers=admin)).json()["total"] == 1


async def test_a_report_needs_a_photo_that_is_an_image(client, world):
    data = {
        "client_uuid": str(uuid.uuid4()),
        "truck_token": world["truck_token"],
        "operator_token": world["operator_token"],
        "incident_type": "AWARIA",
        "category_id": world["battery"],
    }
    none = await client.post("/api/public/incidents", data={"data": json.dumps(data)})
    assert none.status_code == 422
    status, _ = await _report(client, world, photos=[b"%PDF-1.4 not a photo"])
    assert status == 400


async def test_the_category_must_fit_the_type(client, world):
    status, body = await _report(client, world, incident_type="KOLIZJA", category_id=world["battery"])
    assert status == 400, body
    status, _ = await _report(client, world, incident_type="KOLIZJA", category_id=world["rack"])
    assert status == 201


async def test_out_of_service_stops_the_truck(client, admin, world):
    status, body = await _report(client, world, out_of_service=True)
    assert status == 201 and body["truck_out_of_service"] is True
    truck = (await client.get(f"/api/trucks/{world['truck']['id']}", headers=admin)).json()
    assert truck["status"] == "OUT_OF_SERVICE"
    logs = (await client.get(f"/api/audit-logs?resource_type=truck&resource_id={truck['id']}", headers=admin)).json()
    assert logs["items"][0]["payload"] == {"status": "OUT_OF_SERVICE", "incident_id": body["id"]}


async def test_flags_mark_permit_and_hour_meter_problems(client, admin, world):
    _, first = await _report(client, world, mth="1000")
    _, lower = await _report(client, world, mth="900.5")
    flags = (await client.get(f"/api/incidents/{lower['id']}", headers=admin)).json()["flags"]
    assert flags == ["MTH_LOWER_THAN_LAST"]

    # The same operator on a truck type the permit does not cover.
    other = await client.post("/api/trucks", json={"number": "C-01", "truck_type_id": world["front"]}, headers=admin)
    other_token = other.json()["qr_url"].rsplit("/", 1)[1]
    _, wrong_type = await _report(client, world, truck_token=other_token)
    assert (await client.get(f"/api/incidents/{wrong_type['id']}", headers=admin)).json()["flags"] == [
        "TRUCK_TYPE_NOT_PERMITTED"
    ]

    # A suspended permit leaves no active one; the report is still accepted.
    permit = (await client.get("/api/permits", headers=admin)).json()["items"][0]
    await client.patch(f"/api/permits/{permit['id']}", json={"status": "SUSPENDED"}, headers=admin)
    status, none = await _report(client, world)
    assert status == 201
    assert (await client.get(f"/api/incidents/{none['id']}", headers=admin)).json()["flags"] == ["NO_ACTIVE_PERMIT"]

    flagged = (await client.get("/api/incidents?flagged=true", headers=admin)).json()
    assert flagged["total"] == 3
    clean = (await client.get("/api/incidents?flagged=false", headers=admin)).json()
    assert [i["id"] for i in clean["items"]] == [first["id"]]

    scan = (await client.get(f"/api/public/trucks/{world['truck_token']}")).json()
    assert scan["last_mth"] == 900.5


async def test_the_phone_time_is_kept_when_plausible(client, admin, world):
    yesterday = utcnow() - timedelta(days=1)
    _, recent = await _report(client, world, reported_at=yesterday.isoformat())
    _, ancient = await _report(client, world, reported_at=(utcnow() - timedelta(days=30)).isoformat())
    recent_at = (await client.get(f"/api/incidents/{recent['id']}", headers=admin)).json()["occurred_at"]
    ancient_at = (await client.get(f"/api/incidents/{ancient['id']}", headers=admin)).json()["occurred_at"]
    assert recent_at.startswith(yesterday.date().isoformat())
    assert ancient_at.startswith(utcnow().date().isoformat())


async def test_admin_moves_a_report_along_with_comments(client, admin, auth_headers, world):
    _, body = await _report(client, world)
    url = f"/api/incidents/{body['id']}"
    manager = await auth_headers(RoleEnum.MANAGER)
    assert (await client.get(url, headers=manager)).status_code == 200
    assert (await client.patch(url, json={"status": "CLOSED"}, headers=manager)).status_code == 403

    await client.patch(url, json={"status": "IN_PROGRESS", "comment": "Serwis zamówiony"}, headers=admin)
    await client.patch(url, json={"comment": "Czekamy na część"}, headers=admin)
    done = (await client.patch(url, json={"status": "CLOSED"}, headers=admin)).json()

    assert done["status"] == "CLOSED"
    steps = [(e["from_status"], e["to_status"], e["comment"]) for e in done["events"]]
    assert steps == [
        (None, "NEW", None),
        ("NEW", "IN_PROGRESS", "Serwis zamówiony"),
        ("IN_PROGRESS", "IN_PROGRESS", "Czekamy na część"),
        ("IN_PROGRESS", "CLOSED", None),
    ]
    assert done["events"][1]["user"]["login"]
    assert (await client.get("/api/incidents?status=CLOSED", headers=admin)).json()["total"] == 1
    assert (await client.get("/api/incidents?open=true", headers=admin)).json()["total"] == 0
    assert (await client.get("/api/incidents?query=kowal", headers=admin)).json()["total"] == 1
    assert (await client.get("/api/incidents?query=zzz", headers=admin)).json()["total"] == 0


async def test_the_sticker_link_opens_the_web_form(client, world):
    resp = await client.get(f"/t/{world['truck_token']}", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == f"/app/#/t/{world['truck_token']}"
    assert (await client.get("/t/<script>", follow_redirects=False)).status_code == 404
