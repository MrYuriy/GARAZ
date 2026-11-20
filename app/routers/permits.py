from fastapi import APIRouter, File, Query, Response, UploadFile, status

from app.core import settings
from app.core.exc import BadRequestException
from app.dependencies import AdminUserDep, PermitServiceDep, RequestMetaDep, StaffUserDep
from app.enums.permit import PermitStatus
from app.routers.files import file_response
from app.schemas.pagination import Page
from app.schemas.permit import PermitCreate, PermitOut, PermitRenew, PermitUpdate

router = APIRouter(prefix="/permits", tags=["Permits"])


@router.get("", response_model=Page[PermitOut])
async def list_permits(
    staff: StaffUserDep,
    service: PermitServiceDep,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    query: str | None = Query(None, max_length=64),
    status: PermitStatus | None = None,
    operator_id: int | None = None,
    category_id: int | None = None,
    truck_type_id: int | None = None,
    expiring_within_days: int | None = Query(None, ge=0, le=3650),
) -> Page[PermitOut]:
    """Soonest to expire first. `query` matches the permit number or the operator's name;
    `expiring_within_days=30` lists those whose last day is at most 30 days away (expired ones too,
    unless `status=ACTIVE`)."""
    return await service.list_permits(
        page, limit, query, status, operator_id, category_id, truck_type_id, expiring_within_days
    )


@router.get("/cards.pdf", response_class=Response)
async def permit_cards(
    staff: StaffUserDep, service: PermitServiceDep, ids: list[int] = Query(..., max_length=200)
) -> Response:
    """The permits printed on form PL-FORM-QHSE-009, eight to an A4 sheet, to cut out and sign."""
    return file_response(await service.cards_pdf(ids), "application/pdf", "upowaznienia.pdf")


@router.get("/{permit_id}", response_model=PermitOut)
async def get_permit(permit_id: int, staff: StaffUserDep, service: PermitServiceDep) -> PermitOut:
    return await service.get_permit(permit_id)


@router.post("", response_model=PermitOut, status_code=status.HTTP_201_CREATED)
async def create_permit(
    data: PermitCreate, admin: AdminUserDep, service: PermitServiceDep, meta: RequestMetaDep
) -> PermitOut:
    """Add a permit to an operator. Its status follows from the dates (EXPIRED if already past)."""
    return await service.create_permit(admin, data, meta)


@router.patch("/{permit_id}", response_model=PermitOut)
async def update_permit(
    permit_id: int, data: PermitUpdate, admin: AdminUserDep, service: PermitServiceDep, meta: RequestMetaDep
) -> PermitOut:
    """Edit, suspend (`status: SUSPENDED`, with a `comment`) or lift a suspension."""
    return await service.update_permit(admin, permit_id, data, meta)


@router.post("/{permit_id}/renew", response_model=PermitOut, status_code=status.HTTP_201_CREATED)
async def renew_permit(
    permit_id: int, data: PermitRenew, admin: AdminUserDep, service: PermitServiceDep, meta: RequestMetaDep
) -> PermitOut:
    """A new permit with the next number of the year; the old one is archived as it was."""
    return await service.renew_permit(admin, permit_id, data, meta)


@router.get("/{permit_id}/document", response_class=Response)
async def get_document(permit_id: int, staff: StaffUserDep, service: PermitServiceDep) -> Response:
    """The scanned basis document, shown in the browser."""
    content, content_type, filename = await service.read_document(permit_id)
    return file_response(content, content_type, filename, inline=True)


@router.put("/{permit_id}/document", response_model=PermitOut)
async def attach_document(
    permit_id: int,
    admin: AdminUserDep,
    service: PermitServiceDep,
    meta: RequestMetaDep,
    file: UploadFile = File(...),
) -> PermitOut:
    """Attach (or replace) the scan: PDF, JPEG, PNG or WebP."""
    limit = settings.storage.MAX_DOCUMENT_MB * 1024 * 1024
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise BadRequestException(f"The file is larger than {settings.storage.MAX_DOCUMENT_MB} MB")
    return await service.attach_document(admin, permit_id, file.filename, content, meta)


@router.delete("/{permit_id}/document", response_model=PermitOut)
async def remove_document(
    permit_id: int, admin: AdminUserDep, service: PermitServiceDep, meta: RequestMetaDep
) -> PermitOut:
    return await service.remove_document(admin, permit_id, meta)
