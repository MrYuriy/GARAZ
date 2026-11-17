# Request quotas. Backed by Redis so limits hold across worker processes.
from app.core.config.base import BaseConfig


class RateLimitConfig(BaseConfig):
    # Off by default so tests and local runs need no Redis; on in deployments.
    RATE_LIMIT_ENABLED: bool = False

    # Sign-in and token refresh, keyed by client IP.
    RATE_LIMIT_AUTH_ATTEMPTS: int = 10
    RATE_LIMIT_AUTH_WINDOW_SECONDS: int = 300

    # Failed logins keyed by the login being tried, not the IP: catches a
    # distributed guess at one account. Higher, because a whole warehouse can
    # sit behind one NAT.
    RATE_LIMIT_LOGIN_PER_ACCOUNT_ATTEMPTS: int = 20
    RATE_LIMIT_LOGIN_PER_ACCOUNT_WINDOW_SECONDS: int = 900
