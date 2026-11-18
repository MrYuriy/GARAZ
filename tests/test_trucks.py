import pytest
from PIL import Image  # comes with reportlab

from app.core import settings
from app.enums.user import RoleEnum


@pytest.fixture
async def admin(auth_headers):
    return await auth_headers(RoleEnum.ADMIN)


@pytest.fixture
async def setup(client, admin):
    """One site and two truck types, as an administrator would add them."""

    async def add(kind: str, name: str) -> int:
        resp = await client.post(f"/api/dictionaries/{kind}", json={"name": name}, headers=admin)
        return resp.json()["id"]

    async def maker(name: str, *models: str) -> dict:
        made = (await client.post("/api/truck-manufacturers", json={"name": name}, headers=admin)).json()
        ids = {"id": made["id"]}
        for m in models:
            body = {"manufacturer_id": made["id"], "name": m}
            ids[m] = (await client.post("/api/truck-models", json=body, headers=admin)).json()["id"]
        return ids

    return {
        "site": await add("sites", "Magazyn główny"),
        "reach": await add("truck-types", "Wózek wysokiego składowania"),
        "front": await add("truck-types", "Wózek czołowy"),
        "linde": await maker("Linde", "R14", "E20"),
        "jung": await maker("Jungheinrich", "ETV 216"),
    }


