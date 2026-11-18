import logging
import uuid
from datetime import datetime, timedelta

from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.core.exc import BadRequestException, ObjectNotFoundException
from app.core.request_meta import RequestMeta
from app.core.time import local_today, local_zone, utcnow
from app.database.postgres import get_session
from app.enums.audit import AuditAction
from app.enums.incident import IncidentFlag, IncidentStatus, IncidentType
from app.enums.permit import PermitStatus
from app.enums.truck import TruckStatus
from app.models import Incident, IncidentEvent, IncidentPhoto, Operator, Truck
from app.models.dictionary import IncidentCategory
from app.repositories.base import BaseRepository
from app.repositories.dictionary import DictionaryRepository
from app.repositories.incident import IncidentRepository
from app.repositories.operator import OperatorRepository
from app.repositories.truck import TruckRepository
from app.schemas.incident import (
    IncidentBrief,
    IncidentOut,
    IncidentSubmit,
    IncidentUpdate,
    OperatorCheck,
    PublicCategory,
    PublicIncidentOut,
    PublicOperatorOut,
    PublicTruckOut,
)
from app.schemas.pagination import Page
from app.schemas.user import UserOut
from app.services.audit import AuditService
from app.services.permits import status_for
from app.services.photos import Photo, process_photo
from app.services.storage import FileStorage, get_file_storage

logger = logging.getLogger(__name__)


def display_name(full_name: str) -> str:
    """ "Jan Kowalski" -> "Jan K.": shown to whoever holds the card, nothing more."""
    parts = full_name.split()
    if len(parts) < 2:
        return parts[0] if parts else "?"
    return f"{parts[0]} {parts[-1][0]}."


def permit_flags(operator: Operator, truck: Truck) -> list[IncidentFlag]:
    """What is wrong with the operator's right to drive this truck today."""
    flags = []
    if not operator.is_active:
        flags.append(IncidentFlag.OPERATOR_INACTIVE)
    today = local_today()
    active = [
        p for p in operator.permits if status_for(PermitStatus(p.status), p.valid_until, today) == PermitStatus.ACTIVE
    ]
    if not active:
        flags.append(IncidentFlag.NO_ACTIVE_PERMIT)
    elif not any(truck.truck_type_id in {t.id for t in p.truck_types} for p in active):
        flags.append(IncidentFlag.TRUCK_TYPE_NOT_PERMITTED)
    return flags


