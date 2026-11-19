from datetime import datetime

from sqlalchemy import case, func, select

from app.models import Incident, Truck
from app.models.dictionary import IncidentCategory, TruckType


class ReportRepository:
    """Counts across incidents; the lists themselves come from the other repositories."""

    def __init__(self, session) -> None:
        self.session = session

    @staticmethod
    def _period(since: datetime | None, until: datetime | None) -> list:
        conditions = []
        if since:
            conditions.append(Incident.occurred_at >= since)
        if until:
            conditions.append(Incident.occurred_at < until)
        return conditions

    @staticmethod
    def _measures() -> tuple:
        stopped = func.sum(case((Incident.out_of_service.is_(True), 1), else_=0))
        return (
            func.count(Incident.id).label("count"),
            stopped.label("out_of_service"),
            func.max(Incident.occurred_at).label("last_at"),
        )

    async def by_truck(self, since: datetime | None, until: datetime | None) -> list:
        """One row per truck and incident type: count, how many stopped it, the latest."""
        stmt = (
            select(
                Truck.id,
                Truck.number,
                Truck.status,
                TruckType.name.label("truck_type"),
                Incident.incident_type,
                *self._measures(),
            )
            .select_from(Incident)
            .join(Truck, Incident.truck_id == Truck.id)
            .join(TruckType, Truck.truck_type_id == TruckType.id)
            .where(*self._period(since, until))
            .group_by(Truck.id, Truck.number, Truck.status, TruckType.name, Incident.incident_type)
        )
        return list((await self.session.execute(stmt)).all())

    async def by_category(self, since: datetime | None, until: datetime | None) -> list:
        """One row per category and incident type."""
        stmt = (
            select(IncidentCategory.id, IncidentCategory.name, Incident.incident_type, *self._measures())
            .select_from(Incident)
            .join(IncidentCategory, Incident.category_id == IncidentCategory.id)
            .where(*self._period(since, until))
            .group_by(IncidentCategory.id, IncidentCategory.name, Incident.incident_type)
        )
        return list((await self.session.execute(stmt)).all())
