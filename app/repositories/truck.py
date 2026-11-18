from sqlalchemy import func, or_, select

from app.models import Truck, TruckManufacturer, TruckModel
from app.repositories.base import BaseRepository


class TruckRepository(BaseRepository[Truck]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=Truck)

    async def get_by_id(self, truck_id: int, fresh: bool = False) -> Truck | None:
        """`fresh` reloads it, site and type included, after a commit changed them."""
        stmt = select(Truck).where(Truck.id == truck_id)
        if fresh:
            stmt = stmt.execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).unique().scalar_one_or_none()

    async def get_by_number(self, number: str) -> Truck | None:
        """Case-insensitive: "w-12" and "W-12" are the same painted number."""
        stmt = select(Truck).where(func.lower(Truck.number) == number.lower())
        return (await self.session.execute(stmt)).unique().scalar_one_or_none()

    async def get_by_qr_token(self, token: str) -> Truck | None:
        return await self.get_one(qr_token=token)

    async def get_by_ids(self, ids: list[int]) -> list[Truck]:
        stmt = select(Truck).where(Truck.id.in_(ids)).order_by(Truck.number)
        return list((await self.session.execute(stmt)).unique().scalars().all())

    async def search(
        self,
        page: int = 1,
        limit: int = 50,
        query: str | None = None,
        status: str | None = None,
        truck_type_id: int | None = None,
        site_id: int | None = None,
    ) -> tuple[list[Truck], int]:
        """The fleet by number; `query` matches number, manufacturer or model."""
        conditions = []
        if query:
            like = f"%{query}%"
            conditions.append(
                or_(
                    Truck.number.ilike(like),
                    Truck.manufacturer_id.in_(select(TruckManufacturer.id).where(TruckManufacturer.name.ilike(like))),
                    Truck.model_id.in_(select(TruckModel.id).where(TruckModel.name.ilike(like))),
                )
            )
        if status:
            conditions.append(Truck.status == status)
        if truck_type_id:
            conditions.append(Truck.truck_type_id == truck_type_id)
        if site_id:
            conditions.append(Truck.site_id == site_id)

        stmt = select(Truck).where(*conditions).order_by(Truck.number).offset((page - 1) * limit).limit(limit)
        rows = (await self.session.execute(stmt)).unique().scalars().all()
        total = (await self.session.execute(select(func.count()).select_from(Truck).where(*conditions))).scalar() or 0
        return list(rows), total
