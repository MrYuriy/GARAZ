"""Who is on the other end of a request, as far as the audit log cares."""

from dataclasses import dataclass

from fastapi import Request


def client_ip(request: Request) -> str:
    """Caller's real address, from the proxy we sit behind.

    CF-Connecting-IP is Cloudflare's single, un-spoofable client address; it is
    preferred over X-Forwarded-For, which is a chain a caller can prepend to.
    """
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@dataclass(frozen=True)
class RequestMeta:
    ip_address: str | None = None
    user_agent: str | None = None


def get_request_meta(request: Request) -> RequestMeta:
    agent = request.headers.get("user-agent")
    return RequestMeta(ip_address=client_ip(request), user_agent=agent[:512] if agent else None)
