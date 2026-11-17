"""An administrator hands out a starting password; the user replaces it on first sign-in."""

from app.enums.user import RoleEnum
from tests.conftest import PASSWORD


def _bearer(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_new_accounts_must_change_their_password_by_default(client, auth_headers, login):
    headers = await auth_headers(RoleEnum.SUPER_ADMIN)
    resp = await client.post(
        "/api/users", json={"login": "nowy", "password": "start", "role": "MANAGER"}, headers=headers
    )
    assert resp.status_code == 201
    assert resp.json()["must_change_password"] is True

    me = await client.get("/api/auth/me", headers=_bearer(await login("nowy", "start")))
    assert me.json()["must_change_password"] is True


async def test_the_flag_can_be_left_off_on_create(client, auth_headers):
    headers = await auth_headers(RoleEnum.SUPER_ADMIN)
    resp = await client.post(
        "/api/users",
        json={"login": "gotowy", "password": "x", "role": "MANAGER", "must_change_password": False},
        headers=headers,
    )
    assert resp.json()["must_change_password"] is False


async def test_until_changed_only_me_and_change_password_answer(client, make_user, login):
    await make_user("flag1", RoleEnum.ADMIN, must_change_password=True)
    tokens = await login("flag1")

    assert (await client.get("/api/auth/me", headers=_bearer(tokens))).status_code == 200
    blocked = await client.get("/api/users", headers=_bearer(tokens))
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Password change required"


async def test_forced_change_needs_no_current_password_and_clears_the_flag(client, make_user, login):
    await make_user("flag2", RoleEnum.ADMIN, must_change_password=True)
    tokens = await login("flag2")

    resp = await client.post("/api/auth/change-password", json={"new_password": "moje"}, headers=_bearer(tokens))
    assert resp.status_code == 200
    fresh = _bearer(resp.json())
    assert (await client.get("/api/auth/me", headers=fresh)).json()["must_change_password"] is False
    assert (await client.get("/api/users", headers=fresh)).status_code == 200
    assert (await login("flag2", "moje"))["access_token"]


async def test_forced_change_must_actually_change_it(client, make_user, login):
    await make_user("flag3", must_change_password=True)
    tokens = await login("flag3")
    resp = await client.post("/api/auth/change-password", json={"new_password": PASSWORD}, headers=_bearer(tokens))
    assert resp.status_code == 400


async def test_normal_change_still_needs_the_current_password(client, make_user, login):
    await make_user("flag4")
    tokens = await login("flag4")
    resp = await client.post("/api/auth/change-password", json={"new_password": "inne"}, headers=_bearer(tokens))
    assert resp.status_code == 401


async def test_admin_can_set_the_flag_again(client, auth_headers, make_user, login):
    headers = await auth_headers(RoleEnum.ADMIN)
    target = await make_user("flag5", RoleEnum.MANAGER)

    resp = await client.patch(
        f"/api/users/{target.id}", json={"password": "tymczasowe", "must_change_password": True}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is True
    me = await client.get("/api/auth/me", headers=_bearer(await login("flag5", "tymczasowe")))
    assert me.json()["must_change_password"] is True

    cleared = await client.patch(f"/api/users/{target.id}", json={"must_change_password": False}, headers=headers)
    assert cleared.json()["must_change_password"] is False
