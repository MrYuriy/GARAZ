from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exc import BadRequestException, ObjectAlreadyExistsException, ObjectNotFoundException
from app.core.request_meta import RequestMeta
from app.database.postgres import get_session
from app.enums.audit import AuditAction
from app.enums.dictionary import DictionaryKind
from app.enums.incident import IncidentType
from app.models.dictionary import DictionaryMixin, Employer, IncidentCategory, PermitCategory, Site, TruckType
from app.repositories.dictionary import DictionaryRepository
from app.schemas.dictionary import DictionaryEntryCreate, DictionaryEntryOut, DictionaryEntryUpdate
from app.schemas.user import UserOut
from app.services.audit import AuditService

MODELS: dict[DictionaryKind, type[DictionaryMixin]] = {
    DictionaryKind.SITES: Site,
    DictionaryKind.PERMIT_CATEGORIES: PermitCategory,
    DictionaryKind.TRUCK_TYPES: TruckType,
    DictionaryKind.EMPLOYERS: Employer,
    DictionaryKind.INCIDENT_CATEGORIES: IncidentCategory,
}

_INCIDENT_ONLY = ("incident_types", "default_out_of_service")


class DictionaryService:
    """The panel's lists. One code path for all of them; incident categories
    add which event types they belong to and a default for "wyłączony"."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)

    def _repo(self, kind: DictionaryKind) -> DictionaryRepository:
        return DictionaryRepository(self.session, MODELS[kind])

    async def list_entries(
        self, kind: DictionaryKind, include_inactive: bool = False, incident_type: IncidentType | None = None
    ) -> list[DictionaryEntryOut]:
        if incident_type is not None and kind != DictionaryKind.INCIDENT_CATEGORIES:
            raise BadRequestException("incident_type filters incident categories only")
        rows = await self._repo(kind).list_entries(include_inactive)
        if incident_type is not None:
            rows = [r for r in rows if incident_type.value in (r.incident_types or [])]
        return [DictionaryEntryOut.model_validate(r) for r in rows]

    async def create_entry(
        self, acting: UserOut, kind: DictionaryKind, data: DictionaryEntryCreate, meta: RequestMeta | None = None
    ) -> DictionaryEntryOut:
        self._check_extras(kind, data.model_dump(exclude_unset=True))
        repo = self._repo(kind)
        await self._ensure_name_free(repo, data.name)

        values: dict = {"name": data.name, "sort_order": data.sort_order}
        if kind == DictionaryKind.INCIDENT_CATEGORIES:
            values["incident_types"] = _types(data.incident_types)
            values["default_out_of_service"] = bool(data.default_out_of_service)
        row = await repo.create_one(values)
        await self.audit.record(
            AuditAction.DICTIONARY_CREATED,
            user_id=acting.id,
            resource_type=kind.value,
            resource_id=row.id,
            payload={key: value for key, value in values.items() if key != "sort_order"},
            meta=meta,
        )
        await self.session.commit()
        return DictionaryEntryOut.model_validate(row)

    async def update_entry(
        self,
        acting: UserOut,
        kind: DictionaryKind,
        entry_id: int,
        data: DictionaryEntryUpdate,
        meta: RequestMeta | None = None,
    ) -> DictionaryEntryOut:
        sent = data.model_dump(exclude_unset=True)
        self._check_extras(kind, sent)
        repo = self._repo(kind)
        row = await repo.get_by_id(entry_id)
        if row is None:
            raise ObjectNotFoundException(entry_id, "Dictionary entry")

        if "incident_types" in sent:
            sent["incident_types"] = _types(data.incident_types)
        changes = {key: value for key, value in sent.items() if value is not None and value != getattr(row, key)}
        if "name" in changes and changes["name"].lower() != row.name.lower():
            await self._ensure_name_free(repo, changes["name"])

        if changes:
            row = await repo.update_one(row, changes)
            await self.audit.record(
                AuditAction.DICTIONARY_UPDATED,
                user_id=acting.id,
                resource_type=kind.value,
                resource_id=row.id,
                payload=changes,
                meta=meta,
            )
            await self.session.commit()
        return DictionaryEntryOut.model_validate(row)

    @staticmethod
    def _check_extras(kind: DictionaryKind, sent: dict) -> None:
        if kind == DictionaryKind.INCIDENT_CATEGORIES:
            return
        if any(sent.get(key) is not None for key in _INCIDENT_ONLY):
            raise BadRequestException("incident_types and default_out_of_service belong to incident categories only")

    @staticmethod
    async def _ensure_name_free(repo: DictionaryRepository, name: str) -> None:
        if await repo.get_by_name(name):
            raise ObjectAlreadyExistsException(name, "Dictionary entry")


def _types(types: list[IncidentType] | None) -> list[str]:
    """At least one type, each once, in the enum's order."""
    chosen = {t.value for t in types or []}
    if not chosen:
        raise BadRequestException("An incident category needs at least one incident type")
    return [t.value for t in IncidentType if t.value in chosen]


async def get_dictionary_service(session: AsyncSession = Depends(get_session)) -> DictionaryService:
    return DictionaryService(session)
