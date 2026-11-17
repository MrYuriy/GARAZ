"""Redis-backed request quotas, used as FastAPI dependencies.

A fixed window per key: one INCR plus one EXPIRE. It can let through up to two
windows' worth at a boundary, which is fine for what it guards.

Redis being down must never lock anyone out, so failures are logged and allowed.
"""

import logging

from fastapi import Request

from app.core import settings
from app.core.exc import RateLimitedException
from app.core.redis_client import get_redis
from app.core.request_meta import client_ip

logger = logging.getLogger(__name__)


async def enforce(key: str, limit: int, window_seconds: int) -> None:
    if not settings.rate_limit.RATE_LIMIT_ENABLED:
        return
    try:
        count = await get_redis().incr(key)
        if count == 1:
            await get_redis().expire(key, window_seconds)
    except Exception:  # noqa: BLE001 — a Redis outage must not lock anyone out
        logger.exception("Rate limit check failed for %s, allowing the request", key)
        return
    if count > limit:
        raise RateLimitedException(window_seconds)


def _login_key(login: str) -> str:
    return f"ratelimit:login-account:{login.strip().lower()}"


async def login_locked(login: str) -> bool:
    """Whether one account has failed to sign in too often recently.

    Counts failures only, keyed by login, so a distributed guess at one account
    is caught while a user who signs in normally is never affected.
    """
    if not settings.rate_limit.RATE_LIMIT_ENABLED:
        return False
    try:
        count = await get_redis().get(_login_key(login))
    except Exception:  # noqa: BLE001
        logger.exception("Login-lock check failed for %s, allowing", login)
        return False
    return int(count or 0) >= settings.rate_limit.RATE_LIMIT_LOGIN_PER_ACCOUNT_ATTEMPTS


async def record_login_failure(login: str) -> None:
    if not settings.rate_limit.RATE_LIMIT_ENABLED:
        return
    try:
        count = await get_redis().incr(_login_key(login))
        if count == 1:
            await get_redis().expire(_login_key(login), settings.rate_limit.RATE_LIMIT_LOGIN_PER_ACCOUNT_WINDOW_SECONDS)
    except Exception:  # noqa: BLE001
        logger.exception("Recording a login failure failed for %s", login)


class RateLimiter:
    """Dependency that counts requests per client IP against one quota."""

    def __init__(self, name: str, limit: int, window_seconds: int) -> None:
        self.name = name
        self.limit = limit
        self.window_seconds = window_seconds

    async def __call__(self, request: Request) -> None:
        await enforce(f"ratelimit:{self.name}:{client_ip(request)}", self.limit, self.window_seconds)


auth_rate_limit = RateLimiter(
    "auth",
    settings.rate_limit.RATE_LIMIT_AUTH_ATTEMPTS,
    settings.rate_limit.RATE_LIMIT_AUTH_WINDOW_SECONDS,
)
