import secrets

from app.core import settings


def new_qr_token() -> str:
    """A random token for a printed QR code: nothing about the truck or person
    can be read from it, and it cannot be guessed (~190 bits)."""
    return secrets.token_urlsafe(24)


def truck_qr_url(token: str) -> str:
    """What a truck's QR encodes. A plain https link, so any phone camera opens
    it — the installed app through App Links, the web app otherwise."""
    return f"{settings.app.BASE_URL.rstrip('/')}/t/{token}"
