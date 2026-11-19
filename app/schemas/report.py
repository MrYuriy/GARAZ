from datetime import date, datetime

from pydantic import BaseModel

from app.enums.incident import IncidentType
from app.enums.truck import TruckStatus
from app.schemas.common import RefOut
from app.schemas.permit import PermitOut


class ExpiringPermitsReport(BaseModel):
    """Active permits whose last day is at most `days` away (by `until`), soonest first."""

    days: int
    until: date
    items: list[PermitOut]


class TruckOfReport(BaseModel):
    id: int
    number: str
    status: TruckStatus
    truck_type: str


class _Counts(BaseModel):
    # Every type is present, with 0 where nothing happened.
    by_type: dict[IncidentType, int]
    total: int
    # How many of them stopped the truck ("wyłączony z eksploatacji": TAK).
    out_of_service: int
    last_at: datetime


class TruckIncidentsRow(_Counts):
    truck: TruckOfReport


class CategoryIncidentsRow(_Counts):
    category: RefOut


class _Period(BaseModel):
    # Local days, both included; empty means unbounded.
    date_from: date | None
    date_to: date | None


class IncidentsByTruckReport(_Period):
    """Most incidents first."""

    rows: list[TruckIncidentsRow]


class IncidentsByCategoryReport(_Period):
    """Most incidents first."""

    rows: list[CategoryIncidentsRow]
