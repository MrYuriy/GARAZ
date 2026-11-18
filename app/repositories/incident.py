from datetime import datetime
from uuid import UUID

from sqlalchemy import Text, cast, func, or_, select

from app.models import Incident, Operator, Truck
from app.repositories.base import BaseRepository


class IncidentRepository(BaseRepository[Incident]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=Incident)

    async def get_by_id(self, incident_id: int, fresh: bool = False) -> Incident | None:
        stmt = select(Incident).where(Incident.id == incident_id)
        if fresh:
            stmt = stmt.execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).unique().scalar_one_or_none()

    async def get_by_client_uuid(self, client_uuid: UUID) -> Incident | None:
        stmt = select(Incident).where(Incident.client_uuid == client_uuid)
        return (await self.session.execute(stmt)).unique().scalar_one_or_none()

    async def last_mth(self, truck_id: int) -> float | None:
        """The hour meter of this truck's latest report that gave one."""
        stmt = (
            select(Incident.mth)
            .where(Incident.truck_id == truck_id, Incident.mth.is_not(None))
            .order_by(Incident.occurred_at.desc(), Incident.id.desc())
            .limit(1)
        )
        value = (await self.session.execute(stmt)).scalar_one_or_none()
        return float(value) if value is not None else None

    async def search(
        self,
        page: int = 1,
        limit: int = 50,
        query: str | None = None,
        status: str | None = None,
        incident_type: str | None = None,
        truck_id: int | None = None,
        operator_id: int | None = None,
        category_id: int | None = None,
        flagged: bool | None = None,
        open_only: bool = False,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[list[Incident], int]:
        """Newest first. `query` matches the truck number or the operator's name."""
        conditions = []
        if query:
            like = f"%{query}%"
            conditions.append(
                or_(
                    Incident.truck_id.in_(select(Truck.id).where(Truck.number.ilike(like))),
                    Incident.operator_id.in_(select(Operator.id).where(Operator.full_name.ilike(like))),
                )
            )
        for column, value in (
            (Incident.status, status),
            (Incident.incident_type, incident_type),
            (Incident.truck_id, truck_id),
            (Incident.operator_id, operator_id),
            (Incident.category_id, category_id),
        ):
            if value is not None:
                conditions.append(column == value)
        if flagged is not None:
            # flags is a JSON list; an empty one serialises as "[]" in both dialects.
            empty = cast(Incident.flags, Text) == "[]"
            conditions.append(~empty if flagged else empty)
        if open_only:
            conditions.append(Incident.status != "CLOSED")
        if since:
            conditions.append(Incident.occurred_at >= since)
        if until:
            conditions.append(Incident.occurred_at < until)

        stmt = (
            select(Incident)
            .where(*conditions)
            .order_by(Incident.occurred_at.desc(), Incident.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).unique().scalars().all()
        total = (
            await self.session.execute(select(func.count()).select_from(Incident).where(*conditions))
        ).scalar() or 0
        return list(rows), total
