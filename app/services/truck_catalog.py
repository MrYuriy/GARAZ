from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exc import InUseException, ObjectAlreadyExistsException, ObjectNotFoundException
from app.core.request_meta import RequestMeta
from app.database.postgres import get_session
from app.enums.audit import AuditAction
from app.models import TruckManufacturer, TruckModel
from app.repositories.truck_catalog import (
    ManufacturerRepository,
    TruckModelRepository,
    truck_counts,
    trucks_using,
)
from app.schemas.truck_catalog import ManufacturerOut, NameIn, TruckModelCreate, TruckModelOut
from app.schemas.user import UserOut
from app.services.audit import AuditService


class TruckCatalogService:
    """Manufacturers and their models, which trucks are picked from.

    Deleting is allowed only while no truck uses the entry; otherwise the
    answer lists the trucks, so they can be changed or deleted first.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.makers = ManufacturerRepository(session)
        self.models = TruckModelRepository(session)
        self.audit = AuditService(session)

    async def list_manufacturers(self) -> list[ManufacturerOut]:
        per_maker, per_model = await truck_counts(self.session)
        return [self._out(m, per_maker, per_model) for m in await self.makers.list_all()]

    async def create_manufacturer(
        self, acting: UserOut, data: NameIn, meta: RequestMeta | None = None
    ) -> ManufacturerOut:
        await self._ensure_maker_name_free(data.name)
        maker = await self.makers.create_one({"name": data.name})
        await self._record(AuditAction.TRUCK_MANUFACTURER_CREATED, acting, "truck_manufacturer", maker.id, data, meta)
        await self.session.commit()
        return await self._maker_out(maker.id)

    async def rename_manufacturer(
        self, acting: UserOut, maker_id: int, data: NameIn, meta: RequestMeta | None = None
    ) -> ManufacturerOut:
        maker = await self._maker_or_404(maker_id)
        if data.name != maker.name:
            if data.name.lower() != maker.name.lower():
                await self._ensure_maker_name_free(data.name)
            old = maker.name
            await self.makers.update_one(maker, {"name": data.name})
            await self.audit.record(
                AuditAction.TRUCK_MANUFACTURER_UPDATED,
                user_id=acting.id,
                resource_type="truck_manufacturer",
                resource_id=maker_id,
                payload={"name": data.name, "old_name": old},
                meta=meta,
            )
            await self.session.commit()
        return await self._maker_out(maker_id)

    async def delete_manufacturer(self, acting: UserOut, maker_id: int, meta: RequestMeta | None = None) -> None:
        maker = await self._maker_or_404(maker_id)
        trucks = await trucks_using(self.session, manufacturer_id=maker_id)
        if trucks:
            raise InUseException(f"Manufacturer {maker.name!r} is used by {len(trucks)} truck(s)", trucks)
        payload = {"name": maker.name, "models": [m.name for m in maker.models]}
        await self.makers.delete_one(maker)
        await self.audit.record(
            AuditAction.TRUCK_MANUFACTURER_DELETED,
            user_id=acting.id,
            resource_type="truck_manufacturer",
            resource_id=maker_id,
            payload=payload,
            meta=meta,
        )
        await self.session.commit()

    async def create_model(
        self, acting: UserOut, data: TruckModelCreate, meta: RequestMeta | None = None
    ) -> TruckModelOut:
        await self._maker_or_404(data.manufacturer_id)
        await self._ensure_model_name_free(data.manufacturer_id, data.name)
        model = await self.models.create_one({"manufacturer_id": data.manufacturer_id, "name": data.name})
        await self._record(AuditAction.TRUCK_MODEL_CREATED, acting, "truck_model", model.id, data, meta)
        await self.session.commit()
        return TruckModelOut(id=model.id, name=model.name)

    async def rename_model(
        self, acting: UserOut, model_id: int, data: NameIn, meta: RequestMeta | None = None
    ) -> TruckModelOut:
        model = await self._model_or_404(model_id)
        if data.name != model.name:
            if data.name.lower() != model.name.lower():
                await self._ensure_model_name_free(model.manufacturer_id, data.name)
            old = model.name
            await self.models.update_one(model, {"name": data.name})
            await self.audit.record(
                AuditAction.TRUCK_MODEL_UPDATED,
                user_id=acting.id,
                resource_type="truck_model",
                resource_id=model_id,
                payload={"name": data.name, "old_name": old},
                meta=meta,
            )
            await self.session.commit()
        trucks = await trucks_using(self.session, model_id=model_id)
        return TruckModelOut(id=model.id, name=model.name, truck_count=len(trucks))

    async def delete_model(self, acting: UserOut, model_id: int, meta: RequestMeta | None = None) -> None:
        model = await self._model_or_404(model_id)
        trucks = await trucks_using(self.session, model_id=model_id)
        if trucks:
            raise InUseException(f"Model {model.name!r} is used by {len(trucks)} truck(s)", trucks)
        payload = {"name": model.name, "manufacturer_id": model.manufacturer_id}
        await self.models.delete_one(model)
        await self.audit.record(
            AuditAction.TRUCK_MODEL_DELETED,
            user_id=acting.id,
            resource_type="truck_model",
            resource_id=model_id,
            payload=payload,
            meta=meta,
        )
        await self.session.commit()

    async def _record(self, action: AuditAction, acting: UserOut, kind: str, row_id: int, data, meta) -> None:
        await self.audit.record(
            action, user_id=acting.id, resource_type=kind, resource_id=row_id, payload=data.model_dump(), meta=meta
        )

    async def _maker_out(self, maker_id: int) -> ManufacturerOut:
        per_maker, per_model = await truck_counts(self.session)
        return self._out(await self.makers.get_by_id(maker_id, fresh=True), per_maker, per_model)

    @staticmethod
    def _out(maker: TruckManufacturer, per_maker: dict[int, int], per_model: dict[int, int]) -> ManufacturerOut:
        return ManufacturerOut(
            id=maker.id,
            name=maker.name,
            truck_count=per_maker.get(maker.id, 0),
            models=[TruckModelOut(id=m.id, name=m.name, truck_count=per_model.get(m.id, 0)) for m in maker.models],
        )

    async def _maker_or_404(self, maker_id: int) -> TruckManufacturer:
        maker = await self.makers.get_by_id(maker_id)
        if maker is None:
            raise ObjectNotFoundException(maker_id, "Truck manufacturer")
        return maker

    async def _model_or_404(self, model_id: int) -> TruckModel:
        model = await self.models.get_by_id(model_id)
        if model is None:
            raise ObjectNotFoundException(model_id, "Truck model")
        return model

    async def _ensure_maker_name_free(self, name: str) -> None:
        if await self.makers.get_by_name(name):
            raise ObjectAlreadyExistsException(name, "Truck manufacturer")

    async def _ensure_model_name_free(self, maker_id: int, name: str) -> None:
        if await self.models.get_by_name(maker_id, name):
            raise ObjectAlreadyExistsException(name, "Truck model")


async def get_truck_catalog_service(session: AsyncSession = Depends(get_session)) -> TruckCatalogService:
    return TruckCatalogService(session)
