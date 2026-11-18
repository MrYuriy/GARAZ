"""The daily "Wygasłe" pass: active permits past their last day become expired.

It runs inside the API process — once at start-up, then every day shortly
after local midnight — so no separate scheduler container is needed. It is
idempotent: running it twice, or in two processes at once, expires nothing
twice (the second pass finds nothing ACTIVE past its date).
"""

import asyncio
import logging
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import settings
from app.core.time import local_today, local_zone, utcnow
from app.enums.audit import AuditAction
from app.enums.permit import PermitStatus
from app.repositories.permit import PermitRepository
from app.services.audit import AuditService

log = logging.getLogger(__name__)


async def expire_due_permits(session: AsyncSession, today: date | None = None) -> int:
    """Mark every active permit whose valid-until day has passed. Returns how many."""
    today = today or local_today()
    permits = PermitRepository(session)
    audit = AuditService(session)
    due = await permits.due_to_expire(today)
    for permit in due:
        permit.status = PermitStatus.EXPIRED.value
        await audit.record(
            AuditAction.PERMIT_EXPIRED,
            resource_type="permit",
            resource_id=permit.id,
            payload={"number": permit.number, "valid_until": permit.valid_until.isoformat()},
        )
    if due:
        await session.commit()
    return len(due)


def seconds_until_next_run(now: datetime | None = None) -> float:
    """Seconds from `now` to the next configured local time (default 00:05)."""
    local_now = (now or utcnow()).astimezone(local_zone())
    run = local_now.replace(
        hour=settings.permits.PERMIT_EXPIRY_HOUR,
        minute=settings.permits.PERMIT_EXPIRY_MINUTE,
        second=0,
        microsecond=0,
    )
    if run <= local_now:
        run = (run + timedelta(days=1)).replace(
            hour=settings.permits.PERMIT_EXPIRY_HOUR, minute=settings.permits.PERMIT_EXPIRY_MINUTE
        )
    return (run - local_now).total_seconds()


async def run_forever(sessionmaker: async_sessionmaker) -> None:
    """Run now, then daily. A failed pass is logged and retried at the next one."""
    while True:
        try:
            async with sessionmaker() as session:
                count = await expire_due_permits(session)
            if count:
                log.info("Permit expiry: %d permit(s) marked EXPIRED", count)
        except Exception:
            log.exception("Permit expiry pass failed")
        await asyncio.sleep(seconds_until_next_run())
