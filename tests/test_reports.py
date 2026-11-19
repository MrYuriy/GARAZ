import io
from datetime import date, timedelta

from openpyxl import load_workbook
from sqlalchemy import select

from app.core.time import utcnow
from app.enums.user import RoleEnum
from app.models import AuditLog
from tests.test_incidents import _report, _staff, admin, world  # noqa: F401  (fixtures)

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _sheets(resp) -> dict[str, list[tuple]]:
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == XLSX
    assert resp.headers["content-disposition"].startswith("attachment;")
    book = load_workbook(io.BytesIO(resp.content))
    return {ws.title: list(ws.iter_rows(values_only=True)) for ws in book.worksheets}


async def _permit(client, admin, world, number: str, days: int) -> None:  # noqa: F811
    resp = await client.post(
        "/api/permits",
        json={
            "operator_id": world["operator"]["id"],
            "number": number,
            "category_id": world["pcat"],
            "truck_type_ids": [world["front"]],
            "issued_on": str(date.today() - timedelta(days=300)),
            "valid_until": str(date.today() + timedelta(days=days)),
        },
        headers=admin,
    )
    assert resp.status_code == 201, resp.text


async def test_expiring_permits_lists_active_ones_soonest_first(client, admin, auth_headers, world):  # noqa: F811
    await _permit(client, admin, world, "002/2026", 20)
    await _permit(client, admin, world, "003/2026", 5)
    await _permit(client, admin, world, "004/2026", 45)
    manager = await auth_headers(RoleEnum.MANAGER)

    body = (await client.get("/api/reports/expiring-permits", headers=manager)).json()
    assert body["days"] == 30
    assert [p["number"] for p in body["items"]] == ["003/2026", "002/2026"]
    wide = (await client.get("/api/reports/expiring-permits?days=60", headers=manager)).json()
    assert [p["number"] for p in wide["items"]] == ["003/2026", "002/2026", "004/2026"]

    rows = _sheets(await client.get("/api/reports/expiring-permits.xlsx", headers=manager))["Wygasające (30 dni)"]
    assert rows[0][0] == "Nr pozwolenia"
    assert [(r[0], r[1], r[7], r[8]) for r in rows[1:]] == [
        ("003/2026", "Jan Kowalski", 5, "Aktywne"),
        ("002/2026", "Jan Kowalski", 20, "Aktywne"),
    ]


async def test_incidents_by_truck_and_by_category(client, admin, world, sessionmaker):  # noqa: F811
    assert (await _report(client, world, out_of_service=True))[0] == 201
    assert (await _report(client, world))[0] == 201
    assert (await _report(client, world, incident_type="KOLIZJA", category_id=world["rack"]))[0] == 201
    old = utcnow() - timedelta(days=40)
    assert (await _staff(client, admin, world, occurred_at=old.isoformat()))[0] == 201

    body = (await client.get("/api/reports/incidents-by-truck", headers=admin)).json()
    [row] = body["rows"]
    assert row["truck"]["number"] == "W-01" and row["truck"]["truck_type"] == "Reach truck"
    assert row["by_type"] == {"AWARIA": 2, "USZKODZENIE": 0, "KOLIZJA": 2}
    assert row["total"] == 4 and row["out_of_service"] == 1

    since = str(date.today() - timedelta(days=7))
    recent = (await client.get(f"/api/reports/incidents-by-category?date_from={since}", headers=admin)).json()
    assert recent["date_from"] == since
    assert [(r["category"]["name"], r["total"]) for r in recent["rows"]] == [("Bateria", 2), ("Kolizja z regałem", 1)]

    rows = _sheets(await client.get("/api/reports/incidents-by-truck.xlsx", headers=admin))["Zdarzenia wg wózków"]
    assert rows[0][:8] == (
        "Wózek",
        "Typ",
        "Status wózka",
        "Awaria",
        "Uszkodzenie",
        "Kolizja",
        "Razem",
        "Wyłączony z eksploatacji",
    )
    assert rows[1][:8] == ("W-01", "Reach truck", "Wyłączony z eksploatacji", 2, 0, 2, 4, 1)
    cats = _sheets(await client.get(f"/api/reports/incidents-by-category.xlsx?date_from={since}", headers=admin))
    assert [r[0] for r in cats["Zdarzenia wg kategorii"][1:]] == ["Bateria", "Kolizja z regałem"]

    async with sessionmaker() as session:
        logged = (await session.execute(select(AuditLog).where(AuditLog.action == "report.exported"))).scalars().all()
    assert [(a.resource_type, a.payload) for a in logged] == [
        ("incidents-by-truck", {}),
        ("incidents-by-category", {"date_from": since}),
    ]


async def test_operator_history_and_register_exports(client, admin, world):  # noqa: F811
    assert (await _report(client, world, mth="10.5"))[0] == 201
    assert (await _staff(client, admin, world, operator_id=None, operator_name="Piotr Spoza"))[0] == 201

    history = _sheets(await client.get(f"/api/reports/operators/{world['operator']['id']}/history.xlsx", headers=admin))
    assert list(history) == ["Operator", "Uprawnienia", "Zdarzenia"]
    assert history["Operator"][1] == ("Imię i nazwisko", "Jan Kowalski")
    assert [r[0] for r in history["Uprawnienia"][1:]] == ["001/2026"]
    [event] = history["Zdarzenia"][1:]
    assert event[2:6] == ("W-01", "Awaria", "Bateria", "Jan Kowalski") and event[9] == 10.5
    assert (await client.get("/api/reports/operators/9999/history.xlsx", headers=admin)).status_code == 404

    incidents = _sheets(await client.get("/api/reports/incidents.xlsx?query=Spoza", headers=admin))["Zdarzenia"]
    [row] = incidents[1:]
    assert row[5:7] == ("Piotr Spoza", "NIE") and row[10] == "Osoba spoza rejestru operatorów"
    assert row[13]  # the login of whoever entered it

    permits = _sheets(await client.get("/api/reports/permits.xlsx", headers=admin))["Uprawnienia"]
    assert [r[0] for r in permits[1:]] == ["001/2026"]
    operators = _sheets(await client.get("/api/reports/operators.xlsx?is_active=true", headers=admin))["Operatorzy"]
    assert operators[1][:4] == ("Jan Kowalski", None, None, "TAK") and operators[1][5] == "001/2026"
    trucks = _sheets(await client.get("/api/reports/trucks.xlsx", headers=admin))["Wózki"]
    assert trucks[1][0] == "W-01" and trucks[1][3] == "Reach truck"


async def test_reports_need_a_staff_sign_in(client, auth_headers):
    assert (await client.get("/api/reports/expiring-permits")).status_code == 401
    assert (await client.get("/api/reports/trucks.xlsx")).status_code == 401
