import pytest

from app.enums.user import RoleEnum


@pytest.fixture
async def admin(auth_headers):
    return await auth_headers(RoleEnum.ADMIN)


async def _maker(client, admin, name: str) -> dict:
    resp = await client.post("/api/truck-manufacturers", json={"name": name}, headers=admin)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _model(client, admin, maker_id: int, name: str) -> dict:
    resp = await client.post("/api/truck-models", json={"manufacturer_id": maker_id, "name": name}, headers=admin)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _truck(client, admin, number: str, **make) -> dict:
    kind = (await client.post("/api/dictionaries/truck-types", json={"name": f"Typ {number}"}, headers=admin)).json()
    if not (await client.get("/api/dictionaries/sites", headers=admin)).json():
        await client.post("/api/dictionaries/sites", json={"name": "Magazyn"}, headers=admin)
    resp = await client.post("/api/trucks", json={"number": number, "truck_type_id": kind["id"], **make}, headers=admin)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_lists_manufacturers_with_models_and_use_counts(client, admin):
    linde = await _maker(client, admin, " Linde ")
    await _maker(client, admin, "Jungheinrich")
    r14 = await _model(client, admin, linde["id"], "R14")
    await _model(client, admin, linde["id"], "E20")
    await _truck(client, admin, "W-01", model_id=r14["id"])

    listed = (await client.get("/api/truck-manufacturers", headers=admin)).json()
    assert [m["name"] for m in listed] == ["Jungheinrich", "Linde"]
    assert listed[1]["truck_count"] == 1
    assert [(m["name"], m["truck_count"]) for m in listed[1]["models"]] == [("E20", 0), ("R14", 1)]


async def test_names_are_unique_ignoring_case(client, admin):
    linde = await _maker(client, admin, "Linde")
    assert (await client.post("/api/truck-manufacturers", json={"name": "LINDE"}, headers=admin)).status_code == 409
    await _model(client, admin, linde["id"], "R14")
    dup = await client.post("/api/truck-models", json={"manufacturer_id": linde["id"], "name": "r14"}, headers=admin)
    assert dup.status_code == 409
    # The same model name under another manufacturer is fine.
    other = await _maker(client, admin, "Still")
    await _model(client, admin, other["id"], "R14")


async def test_rename(client, admin):
    linde = await _maker(client, admin, "Lnide")
    model = await _model(client, admin, linde["id"], "R41")
    renamed = await client.patch(f"/api/truck-manufacturers/{linde['id']}", json={"name": "Linde"}, headers=admin)
    assert renamed.json()["name"] == "Linde"
    fixed = await client.patch(f"/api/truck-models/{model['id']}", json={"name": "R14"}, headers=admin)
    assert fixed.json()["name"] == "R14"
    logs = (await client.get("/api/audit-logs?action=truck_manufacturer.updated", headers=admin)).json()
    assert logs["items"][0]["payload"] == {"name": "Linde", "old_name": "Lnide"}


async def test_a_model_in_use_cannot_be_deleted_until_its_trucks_change(client, admin):
    linde = await _maker(client, admin, "Linde")
    r14 = await _model(client, admin, linde["id"], "R14")
    e20 = await _model(client, admin, linde["id"], "E20")
    truck = await _truck(client, admin, "W-07", model_id=r14["id"])

    refused = await client.delete(f"/api/truck-models/{r14['id']}", headers=admin)
    assert refused.status_code == 409
    assert refused.json()["trucks"] == [{"id": truck["id"], "number": "W-07"}]

    await client.patch(f"/api/trucks/{truck['id']}", json={"model_id": e20["id"]}, headers=admin)
    assert (await client.delete(f"/api/truck-models/{r14['id']}", headers=admin)).status_code == 204
    models = (await client.get("/api/truck-manufacturers", headers=admin)).json()[0]["models"]
    assert [m["name"] for m in models] == ["E20"]


async def test_a_manufacturer_in_use_cannot_be_deleted_until_its_trucks_go(client, admin):
    linde = await _maker(client, admin, "Linde")
    await _model(client, admin, linde["id"], "R14")
    truck = await _truck(client, admin, "W-08", manufacturer_id=linde["id"])

    refused = await client.delete(f"/api/truck-manufacturers/{linde['id']}", headers=admin)
    assert refused.status_code == 409
    assert [t["number"] for t in refused.json()["trucks"]] == ["W-08"]

    await client.delete(f"/api/trucks/{truck['id']}", headers=admin)
    assert (await client.delete(f"/api/truck-manufacturers/{linde['id']}", headers=admin)).status_code == 204
    assert (await client.get("/api/truck-manufacturers", headers=admin)).json() == []
    logs = (await client.get("/api/audit-logs?action=truck_manufacturer.deleted", headers=admin)).json()
    assert logs["items"][0]["payload"] == {"name": "Linde", "models": ["R14"]}


async def test_a_manager_reads_but_cannot_change(client, admin, auth_headers):
    linde = await _maker(client, admin, "Linde")
    manager = await auth_headers(RoleEnum.MANAGER)
    assert len((await client.get("/api/truck-manufacturers", headers=manager)).json()) == 1
    assert (await client.post("/api/truck-manufacturers", json={"name": "X"}, headers=manager)).status_code == 403
    assert (await client.delete(f"/api/truck-manufacturers/{linde['id']}", headers=manager)).status_code == 403
    body = {"manufacturer_id": linde["id"], "name": "R14"}
    assert (await client.post("/api/truck-models", json=body, headers=manager)).status_code == 403
