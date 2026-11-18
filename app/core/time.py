"""The one clock the application reads.

Every timestamp is timezone-aware UTC. Naive datetimes are refused at the
database boundary (see `models.base.UTCDateTime`), so "what zone was this in?"
never has to be guessed later — which matters here, because the time of a
reported incident is evidence.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    return datetime.now(UTC)


def local_zone() -> ZoneInfo:
    """The warehouse's zone (settings.app.TIMEZONE)."""
    from app.core import settings

    return ZoneInfo(settings.app.TIMEZONE)


def local_today() -> date:
    """Today on the warehouse floor. A permit "valid until 31.03" is valid all
    of that day in Poland, whatever the UTC date is at 00:30."""
    return utcnow().astimezone(local_zone()).date()
