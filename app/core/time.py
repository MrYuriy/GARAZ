"""The one clock the application reads.

Every timestamp is timezone-aware UTC. Naive datetimes are refused at the
database boundary (see `models.base.UTCDateTime`), so "what zone was this in?"
never has to be guessed later — which matters here, because the time of a
reported incident is evidence.
"""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)
