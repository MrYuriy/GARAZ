import pytest
from sqlalchemy import select

from app.core import settings
from app.enums.user import RoleEnum
from app.models import User
from scripts.bootstrap_admin import ensure_admin


@pytest.fixture
def bootstrap_env(monkeypatch):
    monkeypatch.setattr(settings.auth, "ADMIN_BOOTSTRAP_LOGIN", "Root")
    monkeypatch.setattr(settings.auth, "ADMIN_BOOTSTRAP_PASSWORD", "Bootstrap-Pass-1")


async def test_does_nothing_when_not_configured(sessionmaker, monkeypatch):
    # Explicit, so a developer's own .env cannot configure it behind the test.
    monkeypatch.setattr(settings.auth, "ADMIN_BOOTSTRAP_PASSWORD", "")
    assert await ensure_admin(sessionmaker) == "not configured"


async def test_creates_the_first_super_admin(bootstrap_env, sessionmaker, login):
    assert await ensure_admin(sessionmaker) == "created root as SUPER_ADMIN"
    assert (await login("root", "Bootstrap-Pass-1"))["access_token"]


async def test_is_a_no_op_once_one_exists(bootstrap_env, sessionmaker):
    await ensure_admin(sessionmaker)
    assert await ensure_admin(sessionmaker) == "a SUPER_ADMIN already exists"
    async with sessionmaker() as s:
        assert len((await s.execute(select(User))).scalars().all()) == 1


async def test_promotes_an_existing_account(bootstrap_env, sessionmaker, make_user):
    await make_user("root", RoleEnum.MANAGER)
    assert await ensure_admin(sessionmaker) == "promoted root to SUPER_ADMIN"
    async with sessionmaker() as s:
        user = (await s.execute(select(User))).scalar_one()
        assert user.role == "SUPER_ADMIN"
