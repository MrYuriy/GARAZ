import pytest

from app.enums.user import RoleEnum

KINDS = ["sites", "permit-categories", "truck-types", "employers"]


@pytest.mark.parametrize("kind", KINDS)
async def test_admin_adds_and_everyone_staff_reads(client, auth_headers, kind):
    admin = await auth_headers(RoleEnum.ADMIN)
    manager = await auth_headers(RoleEnum.MANAGER)

    resp = await client.post(f"/api/dictionaries/{kind}", json={"name": "  Pozycja   A "}, headers=admin)
    assert resp.status_code == 201
    assert resp.json()["name"] == "Pozycja A"  # spaces tidied
    assert resp.json()["incident_types"] is None

    listed = await client.get(f"/api/dictionaries/{kind}", headers=manager)
    assert [e["name"] for e in listed.json()] == ["Pozycja A"]


async def test_a_manager_cannot_change_lists(client, auth_headers):
    manager = await auth_headers(RoleEnum.MANAGER)
    resp = await client.post("/api/dictionaries/employers", json={"name": "Agencja X"}, headers=manager)
    assert resp.status_code == 403


async def test_reading_needs_a_sign_in(client):
    assert (await client.get("/api/dictionaries/truck-types")).status_code == 401


async def test_unknown_list_is_a_422(client, auth_headers):
    admin = await auth_headers(RoleEnum.ADMIN)
    assert (await client.get("/api/dictionaries/colours", headers=admin)).status_code == 422


async def test_names_are_unique_ignoring_case(client, auth_headers):
    admin = await auth_headers(RoleEnum.ADMIN)
    await client.post("/api/dictionaries/truck-types", json={"name": "Reach truck"}, headers=admin)
    dup = await client.post("/api/dictionaries/truck-types", json={"name": "reach TRUCK"}, headers=admin)
    assert dup.status_code == 409
    # The same name in another list is fine.
    other = await client.post("/api/dictionaries/permit-categories", json={"name": "Reach truck"}, headers=admin)
    assert other.status_code == 201


async def test_blank_name_is_refused(client, auth_headers):
    admin = await auth_headers(RoleEnum.ADMIN)
    assert (await client.post("/api/dictionaries/employers", json={"name": "   "}, headers=admin)).status_code == 422


async def test_switched_off_entries_hide_but_stay(client, auth_headers):
    admin = await auth_headers(RoleEnum.ADMIN)
    entry = (await client.post("/api/dictionaries/employers", json={"name": "Stara agencja"}, headers=admin)).json()

    off = await client.patch(f"/api/dictionaries/employers/{entry['id']}", json={"is_active": False}, headers=admin)
    assert off.json()["is_active"] is False
    assert (await client.get("/api/dictionaries/employers", headers=admin)).json() == []
    everything = await client.get("/api/dictionaries/employers?include_inactive=true", headers=admin)
    assert [e["name"] for e in everything.json()] == ["Stara agencja"]


async def test_rename_reorder_and_case_only_rename(client, auth_headers):
    admin = await auth_headers(RoleEnum.ADMIN)
    a = (await client.post("/api/dictionaries/sites", json={"name": "B", "sort_order": 1}, headers=admin)).json()
    await client.post("/api/dictionaries/sites", json={"name": "A", "sort_order": 2}, headers=admin)
    names = [e["name"] for e in (await client.get("/api/dictionaries/sites", headers=admin)).json()]
    assert names == ["B", "A"]  # sort_order first, then name

    renamed = await client.patch(f"/api/dictionaries/sites/{a['id']}", json={"name": "b"}, headers=admin)
    assert renamed.status_code == 200 and renamed.json()["name"] == "b"
    clash = await client.patch(f"/api/dictionaries/sites/{a['id']}", json={"name": "a"}, headers=admin)
    assert clash.status_code == 409


async def test_missing_entry_is_a_404(client, auth_headers):
    admin = await auth_headers(RoleEnum.ADMIN)
    resp = await client.patch("/api/dictionaries/sites/999", json={"name": "X"}, headers=admin)
    assert resp.status_code == 404


async def test_incident_category_needs_types_and_keeps_its_default(client, auth_headers):
    admin = await auth_headers(RoleEnum.ADMIN)
    url = "/api/dictionaries/incident-categories"
    assert (await client.post(url, json={"name": "Hamulce"}, headers=admin)).status_code == 400

    created = await client.post(
        url,
        json={"name": "Hamulce", "incident_types": ["USZKODZENIE", "AWARIA", "AWARIA"], "default_out_of_service": True},
        headers=admin,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["incident_types"] == ["AWARIA", "USZKODZENIE"]  # deduplicated, ordered
    assert body["default_out_of_service"] is True

    emptied = await client.patch(f"{url}/{body['id']}", json={"incident_types": []}, headers=admin)
    assert emptied.status_code == 400


async def test_incident_fields_are_refused_on_other_lists(client, auth_headers):
    admin = await auth_headers(RoleEnum.ADMIN)
    resp = await client.post(
        "/api/dictionaries/truck-types", json={"name": "Paleciak", "incident_types": ["AWARIA"]}, headers=admin
    )
    assert resp.status_code == 400


async def test_categories_filter_by_incident_type(client, auth_headers):
    admin = await auth_headers(RoleEnum.ADMIN)
    url = "/api/dictionaries/incident-categories"
    await client.post(url, json={"name": "Maszt", "incident_types": ["AWARIA", "USZKODZENIE"]}, headers=admin)
    await client.post(url, json={"name": "Kolizja z regałem", "incident_types": ["KOLIZJA"]}, headers=admin)
    await client.post(url, json={"name": "Inne", "incident_types": ["AWARIA", "USZKODZENIE", "KOLIZJA"]}, headers=admin)

    collision = await client.get(f"{url}?incident_type=KOLIZJA", headers=admin)
    assert [e["name"] for e in collision.json()] == ["Inne", "Kolizja z regałem"]
    wrong_list = await client.get("/api/dictionaries/employers?incident_type=KOLIZJA", headers=admin)
    assert wrong_list.status_code == 400


async def test_changes_are_audited(client, auth_headers):
    admin = await auth_headers(RoleEnum.SUPER_ADMIN)
    entry = (await client.post("/api/dictionaries/employers", json={"name": "CEVA"}, headers=admin)).json()
    await client.patch(f"/api/dictionaries/employers/{entry['id']}", json={"sort_order": 5}, headers=admin)

    logs = (await client.get("/api/audit-logs?resource_type=employers", headers=admin)).json()["items"]
    assert [log["action"] for log in logs] == ["dictionary.updated", "dictionary.created"]
    assert logs[0]["payload"] == {"sort_order": 5}
