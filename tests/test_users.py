from sqlalchemy import select

from app.enums.user import RoleEnum
from app.models import AuditLog

NEW_PASSWORD = "Pallet-Jack-42"


def _new(login: str, role: str, **extra) -> dict:
    return {"login": login, "password": NEW_PASSWORD, "full_name": "Jan Kowalski", "role": role, **extra}


async def test_super_admin_creates_an_admin(client, auth_headers, login):
    headers = await auth_headers(RoleEnum.SUPER_ADMIN)
    resp = await client.post("/api/users", json=_new("Admin2", "ADMIN"), headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["login"] == "admin2"
    assert body["email"] is None
    assert body["role"] == "ADMIN"
    assert body["status"] == "ACTIVE"
    assert "hashed_password" not in body

    assert (await login("admin2", NEW_PASSWORD))["access_token"]


async def test_admin_creates_a_manager_but_not_an_admin(client, auth_headers):
    headers = await auth_headers(RoleEnum.ADMIN)
    ok = await client.post("/api/users", json=_new("kier", "MANAGER"), headers=headers)
    assert ok.status_code == 201

    denied = await client.post("/api/users", json=_new("boss", "ADMIN"), headers=headers)
    assert denied.status_code == 403


async def test_manager_has_no_access_to_user_management(client, auth_headers):
    headers = await auth_headers(RoleEnum.MANAGER)
    assert (await client.get("/api/users", headers=headers)).status_code == 403
    assert (await client.post("/api/users", json=_new("x", "MANAGER"), headers=headers)).status_code == 403


async def test_duplicate_login_is_a_conflict(client, auth_headers):
    headers = await auth_headers(RoleEnum.SUPER_ADMIN)
    await client.post("/api/users", json=_new("dup", "MANAGER"), headers=headers)
    again = await client.post("/api/users", json=_new("DUP", "MANAGER"), headers=headers)
    assert again.status_code == 409


async def test_two_accounts_may_share_a_notification_email(client, auth_headers):
    # e.g. a shared shift-leader mailbox
    headers = await auth_headers(RoleEnum.SUPER_ADMIN)
    shared = "zmiana@garaz.pl"
    first = await client.post("/api/users", json=_new("lider1", "MANAGER", email=shared), headers=headers)
    second = await client.post("/api/users", json=_new("lider2", "MANAGER", email=shared), headers=headers)
    assert first.status_code == second.status_code == 201


async def test_login_format_is_checked_on_create(client, auth_headers):
    headers = await auth_headers(RoleEnum.SUPER_ADMIN)
    for bad in ("a", "jan kowalski", "jan@garaz.pl", "-jan", "x" * 65):
        resp = await client.post("/api/users", json=_new(bad, "MANAGER"), headers=headers)
        assert resp.status_code == 422, bad


async def test_bad_email_is_rejected_and_blank_means_none(client, auth_headers):
    headers = await auth_headers(RoleEnum.SUPER_ADMIN)
    bad = await client.post("/api/users", json=_new("e1", "MANAGER", email="not-an-email"), headers=headers)
    assert bad.status_code == 422
    blank = await client.post("/api/users", json=_new("e2", "MANAGER", email=""), headers=headers)
    assert blank.status_code == 201
    assert blank.json()["email"] is None


async def test_email_can_be_set_changed_and_cleared(client, auth_headers, make_user):
    headers = await auth_headers(RoleEnum.ADMIN)
    manager = await make_user("mail", RoleEnum.MANAGER)
    url = f"/api/users/{manager.id}"

    assert (await client.patch(url, json={"email": "a@garaz.pl"}, headers=headers)).json()["email"] == "a@garaz.pl"
    # Not sending it leaves it alone...
    assert (await client.patch(url, json={"full_name": "X"}, headers=headers)).json()["email"] == "a@garaz.pl"
    # ...sending null clears it.
    assert (await client.patch(url, json={"email": None}, headers=headers)).json()["email"] is None


async def test_login_can_be_renamed_but_not_onto_another(client, auth_headers, make_user, login):
    headers = await auth_headers(RoleEnum.ADMIN)
    manager = await make_user("old.name", RoleEnum.MANAGER)
    await make_user("taken", RoleEnum.MANAGER)

    clash = await client.patch(f"/api/users/{manager.id}", json={"login": "Taken"}, headers=headers)
    assert clash.status_code == 409
    renamed = await client.patch(f"/api/users/{manager.id}", json={"login": "New.Name"}, headers=headers)
    assert renamed.json()["login"] == "new.name"
    assert (await login("new.name"))["access_token"]


async def test_list_filters_and_searches(client, auth_headers, make_user):
    headers = await auth_headers(RoleEnum.SUPER_ADMIN)
    await make_user("m1", RoleEnum.MANAGER)
    await make_user("m2", RoleEnum.MANAGER, email="kierownik@garaz.pl")

    managers = (await client.get("/api/users", params={"role": "MANAGER"}, headers=headers)).json()
    assert managers["total"] == 2
    by_login = (await client.get("/api/users", params={"query": "m1"}, headers=headers)).json()
    assert [u["login"] for u in by_login["items"]] == ["m1"]
    by_email = (await client.get("/api/users", params={"query": "kierownik"}, headers=headers)).json()
    assert [u["login"] for u in by_email["items"]] == ["m2"]


async def test_disabling_signs_the_user_out(client, auth_headers, make_user, login):
    headers = await auth_headers(RoleEnum.ADMIN)
    manager = await make_user("leaving", RoleEnum.MANAGER)
    tokens = await login("leaving")

    resp = await client.patch(f"/api/users/{manager.id}", json={"status": "DISABLED"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "DISABLED"

    # The access token stops working at once, not when it expires...
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 401
    # ...and the session cannot be renewed.
    refresh = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh.status_code == 401


async def test_admin_resets_a_managers_password(client, auth_headers, make_user, login):
    headers = await auth_headers(RoleEnum.ADMIN)
    manager = await make_user("forgot", RoleEnum.MANAGER)

    resp = await client.patch(f"/api/users/{manager.id}", json={"password": NEW_PASSWORD}, headers=headers)
    assert resp.status_code == 200
    assert (await login("forgot", NEW_PASSWORD))["access_token"]


async def test_admin_cannot_touch_another_admin_or_promote(client, auth_headers, make_user):
    headers = await auth_headers(RoleEnum.ADMIN)
    other_admin = await make_user("peer", RoleEnum.ADMIN)
    manager = await make_user("m", RoleEnum.MANAGER)

    edit_peer = await client.patch(f"/api/users/{other_admin.id}", json={"status": "DISABLED"}, headers=headers)
    assert edit_peer.status_code == 403
    promote = await client.patch(f"/api/users/{manager.id}", json={"role": "ADMIN"}, headers=headers)
    assert promote.status_code == 403


async def test_nobody_edits_themselves_here(client, make_user, login):
    me = await make_user("root", RoleEnum.SUPER_ADMIN)
    tokens = await login("root")
    resp = await client.patch(
        f"/api/users/{me.id}",
        json={"status": "DISABLED"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 400


async def test_unknown_user_is_404(client, auth_headers):
    headers = await auth_headers(RoleEnum.SUPER_ADMIN)
    assert (await client.get("/api/users/9999", headers=headers)).status_code == 404


async def test_changes_are_audited_without_the_password(client, auth_headers, make_user, session):
    headers = await auth_headers(RoleEnum.SUPER_ADMIN)
    target = await make_user("aud", RoleEnum.MANAGER)

    await client.patch(
        f"/api/users/{target.id}",
        json={"full_name": "Ewa Nowak", "password": NEW_PASSWORD},
        headers=headers,
    )
    entry = (
        await session.execute(
            select(AuditLog).where(AuditLog.action == "user.updated", AuditLog.resource_id == str(target.id))
        )
    ).scalar_one()
    assert entry.payload == {"full_name": "Ewa Nowak", "password": "reset"}
    assert NEW_PASSWORD not in str(entry.payload)


async def test_audit_log_is_readable_by_admins_only(client, auth_headers):
    admin = await auth_headers(RoleEnum.ADMIN)
    manager = await auth_headers(RoleEnum.MANAGER)

    resp = await client.get("/api/audit-logs", params={"action": "auth.login"}, headers=admin)
    assert resp.status_code == 200
    assert resp.json()["total"] == 2  # both sign-ins above
    assert (await client.get("/api/audit-logs", headers=manager)).status_code == 403
