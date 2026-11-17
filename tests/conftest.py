import os

# Settings require DATABASE_URL at import time. The suite never touches it —
# every session is overridden below — but it must not point at a real database.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core import settings  # noqa: E402
from app.core.security.password import hash_password  # noqa: E402
from app.database.postgres import get_session  # noqa: E402
from app.enums.user import RoleEnum, UserStatus  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import AuditLog, RefreshToken, User  # noqa: E402

# Tables the suite needs, created on the in-memory sqlite engine. Order matters
# for foreign keys.
TEST_TABLES = [
    User.__table__,
    RefreshToken.__table__,
    AuditLog.__table__,
]

PASSWORD = "Warehouse-2026"


@pytest.fixture(autouse=True)
def _no_rate_limit():
    # Force it off whatever a developer's .env says: it would need Redis.
    original = settings.rate_limit.RATE_LIMIT_ENABLED
    settings.rate_limit.RATE_LIMIT_ENABLED = False
    yield
    settings.rate_limit.RATE_LIMIT_ENABLED = original


@pytest_asyncio.fixture
async def engine():
    # In-memory sqlite shared across the test via a single pooled connection.
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        for table in TEST_TABLES:
            await conn.run_sync(table.create)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def sessionmaker(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(sessionmaker) -> AsyncSession:
    async with sessionmaker() as s:
        yield s


@pytest_asyncio.fixture
async def app(sessionmaker):
    async def _override_session():
        async with sessionmaker() as s:
            yield s

    application = create_app()
    application.dependency_overrides[get_session] = _override_session
    return application


@pytest_asyncio.fixture
async def client(app) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def make_user(sessionmaker):
    """Insert a user straight into the database (there is no sign-up)."""

    async def _make(
        login: str,
        role: RoleEnum = RoleEnum.ADMIN,
        password: str = PASSWORD,
        status: UserStatus = UserStatus.ACTIVE,
        email: str | None = None,
        must_change_password: bool = False,
    ) -> User:
        async with sessionmaker() as s:
            user = User(
                login=login.lower(),
                email=email,
                hashed_password=hash_password(password),
                role=role.value,
                status=status.value,
                must_change_password=must_change_password,
            )
            s.add(user)
            await s.commit()
            await s.refresh(user)
            return user

    return _make


@pytest_asyncio.fixture
async def login(client):
    """Sign in and return the token pair."""

    async def _login(login: str, password: str = PASSWORD) -> dict:
        resp = await client.post("/api/auth/login", json={"login": login, "password": password})
        assert resp.status_code == 200, resp.text
        return resp.json()

    return _login


@pytest_asyncio.fixture
async def auth_headers(make_user, login):
    """Create a user of the given role and return Bearer headers for them."""

    async def _headers(role: RoleEnum = RoleEnum.ADMIN, name: str | None = None) -> dict:
        name = name or role.value.lower()
        await make_user(name, role)
        tokens = await login(name)
        return {"Authorization": f"Bearer {tokens['access_token']}"}

    return _headers