class IncidentService:
    """Reports from the operators' phones (public) and their handling in the panel."""

    def __init__(self, session: AsyncSession, storage: FileStorage) -> None:
        self.session = session
        self.storage = storage
        self.incidents = IncidentRepository(session)
        self.trucks = TruckRepository(session)
        self.operators = OperatorRepository(session)
        self.categories = DictionaryRepository(session, IncidentCategory)
        self.photos = BaseRepository(session, IncidentPhoto)
        self.events = BaseRepository(session, IncidentEvent)
        self.audit = AuditService(session)

    # ----- public -----

    async def public_truck(self, token: str) -> PublicTruckOut:
        truck = await self._truck(token)
        categories = await self.categories.list_entries()
        return PublicTruckOut(
            number=truck.number,
            truck_type=truck.truck_type.name,
            make=" ".join(x.name for x in (truck.manufacturer, truck.model) if x) or None,
            status=TruckStatus(truck.status),
            last_mth=await self.incidents.last_mth(truck.id),
            categories=[
                PublicCategory(
                    id=c.id,
                    name=c.name,
                    incident_types=c.incident_types,
                    default_out_of_service=c.default_out_of_service,
                )
                for c in categories
            ],
        )

    async def public_operator(self, data: OperatorCheck) -> PublicOperatorOut:
        """An operator card opens nothing on its own: the truck's code must come with it."""
        await self._truck(data.truck_token)
        operator = await self._operator(data.operator_token)
        return PublicOperatorOut(display_name=display_name(operator.full_name))

    async def submit(self, data: IncidentSubmit, photos: list[bytes], meta: RequestMeta) -> PublicIncidentOut:
        existing = await self.incidents.get_by_client_uuid(data.client_uuid)
        if existing:
            return self._receipt(existing, created=False)

        truck = await self._truck(data.truck_token)
        operator = await self._operator(data.operator_token)
        await self._check_category(data.category_id, data.incident_type)
        processed = await self._process(photos)

        saved: list[str] = []
        try:
            incident = await self.incidents.create_one(
                {
                    "client_uuid": data.client_uuid,
                    "truck_id": truck.id,
                    "operator_id": operator.id,
                    "incident_type": data.incident_type.value,
                    "category_id": data.category_id,
                    "description": data.description,
                    "mth": data.mth,
                    "out_of_service": data.out_of_service,
                    "flags": [f.value for f in await self._flags(operator, truck, data)],
                    "status": IncidentStatus.NEW.value,
                    "occurred_at": self._occurred_at(data.reported_at),
                    "reporter_ip": meta.ip_address,
                    "reporter_agent": meta.user_agent,
                }
            )
            for position, photo in enumerate(processed):
                saved += await self._store(incident.id, position, photo)
            await self.events.create_one(
                {"incident_id": incident.id, "from_status": None, "to_status": IncidentStatus.NEW.value}
            )
            await self.audit.record(
                AuditAction.INCIDENT_CREATED,
                resource_type="incident",
                resource_id=incident.id,
                payload={
                    "truck": truck.number,
                    "operator_id": operator.id,
                    "incident_type": data.incident_type.value,
                    "category_id": data.category_id,
                    "out_of_service": data.out_of_service,
                    "flags": incident.flags,
                    "photos": len(processed),
                },
                meta=meta,
            )
            if data.out_of_service and truck.status == TruckStatus.ACTIVE.value:
                await self.trucks.update_one(truck, {"status": TruckStatus.OUT_OF_SERVICE.value})
                await self.audit.record(
                    AuditAction.TRUCK_UPDATED,
                    resource_type="truck",
                    resource_id=truck.id,
                    payload={"status": TruckStatus.OUT_OF_SERVICE.value, "incident_id": incident.id},
                    meta=meta,
                )
            await self.session.commit()
        except IntegrityError:
            # The same report arrived twice at once and the other one won.
            await self.session.rollback()
            await self._forget(saved)
            existing = await self.incidents.get_by_client_uuid(data.client_uuid)
            if existing is None:
                raise
            return self._receipt(existing, created=False)
        except BaseException:
            await self._forget(saved)
            raise
        fresh = await self.incidents.get_by_id(incident.id, fresh=True)
        return self._receipt(fresh, created=True)

    # ----- panel -----

    async def list_incidents(self, page: int = 1, limit: int = 50, **filters) -> Page[IncidentBrief]:
        zone = local_zone()
        date_from, date_to = filters.pop("date_from", None), filters.pop("date_to", None)
        if date_from:
            filters["since"] = datetime.combine(date_from, datetime.min.time(), zone)
        if date_to:
            filters["until"] = datetime.combine(date_to + timedelta(days=1), datetime.min.time(), zone)
        for key in ("status", "incident_type"):
            if filters.get(key) is not None:
                filters[key] = filters[key].value
        rows, total = await self.incidents.search(page, limit, **filters)
        return Page(items=[IncidentBrief.model_validate(r) for r in rows], total=total, page=page, limit=limit)

    async def get_incident(self, incident_id: int) -> IncidentOut:
        return IncidentOut.model_validate(await self._get_or_404(incident_id))

    async def update_incident(
        self, acting: UserOut, incident_id: int, data: IncidentUpdate, meta: RequestMeta | None = None
    ) -> IncidentOut:
        incident = await self._get_or_404(incident_id)
        new_status = data.status.value if data.status else incident.status
        if new_status == incident.status and not data.comment:
            return IncidentOut.model_validate(incident)
        await self.events.create_one(
            {
                "incident_id": incident.id,
                "user_id": acting.id,
                "from_status": incident.status,
                "to_status": new_status,
                "comment": data.comment,
            }
        )
        payload: dict = {"comment": data.comment} if data.comment else {}
        if new_status != incident.status:
            payload = {"status": new_status, "old_status": incident.status, **payload}
            await self.incidents.update_one(incident, {"status": new_status})
        await self.audit.record(
            AuditAction.INCIDENT_UPDATED,
            user_id=acting.id,
            resource_type="incident",
            resource_id=incident.id,
            payload=payload,
            meta=meta,
        )
        await self.session.commit()
        return IncidentOut.model_validate(await self.incidents.get_by_id(incident_id, fresh=True))

    async def read_photo(self, incident_id: int, photo_id: int, thumb: bool) -> bytes:
        incident = await self._get_or_404(incident_id)
        photo = next((p for p in incident.photos if p.id == photo_id), None)
        if photo is None:
            raise ObjectNotFoundException(photo_id, "Photo")
        return await self.storage.read(photo.thumb_key if thumb else photo.key)

    # ----- helpers -----

    async def _truck(self, token: str) -> Truck:
        truck = await self.trucks.get_by_qr_token(token)
        # A truck out of the fleet behaves like an unknown code.
        if truck is None or truck.status == TruckStatus.INACTIVE.value:
            raise ObjectNotFoundException(None, "Truck")
        return truck

    async def _operator(self, token: str) -> Operator:
        operator = await self.operators.get_by_qr_token(token)
        if operator is None:
            raise ObjectNotFoundException(None, "Operator")
        return operator

    async def _check_category(self, category_id: int, incident_type: IncidentType) -> None:
        category = await self.categories.get_by_id(category_id)
        if category is None or not category.is_active:
            raise BadRequestException(f"Incident category {category_id} does not exist")
        if incident_type.value not in category.incident_types:
            raise BadRequestException(f"Category {category.name!r} is not offered for {incident_type.value}")

    async def _process(self, photos: list[bytes]) -> list[Photo]:
        cfg = settings.incidents
        if not photos:
            raise BadRequestException("Add at least one photo")
        if len(photos) > cfg.MAX_PHOTOS:
            raise BadRequestException(f"At most {cfg.MAX_PHOTOS} photos")
        if any(len(p) > cfg.MAX_PHOTO_MB * 1024 * 1024 for p in photos):
            raise BadRequestException(f"A photo may be at most {cfg.MAX_PHOTO_MB} MB")
        return [await process_photo(p) for p in photos]

    async def _flags(self, operator: Operator, truck: Truck, data: IncidentSubmit) -> list[IncidentFlag]:
        flags = permit_flags(operator, truck)
        if data.mth is not None:
            last = await self.incidents.last_mth(truck.id)
            if last is not None and float(data.mth) < last:
                flags.append(IncidentFlag.MTH_LOWER_THAN_LAST)
        return flags

    @staticmethod
    def _occurred_at(reported_at: datetime | None) -> datetime:
        """The phone's own time when plausible: not in the future, not long ago."""
        now = utcnow()
        if reported_at is None or reported_at.tzinfo is None:
            return now
        oldest = now - timedelta(days=settings.incidents.MAX_REPORT_DELAY_DAYS)
        if reported_at > now + timedelta(minutes=5) or reported_at < oldest:
            return now
        return min(reported_at, now)

    async def _store(self, incident_id: int, position: int, photo: Photo) -> list[str]:
        name = uuid.uuid4().hex
        key, thumb_key = f"incidents/{incident_id}/{name}.jpg", f"incidents/{incident_id}/{name}_t.jpg"
        await self.storage.save(key, photo.full)
        await self.storage.save(thumb_key, photo.thumb)
        await self.photos.create_one(
            {
                "incident_id": incident_id,
                "position": position,
                "key": key,
                "thumb_key": thumb_key,
                "size": len(photo.full),
                "width": photo.width,
                "height": photo.height,
            }
        )
        return [key, thumb_key]

    async def _forget(self, keys: list[str]) -> None:
        for key in keys:
            try:
                await self.storage.delete(key)
            except OSError:
                logger.exception("Could not remove %s after a failed report", key)

    @staticmethod
    def _receipt(incident: Incident, created: bool) -> PublicIncidentOut:
        return PublicIncidentOut(
            id=incident.id,
            created=created,
            truck_out_of_service=incident.truck.status == TruckStatus.OUT_OF_SERVICE.value,
        )

    async def _get_or_404(self, incident_id: int) -> Incident:
        incident = await self.incidents.get_by_id(incident_id)
        if incident is None:
            raise ObjectNotFoundException(incident_id, "Incident")
        return incident


async def get_incident_service(
    session: AsyncSession = Depends(get_session), storage: FileStorage = Depends(get_file_storage)
) -> IncidentService:
    return IncidentService(session, storage)
