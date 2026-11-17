from urllib.parse import urlsplit, urlunsplit

from pydantic import Field

from app.core.config.base import BaseConfig


class DbBaseConfig(BaseConfig):
    # Full connection string. Tests and CI point it at sqlite in memory.
    DATABASE_URL: str = Field(..., alias="DATABASE_URL")
    ECHO: bool = Field(False, alias="DB_ECHO")

    @property
    def url(self) -> str:
        """Async SQLAlchemy URL.

        Postgres URLs are switched to the asyncpg driver and stripped of
        libpq-only query params (sslmode and friends), which asyncpg does not
        accept in the URL. sqlite only gets the aiosqlite driver ensured.
        """
        raw = self.DATABASE_URL
        if raw.startswith(("postgres://", "postgresql://")):
            parts = urlsplit(raw)
            return urlunsplit(("postgresql+asyncpg", parts.netloc, parts.path, "", ""))
        if raw.startswith("sqlite://") and "+aiosqlite" not in raw:
            return raw.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return raw

    @property
    def connect_args(self) -> dict:
        # The compose Postgres has no TLS: opt out with the standard libpq flag
        # in DATABASE_URL ("...?sslmode=disable"). Anything else gets TLS.
        if not self.url.startswith("postgresql+asyncpg"):
            return {}
        if "sslmode=disable" in self.DATABASE_URL:
            return {}
        return {"ssl": True}
