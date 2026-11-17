from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.security.password import hash_password
from app.core.time import utcnow
from app.models import User


async def test_timestamps_come_back_aware_utc_on_sqlite(session):
    user = User(login="t", hashed_password=hash_password("x"), role="ADMIN")
    session.add(user)
    await session.commit()

    loaded = (await session.execute(select(User).where(User.id == user.id))).scalar_one()
    assert loaded.created_at.tzinfo is not None
    assert loaded.created_at.utcoffset() == timedelta(0)


async def test_other_zones_are_stored_as_the_same_instant(session):
    warsaw_summer = timezone(timedelta(hours=2))
    moment = datetime(2026, 7, 1, 14, 5, tzinfo=warsaw_summer)
    user = User(login="z", hashed_password="x", role="ADMIN", last_login_at=moment)
    session.add(user)
    await session.commit()
    session.expunge_all()

    loaded = (await session.execute(select(User).where(User.login == "z"))).scalar_one()
    assert loaded.last_login_at == moment
    assert loaded.last_login_at.hour == 12  # 14:05 in Warsaw is 12:05 UTC


async def test_naive_datetimes_are_refused(session):
    user = User(login="n", hashed_password="x", role="ADMIN", last_login_at=datetime(2026, 1, 1))
    session.add(user)
    with pytest.raises(Exception, match="Naive datetime"):
        await session.commit()


def test_utcnow_is_aware():
    assert utcnow().utcoffset() == timedelta(0)
