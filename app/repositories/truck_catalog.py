from sqlalchemy import func, select

from app.models import Truck, TruckManufacturer, TruckModel
from app.repositories.base import BaseRepository


class ManufacturerRepository(BaseRepository[TruckManufacturer]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=TruckManufacturer)

    async def list_all(self) -> list[TruckManufacturer]:
        stmt = select(TruckManufacturer).order_by(func.lower(TruckManufacturer.name))
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_by_id(self, manufacturer_id: int, fresh: bool = False) -> TruckManufacturer | None:
        stmt = select(TruckManufacturer).where(TruckManufacturer.id == manufacturer_id)
        if fresh:
            stmt = stmt.execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_name(self, name: str) -> TruckManufacturer | None:
        """Case-insensitive: "linde" and "Linde" are one manufacturer."""
        stmt = select(TruckManufacturer).where(func.lower(TruckManufacturer.name) == name.lower())
        return (await self.session.execute(stmt)).scalar_one_or_none()


class TruckModelRepository(BaseRepository[TruckModel]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=TruckModel)

    async def get_by_id(self, model_id: int) -> TruckModel | None:
        return await self.session.get(TruckModel, model_id)

    async def get_by_name(self, manufacturer_id: int, name: str) -> TruckModel | None:
        stmt = select(TruckModel).where(
            TruckModel.manufacturer_id == manufacturer_id, func.lower(TruckModel.name) == name.lower()
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()


async def trucks_using(session, *, manufacturer_id: int | None = None, model_id: int | None = None) -> list[dict]:
    """The trucks pointing at a manufacturer (its models included) or at one model, by number."""
    stmt = select(Truck.id, Truck.number).order_by(Truck.number)
    if manufacturer_id is not None:
        stmt = stmt.where(Truck.manufacturer_id == manufacturer_id)
    if model_id is not None:
        stmt = stmt.where(Truck.model_id == model_id)
    return [{"id": row.id, "number": row.number} for row in (await session.execute(stmt)).all()]


async def truck_counts(session) -> tuple[dict[int, int], dict[int, int]]:
    """How many trucks use each manufacturer and each model."""
    makers = await session.execute(
        select(Truck.manufacturer_id, func.count())
        .where(Truck.manufacturer_id.is_not(None))
        .group_by(Truck.manufacturer_id)
    )
    models = await session.execute(
        select(Truck.model_id, func.count()).where(Truck.model_id.is_not(None)).group_by(Truck.model_id)
    )
    return dict(makers.all()), dict(models.all())
