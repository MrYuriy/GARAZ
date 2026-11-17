"""One shared, lazily created async Redis client (its own connection pool)."""

import redis.asyncio as redis

from app.core import settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(
            settings.redis.url,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
    return _client
