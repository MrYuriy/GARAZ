# Async SQLAlchemy engine + session factory.
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import settings

engine = create_async_engine(
    settings.db.url,
    echo=settings.db.ECHO,
    connect_args=settings.db.connect_args,
    # Verify liveness before use and recycle before a connection goes stale.
    pool_pre_ping=True,
    pool_recycle=300,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    # Whatever a request did not commit is rolled back when the session closes:
    # services commit once, at the end of a unit of work.
    async with async_session() as session:
        yield session
