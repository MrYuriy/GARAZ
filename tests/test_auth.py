from datetime import timedelta

from sqlalchemy import select

from app.core import settings
from app.enums.user import RoleEnum, UserStatus
from app.models import AuditLog, RefreshToken
from tests.conftest import PASSWORD


def _bearer(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_login_returns_tokens_that_resolve_to_the_user(client, make_user, login):
    await make_user("akowalska", RoleEnum.MANAGER, email="anna@garaz.pl")

    tokens = await login("akowalska")
    assert tokens["token_type"] == "bearer"

    me = await client.get("/api/auth/me", headers=_bearer(tokens))
    assert me.status_code == 200
    body = me.json()
    assert body["login"] == "akowalska"
    assert body["email"] == "anna@garaz.pl"
    assert body["role"] == "MANAGER"
    assert body["last_login_at"] is not None


async def test_login_is_case_insensitive_and_trimmed(make_user, login):
    await make_user("ola.nowak")
    assert (await login("  OLA.Nowak "))["access_token"]


async def test_email_is_not_a_login(client, make_user):
    await make_user("jan", email="jan@garaz.pl")
    resp = await client.post("/api/auth/login", json={"login": "jan@garaz.pl", "password": PASSWORD})
    assert resp.status_code == 401


async def test_wrong_password_and_unknown_login_look_the_same(client, make_user):
    await make_user("piotr")
    wrong = await client.post("/api/auth/login", json={"login": "piotr", "password": "nope-nope-1"})
    unknown = await client.post("/api/auth/login", json={"login": "ghost", "password": "nope-nope-1"})
    # Even a login that could never exist gets the same answer, not a 422.
    malformed = await client.post("/api/auth/login", json={"login": "no such!", "password": "nope-nope-1"})
    assert wrong.status_code == unknown.status_code == malformed.status_code == 401
    assert wrong.json() == unknown.json() == malformed.json()


async def test_disabled_account_cannot_sign_in(client, make_user):
    await make_user("gone", status=UserStatus.DISABLED)
    resp = await client.post("/api/auth/login", json={"login": "gone", "password": PASSWORD})
    assert resp.status_code == 401


async def test_login_is_audited(make_user, login, session):
    user = await make_user("audit")
    await login("audit")
    entries = (await session.execute(select(AuditLog).where(AuditLog.user_id == user.id))).scalars().all()
    assert [e.action for e in entries] == ["auth.login"]


async def test_me_requires_a_valid_token(client):
    assert (await client.get("/api/auth/me")).status_code == 401
    bad = await client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401


async def test_refresh_token_is_not_an_access_token(client, make_user, login):
    await make_user("mix")
    tokens = await login("mix")
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert resp.status_code == 401


async def test_refresh_rotates(client, make_user, login):
    await make_user("rot")
    first = await login("rot")

    resp = await client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert resp.status_code == 200
    second = resp.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert (await client.get("/api/auth/me", headers=_bearer(second))).status_code == 200


async def test_concurrent_refresh_inside_grace_window_is_allowed(client, make_user, login):
    await make_user("tabs")
    tokens = await login("tabs")

    # Two tabs refreshing with the same token at the same moment.
    a = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    b = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert a.status_code == b.status_code == 200


async def test_replay_after_grace_window_ends_every_session(client, make_user, login, session, monkeypatch):
    user = await make_user("thief")
    tokens = await login("thief")
    rotated = (await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})).json()

    monkeypatch.setattr(settings.auth, "REFRESH_REUSE_GRACE_SECONDS", -1)
    replay = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401

    # The legitimate, newer token is dead too: which copy is the thief's is unknowable.
    after = await client.post("/api/auth/refresh", json={"refresh_token": rotated["refresh_token"]})
    assert after.status_code == 401

    actions = (await session.execute(select(AuditLog.action).where(AuditLog.user_id == user.id))).scalars().all()
    assert "auth.token_reuse" in actions


async def test_logout_retires_the_token_at_once(client, make_user, login):
    await make_user("out")
    tokens = await login("out")

    assert (await client.post("/api/auth/logout", json={"refresh_token": tokens["refresh_token"]})).status_code == 204
    again = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert again.status_code == 401


async def test_logout_all_retires_every_session(client, make_user, login, session):
    user = await make_user("lost-phone")
    phone = await login("lost-phone")
    laptop = await login("lost-phone")

    assert (await client.post("/api/auth/logout-all", headers=_bearer(laptop))).status_code == 204
    for tokens in (phone, laptop):
        resp = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert resp.status_code == 401

    live = await session.execute(
        select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
    )
    assert live.scalars().all() == []


async def test_expired_refresh_token_is_refused(client, make_user, login, sessionmaker):
    await make_user("old")
    tokens = await login("old")
    async with sessionmaker() as s:
        for row in (await s.execute(select(RefreshToken))).scalars():
            row.expires_at = row.expires_at - timedelta(days=365)
        await s.commit()

    resp = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 401


async def test_change_password_signs_out_other_sessions(client, make_user, login):
    await make_user("pw")
    other = await login("pw")
    this = await login("pw")

    resp = await client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "Forklift-Blue-77"},
        headers=_bearer(this),
    )
    assert resp.status_code == 200
    fresh = resp.json()

    assert (await client.post("/api/auth/refresh", json={"refresh_token": other["refresh_token"]})).status_code == 401
    assert (await client.post("/api/auth/refresh", json={"refresh_token": fresh["refresh_token"]})).status_code == 200
    assert (await login("pw", "Forklift-Blue-77"))["access_token"]


async def test_change_password_checks_the_current_one(client, make_user, login):
    await make_user("pw2")
    tokens = await login("pw2")
    resp = await client.post(
        "/api/auth/change-password",
        json={"current_password": "wrong-password-1", "new_password": "Forklift-Blue-77"},
        headers=_bearer(tokens),
    )
    assert resp.status_code == 401


async def test_any_non_empty_password_is_accepted(client, make_user, login):
    # No strength rules: short or simple is the user's call.
    await make_user("pw3")
    tokens = await login("pw3")
    resp = await client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "1"},
        headers=_bearer(tokens),
    )
    assert resp.status_code == 200
    assert (await login("pw3", "1"))["access_token"]
    empty = await client.post(
        "/api/auth/change-password",
        json={"current_password": "1", "new_password": ""},
        headers=_bearer(resp.json()),
    )
    assert empty.status_code == 422


async def test_a_long_passphrase_works(make_user, login):
    # bcrypt reads 72 bytes; longer must not crash, and must still match.
    long = "ł" * 100
    await make_user("pw4", password=long)
    assert (await login("pw4", long))["access_token"]