async def _add(client, headers, setup, number="W-01", **extra) -> dict:
    resp = await client.post(
        "/api/trucks", json={"number": number, "truck_type_id": setup["reach"], **extra}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_admin_adds_a_truck_with_a_qr_link(client, admin, setup, monkeypatch):
    monkeypatch.setattr(settings.app, "BASE_URL", "https://garaz.example.pl/")
    truck = await _add(client, admin, setup, "  W-01 ", model_id=setup["linde"]["R14"])

    assert truck["number"] == "W-01"
    assert truck["status"] == "ACTIVE"
    assert truck["site"] == {"id": setup["site"], "name": "Magazyn główny"}
    assert truck["truck_type"]["name"] == "Wózek wysokiego składowania"
    assert truck["qr_url"].startswith("https://garaz.example.pl/t/")
    token = truck["qr_url"].rsplit("/", 1)[1]
    assert len(token) >= 30 and "W-01" not in token  # nothing readable in the code
    assert "qr_token" not in truck
    # The model brings its manufacturer.
    assert truck["manufacturer"] == {"id": setup["linde"]["id"], "name": "Linde"}
    assert truck["model"] == {"id": setup["linde"]["R14"], "name": "R14"}


async def test_number_is_unique_ignoring_case(client, admin, setup):
    await _add(client, admin, setup, "W-01")
    dup = await client.post("/api/trucks", json={"number": "w-01", "truck_type_id": setup["reach"]}, headers=admin)
    assert dup.status_code == 409


async def test_site_must_be_given_when_there_are_several(client, admin, setup):
    await client.post("/api/dictionaries/sites", json={"name": "Magazyn 2"}, headers=admin)
    resp = await client.post("/api/trucks", json={"number": "W-02", "truck_type_id": setup["reach"]}, headers=admin)
    assert resp.status_code == 400
    ok = await client.post(
        "/api/trucks", json={"number": "W-02", "truck_type_id": setup["reach"], "site_id": setup["site"]}, headers=admin
    )
    assert ok.status_code == 201


async def test_switched_off_or_unknown_type_is_refused(client, admin, setup):
    await client.patch(f"/api/dictionaries/truck-types/{setup['front']}", json={"is_active": False}, headers=admin)
    off = await client.post("/api/trucks", json={"number": "W-03", "truck_type_id": setup["front"]}, headers=admin)
    assert off.status_code == 400
    unknown = await client.post("/api/trucks", json={"number": "W-03", "truck_type_id": 999}, headers=admin)
    assert unknown.status_code == 400


async def test_a_manager_reads_but_cannot_change(client, admin, auth_headers, setup):
    truck = await _add(client, admin, setup)
    manager = await auth_headers(RoleEnum.MANAGER)
    assert (await client.get("/api/trucks", headers=manager)).json()["total"] == 1
    assert (await client.get(f"/api/trucks/{truck['id']}/qr.png", headers=manager)).status_code == 200
    assert (
        await client.patch(f"/api/trucks/{truck['id']}", json={"status": "INACTIVE"}, headers=manager)
    ).status_code == 403
    assert (await client.post(f"/api/trucks/{truck['id']}/qr", headers=manager)).status_code == 403


async def test_search_and_filters(client, admin, setup):
    await _add(client, admin, setup, "W-01", manufacturer_id=setup["linde"]["id"])
    await _add(client, admin, setup, "W-02", model_id=setup["jung"]["ETV 216"])
    front = await client.post("/api/trucks", json={"number": "C-01", "truck_type_id": setup["front"]}, headers=admin)
    await client.patch(f"/api/trucks/{front.json()['id']}", json={"status": "OUT_OF_SERVICE"}, headers=admin)

    def numbers(resp):
        return [t["number"] for t in resp.json()["items"]]

    assert numbers(await client.get("/api/trucks", headers=admin)) == ["C-01", "W-01", "W-02"]
    assert numbers(await client.get("/api/trucks?query=jung", headers=admin)) == ["W-02"]
    assert numbers(await client.get("/api/trucks?query=etv", headers=admin)) == ["W-02"]
    assert numbers(await client.get("/api/trucks?status=OUT_OF_SERVICE", headers=admin)) == ["C-01"]
    assert numbers(await client.get(f"/api/trucks?truck_type_id={setup['reach']}", headers=admin)) == ["W-01", "W-02"]


async def test_edit_clears_fields_and_audits_status_with_comment(client, admin, setup):
    truck = await _add(client, admin, setup, model_id=setup["linde"]["R14"])
    url = f"/api/trucks/{truck['id']}"

    stopped = await client.patch(
        url, json={"status": "OUT_OF_SERVICE", "model_id": None, "truck_type_id": setup["front"]}, headers=admin
    )
    assert stopped.status_code == 200
    body = stopped.json()
    assert body["status"] == "OUT_OF_SERVICE"
    assert body["model"] is None and body["manufacturer"]["name"] == "Linde"
    assert body["truck_type"]["name"] == "Wózek czołowy"

    back = await client.patch(url, json={"status": "ACTIVE", "comment": "naprawa zakończona"}, headers=admin)
    assert back.json()["status"] == "ACTIVE"

    logs = (await client.get(f"/api/audit-logs?resource_type=truck&resource_id={truck['id']}", headers=admin)).json()
    assert logs["items"][0]["payload"] == {"status": "ACTIVE", "comment": "naprawa zakończona"}
    assert [log["action"] for log in logs["items"]] == ["truck.updated", "truck.updated", "truck.created"]


async def test_renaming_onto_another_number_is_refused(client, admin, setup):
    await _add(client, admin, setup, "W-01")
    second = await _add(client, admin, setup, "W-02")
    resp = await client.patch(f"/api/trucks/{second['id']}", json={"number": "w-01"}, headers=admin)
    assert resp.status_code == 409


async def test_reissuing_the_qr_changes_the_link(client, admin, setup):
    truck = await _add(client, admin, setup)
    fresh = await client.post(f"/api/trucks/{truck['id']}/qr", headers=admin)
    assert fresh.status_code == 200
    assert fresh.json()["qr_url"] != truck["qr_url"]
    logs = (await client.get("/api/audit-logs?action=truck.qr_reissued", headers=admin)).json()
    assert logs["total"] == 1


async def test_qr_png_is_a_valid_image(client, admin, setup, tmp_path):
    truck = await _add(client, admin, setup)
    resp = await client.get(f"/api/trucks/{truck['id']}/qr.png", headers=admin)
    assert resp.headers["content-type"] == "image/png"
    assert "qr-W-01.png" in resp.headers["content-disposition"]
    path = tmp_path / "qr.png"
    path.write_bytes(resp.content)
    with Image.open(path) as image:
        assert image.size[0] == image.size[1] >= 200


async def test_labels_pdf_has_one_page_per_eight_trucks(client, admin, setup):
    ids = [(await _add(client, admin, setup, f"W-{i:02}"))["id"] for i in range(9)]
    resp = await client.get("/api/trucks/labels.pdf", params={"ids": ids}, headers=admin)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    assert b"/Count 2" in resp.content  # 9 labels, 8 per sheet


async def test_labels_need_known_trucks(client, admin, setup):
    resp = await client.get("/api/trucks/labels.pdf", params={"ids": [999]}, headers=admin)
    assert resp.status_code == 404
    assert (await client.get("/api/trucks/labels.pdf", headers=admin)).status_code == 422


async def test_a_model_must_belong_to_the_manufacturer(client, admin, setup):
    resp = await client.post(
        "/api/trucks",
        json={
            "number": "W-09",
            "truck_type_id": setup["reach"],
            "manufacturer_id": setup["jung"]["id"],
            "model_id": setup["linde"]["R14"],
        },
        headers=admin,
    )
    assert resp.status_code == 400
    unknown = await client.post(
        "/api/trucks", json={"number": "W-09", "truck_type_id": setup["reach"], "model_id": 999}, headers=admin
    )
    assert unknown.status_code == 400


async def test_changing_the_manufacturer_drops_the_old_model(client, admin, setup):
    truck = await _add(client, admin, setup, model_id=setup["linde"]["E20"])
    url = f"/api/trucks/{truck['id']}"
    moved = (await client.patch(url, json={"manufacturer_id": setup["jung"]["id"]}, headers=admin)).json()
    assert moved["manufacturer"]["name"] == "Jungheinrich" and moved["model"] is None
    picked = (await client.patch(url, json={"model_id": setup["jung"]["ETV 216"]}, headers=admin)).json()
    assert picked["model"]["name"] == "ETV 216"
    cleared = (await client.patch(url, json={"manufacturer_id": None}, headers=admin)).json()
    assert cleared["manufacturer"] is None and cleared["model"] is None


async def test_admin_deletes_a_truck(client, admin, auth_headers, setup):
    truck = await _add(client, admin, setup)
    manager = await auth_headers(RoleEnum.MANAGER)
    assert (await client.delete(f"/api/trucks/{truck['id']}", headers=manager)).status_code == 403
    assert (await client.delete(f"/api/trucks/{truck['id']}", headers=admin)).status_code == 204
    assert (await client.get(f"/api/trucks/{truck['id']}", headers=admin)).status_code == 404
    logs = (await client.get("/api/audit-logs?action=truck.deleted", headers=admin)).json()
    assert logs["items"][0]["payload"] == {"number": "W-01"}
