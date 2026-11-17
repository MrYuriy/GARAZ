# SQLAlchemy declarative base, cross-dialect column types and mixins.
#
# Every model must work on Postgres (production) and on sqlite (the test
# suite), so the types below pick a native implementation per dialect.
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import TypeDecorator

from app.core.time import utcnow

Base = declarative_base()

# Native UUID on Postgres, portable variant on sqlite. The Postgres
# gen_random_uuid() default is set in migrations; the ORM always sets one
# client-side too.
UUIDType = PGUUID(as_uuid=True).with_variant(Uuid(), "sqlite")

# JSONB on Postgres, generic JSON on sqlite.
JSONType = JSONB().with_variant(JSON(), "sqlite")


class UTCDateTime(TypeDecorator):
    """A timestamp that is always timezone-aware UTC in Python.

    `timestamptz` on Postgres. sqlite has no zones, so there it is stored as
    naive UTC and the zone is put back on load — otherwise the test suite
    would compare aware and naive datetimes and fail where production would
    not. Naive values are refused outright: a time without a zone is a bug
    waiting to be misread, and the time of an incident is evidence.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime given to a UTCDateTime column; use app.core.time.utcnow()")
        value = value.astimezone(UTC)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class UUIDMixin:
    uuid = Column(UUIDType, primary_key=True, default=uuid4)


class TimestampMixin:
    created_at = Column(UTCDateTime, default=utcnow, server_default=func.now(), nullable=False, index=True)
    updated_at = Column(UTCDateTime, default=utcnow, server_default=func.now(), onupdate=utcnow, nullable=False)
