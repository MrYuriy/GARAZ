from sqlalchemy import select

from app.models import AuditLog


async def test_a_signed_out_device_retrying_does_not_end_the_kept_session(client, make_user, login, session):
    """After "sign out everywhere" the other devices still hold their tokens
    and will try them. That is not theft and must not end the session the
    user just kept."""
    user = await make_user("kept")
    other = await login("kept")
    this = await login("kept")

    await client.post("/api/auth/logout-all", headers={"Authorization": f"Bearer {this['access_token']}"})
    fresh = await login("kept")

    stale = await client.post("/api/auth/refresh", json={"refresh_token": other["refresh_token"]})
    assert stale.status_code == 401
    kept = await client.post("/api/auth/refresh", json={"refresh_token": fresh["refresh_token"]})
    assert kept.status_code == 200

    actions = (await session.execute(select(AuditLog.action).where(AuditLog.user_id == user.id))).scalars().all()
    assert "auth.token_reuse" not in actions
