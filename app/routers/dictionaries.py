from fastapi import APIRouter, status

from app.dependencies import AdminUserDep, DictionaryServiceDep, RequestMetaDep, StaffUserDep
from app.enums.dictionary import DictionaryKind
from app.enums.incident import IncidentType
from app.schemas.dictionary import DictionaryEntryCreate, DictionaryEntryOut, DictionaryEntryUpdate

router = APIRouter(prefix="/dictionaries", tags=["Dictionaries"])


@router.get("/{kind}", response_model=list[DictionaryEntryOut])
async def list_entries(
    kind: DictionaryKind,
    staff: StaffUserDep,
    service: DictionaryServiceDep,
    include_inactive: bool = False,
    incident_type: IncidentType | None = None,
) -> list[DictionaryEntryOut]:
    """A whole list, in display order. Lists are short, so there is no paging.

    `incident_type` narrows incident categories to the ones a report of that type offers.
    """
    return await service.list_entries(kind, include_inactive, incident_type)


@router.post("/{kind}", response_model=DictionaryEntryOut, status_code=status.HTTP_201_CREATED)
async def create_entry(
    kind: DictionaryKind,
    data: DictionaryEntryCreate,
    admin: AdminUserDep,
    service: DictionaryServiceDep,
    meta: RequestMetaDep,
) -> DictionaryEntryOut:
    return await service.create_entry(admin, kind, data, meta)


@router.patch("/{kind}/{entry_id}", response_model=DictionaryEntryOut)
async def update_entry(
    kind: DictionaryKind,
    entry_id: int,
    data: DictionaryEntryUpdate,
    admin: AdminUserDep,
    service: DictionaryServiceDep,
    meta: RequestMetaDep,
) -> DictionaryEntryOut:
    """Rename, reorder, or switch an entry off (`is_active: false`). Entries are never deleted."""
    return await service.update_entry(admin, kind, entry_id, data, meta)
