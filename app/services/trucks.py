from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exc import BadRequestException, ObjectAlreadyExistsException, ObjectNotFoundException
from app.core.request_meta import RequestMeta
from app.core.security.qr_token import new_qr_token, truck_qr_url
from app.core.time import utcnow
from app.database.postgres import get_session
from app.enums.audit import AuditAction
from app.enums.truck import TruckStatus
from app.models import Truck
from app.models.dictionary import Site, TruckType
from app.repositories.dictionary import DictionaryRepository
from app.repositories.truck import TruckRepository
from app.schemas.pagination import Page
from app.schemas.truck import TruckCreate, TruckOut, TruckUpdate
from app.schemas.user import UserOut
from app.services import qr
from app.services.audit import AuditService
from app.services.refs import ensure_active, only_site

MAX_LABELS = 200


class TruckService:
    """The fleet register and its QR stickers."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.trucks = TruckRepository(session)
        self.sites = DictionaryRepository(session, Site)
        self.types = DictionaryRepository(session, TruckType)
        self.audit = AuditService(session)

    async def list_trucks(
        self,
        page: int = 1,
        limit: int = 50,
        query: str | None = None,
        status: TruckStatus | None = None,
        truck_type_id: int | None = None,
        site_id: int | None = None,
    ) -> Page[TruckOut]:
        rows, total = await self.trucks.search(
            page, limit, query, status.value if status else None, truck_type_id, site_id
        )
        return Page(items=[TruckOut.model_validate(r) for r in rows], total=total, page=page, limit=limit)

    async def get_truck(self, truck_id: int) -> TruckOut:
        return TruckOut.model_validate(await self._get_or_404(truck_id))

    async def create_truck(self, acting: UserOut, data: TruckCreate, meta: RequestMeta | None = None) -> TruckOut:
        await self._ensure_number_free(data.number)
        await ensure_active(self.types, data.truck_type_id, "Truck type")
        site_id = data.site_id or await only_site(self.sites)
        if data.site_id:
            await ensure_active(self.sites, site_id, "Site")

        truck = await self.trucks.create_one(
            {
                "number": data.number,
                "manufacturer": data.manufacturer,
                "model": data.model,
                "truck_type_id": data.truck_type_id,
                "site_id": site_id,
                "status": TruckStatus.ACTIVE.value,
                "qr_token": new_qr_token(),
                "qr_issued_at": utcnow(),
            }
        )
        await self.audit.record(
            AuditAction.TRUCK_CREATED,
            user_id=acting.id,
            resource_type="truck",
            resource_id=truck.id,
            payload={"number": data.number, "truck_type_id": data.truck_type_id, "site_id": site_id},
            meta=meta,
        )
        await self.session.commit()
        return await self.get_truck(truck.id)

    async def update_truck(
        self, acting: UserOut, truck_id: int, data: TruckUpdate, meta: RequestMeta | None = None
    ) -> TruckOut:
        truck = await self._get_or_404(truck_id)
        sent = data.model_dump(exclude_unset=True)
        comment = sent.pop("comment", None)
        if "status" in sent and sent["status"] is not None:
            sent["status"] = sent["status"].value

        changes = {}
        for key, value in sent.items():
            # Manufacturer and model may be cleared; everything else ignores null.
            if value is None and key not in ("manufacturer", "model"):
                continue
            if value != getattr(truck, key):
                changes[key] = value

        if "number" in changes and changes["number"].lower() != truck.number.lower():
            await self._ensure_number_free(changes["number"])
        if "truck_type_id" in changes:
            await ensure_active(self.types, changes["truck_type_id"], "Truck type")
        if "site_id" in changes:
            await ensure_active(self.sites, changes["site_id"], "Site")

        if changes:
            await self.trucks.update_one(truck, changes)
            payload = dict(changes)
            if comment:
                payload["comment"] = comment
            await self.audit.record(
                AuditAction.TRUCK_UPDATED,
                user_id=acting.id,
                resource_type="truck",
                resource_id=truck.id,
                payload=payload,
                meta=meta,
            )
            await self.session.commit()
        return TruckOut.model_validate(await self.trucks.get_by_id(truck_id, fresh=True))

    async def reissue_qr(self, acting: UserOut, truck_id: int, meta: RequestMeta | None = None) -> TruckOut:
        """New token: the printed sticker stops working at once and must be replaced."""
        truck = await self._get_or_404(truck_id)
        await self.trucks.update_one(truck, {"qr_token": new_qr_token(), "qr_issued_at": utcnow()})
        await self.audit.record(
            AuditAction.TRUCK_QR_REISSUED,
            user_id=acting.id,
            resource_type="truck",
            resource_id=truck.id,
            payload={"number": truck.number},
            meta=meta,
        )
        await self.session.commit()
        return TruckOut.model_validate(await self.trucks.get_by_id(truck_id, fresh=True))

    async def qr_png(self, truck_id: int) -> tuple[str, bytes]:
        truck = await self._get_or_404(truck_id)
        return truck.number, qr.qr_png(truck_qr_url(truck.qr_token))

    async def labels_pdf(self, ids: list[int]) -> bytes:
        unique = list(dict.fromkeys(ids))
        if not unique:
            raise BadRequestException("Choose at least one truck")
        if len(unique) > MAX_LABELS:
            raise BadRequestException(f"At most {MAX_LABELS} labels at once")
        trucks = await self.trucks.get_by_ids(unique)
        missing = set(unique) - {t.id for t in trucks}
        if missing:
            raise ObjectNotFoundException(sorted(missing)[0], "Truck")
        labels = [
            qr.Label(qr_data=truck_qr_url(t.qr_token), title=t.number, subtitle=t.truck_type.name) for t in trucks
        ]
        return qr.labels_pdf(labels)

    async def _get_or_404(self, truck_id: int) -> Truck:
        truck = await self.trucks.get_by_id(truck_id)
        if truck is None:
            raise ObjectNotFoundException(truck_id, "Truck")
        return truck

    async def _ensure_number_free(self, number: str) -> None:
        if await self.trucks.get_by_number(number):
            raise ObjectAlreadyExistsException(number, "Truck")


async def get_truck_service(session: AsyncSession = Depends(get_session)) -> TruckService:
    return TruckService(session)
