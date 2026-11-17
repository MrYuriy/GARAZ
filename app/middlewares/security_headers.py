"""Baseline security response headers.

The cheap, high-value ones that apply everywhere and cannot break the API.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_HEADERS = {
    # Never let a browser second-guess a declared content type.
    "X-Content-Type-Options": "nosniff",
    # The app is never meant to be framed — blunts clickjacking.
    "X-Frame-Options": "DENY",
    # Don't leak the full URL (which can carry ids and QR tokens) to other origins.
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # The camera is the point of the app: operators scan QR codes and photograph
    # damage from the browser. So it is allowed — but only for our own origin.
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(self)",
    # Everything is HTTPS behind Cloudflare — pin browsers to it.
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for name, value in _HEADERS.items():
            response.headers.setdefault(name, value)
        return response
