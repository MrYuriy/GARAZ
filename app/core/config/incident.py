# Incident reports sent by operators from their phones.
from app.core.config.base import BaseConfig


class IncidentConfig(BaseConfig):
    # At least one photo per report; this cap only stops a runaway client.
    MAX_PHOTOS: int = 30
    # One photo as sent. The phone compresses first; this is the upper bound.
    MAX_PHOTO_MB: int = 15
    # Stored photos are re-encoded to JPEG no larger than this (longest side),
    # which also drops EXIF (GPS position included).
    PHOTO_MAX_SIDE: int = 2048
    THUMB_SIDE: int = 320
    # An offline phone may send a report later; its own time is trusted up to
    # this many days back, otherwise the arrival time is used.
    MAX_REPORT_DELAY_DAYS: int = 7
    # The public, sign-in-free endpoints, per client IP. A warehouse may share one NAT.
    RATE_LIMIT_PUBLIC_ATTEMPTS: int = 120
    RATE_LIMIT_PUBLIC_WINDOW_SECONDS: int = 300
