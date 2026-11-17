from app.core.config.app import AppBaseConfig
from app.core.config.auth import AuthConfig
from app.core.config.base import BaseConfig
from app.core.config.db import DbBaseConfig
from app.core.config.jwt import JwtConfig
from app.core.config.rate_limit import RateLimitConfig
from app.core.config.redis import RedisConfig

__all__ = ["Settings", "settings"]


class Settings(BaseConfig):
    """Central settings aggregator: one sub-config per concern."""

    app: AppBaseConfig = AppBaseConfig()
    db: DbBaseConfig = DbBaseConfig()
    jwt: JwtConfig = JwtConfig()
    auth: AuthConfig = AuthConfig()
    rate_limit: RateLimitConfig = RateLimitConfig()
    redis: RedisConfig = RedisConfig()


settings = Settings()
