from datetime import date

from sqlalchemy import func, or_, select

from app.enums.permit import PermitStatus
from app.models import Operator, Permit, permit_truck_types
from app.repositories.base import BaseRepository


class PermitRepository(BaseRepository[Permit]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=Permit)

    async def get_by_id(self, permit_id: int, fresh: bool = False) -> Permit | None:
        stmt = select(Permit).where(Permit.id == permit_id)
        if fresh:
            stmt = stmt.execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).unique().scalar_one_or_none()

    async def get_by_number(self, number: str) -> Permit | None:
        """Case-insensitive, like truck numbers."""
        stmt = select(Permit).where(func.lower(Permit.number) == number.lower())
        return (await self.session.execute(stmt)).unique().scalar_one_or_none()

    async def search(
        self,
        page: int = 1,
        limit: int = 50,
        query: str | None = None,
        status: str | None = None,
        operator_id: int | None = None,
        category_id: int | None = None,
        truck_type_id: int | None = None,
        valid_until_before: date | None = None,
    ) -> tuple[list[Permit], int]:
        """Soonest to expire first; `query` matches the permit number or the operator's name."""
        conditions = []
        if query:
            like = f"%{query}%"
            conditions.append(or_(Permit.number.ilike(like), Operator.full_name.ilike(like)))
        if status:
            conditions.append(Permit.status == status)
        if operator_id:
            conditions.append(Permit.operator_id == operator_id)
        if category_id:
            conditions.append(Permit.category_id == category_id)
        if truck_type_id:
            covered = select(permit_truck_types.c.permit_id).where(permit_truck_types.c.truck_type_id == truck_type_id)
            conditions.append(Permit.id.in_(covered))
        if valid_until_before:
            conditions.append(Permit.valid_until <= valid_until_before)

        # An explicit join, so `query` can reach the name; the eager join for
        # the response is separate and stays out of the count.
        base = select(Permit).join(Operator, Permit.operator_id == Operator.id).where(*conditions)
        stmt = base.order_by(Permit.valid_until, Permit.number).offset((page - 1) * limit).limit(limit)
        rows = (await self.session.execute(stmt)).unique().scalars().all()
        count = select(func.count(Permit.id)).join(Operator, Permit.operator_id == Operator.id).where(*conditions)
        total = (await self.session.execute(count)).scalar() or 0
        return list(rows), total

    async def due_to_expire(self, today: date) -> list[Permit]:
        """Active permits whose last valid day has passed."""
        stmt = select(Permit).where(Permit.status == PermitStatus.ACTIVE.value, Permit.valid_until < today)
        return list((await self.session.execute(stmt)).unique().scalars().all())
