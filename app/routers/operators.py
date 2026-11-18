from fastapi import APIRouter, Query, Response, status

from app.dependencies import AdminUserDep, OperatorServiceDep, RequestMetaDep, StaffUserDep
from app.routers.files import file_response
from app.schemas.operator import OperatorCreate, OperatorOut, OperatorUpdate
from app.schemas.pagination import Page

router = APIRouter(prefix="/operators", tags=["Operators"])


@router.get("", response_model=Page[OperatorOut])
async def list_operators(
    staff: StaffUserDep,
    service: OperatorServiceDep,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    query: str | None = Query(None, max_length=64),
    employer_id: int | None = None,
    is_active: bool | None = None,
) -> Page[OperatorOut]:
    """Operators by name, each with their permits; `query` matches the name or the Hyster card."""
    return await service.list_operators(page, limit, query, employer_id, is_active)


@router.get("/cards.pdf", response_class=Response)
async def cards_pdf(
    staff: StaffUserDep, service: OperatorServiceDep, ids: list[int] = Query(..., max_length=200)
) -> Response:
    """QR cards for the chosen operators, 8 per A4 sheet."""
    return file_response(await service.cards_pdf(ids), "application/pdf", "karty-operatorow.pdf")


@router.get("/{operator_id}", response_model=OperatorOut)
async def get_operator(operator_id: int, staff: StaffUserDep, service: OperatorServiceDep) -> OperatorOut:
    return await service.get_operator(operator_id)


@router.get("/{operator_id}/qr.png", response_class=Response)
async def operator_qr_png(operator_id: int, staff: StaffUserDep, service: OperatorServiceDep) -> Response:
    name, png = await service.qr_png(operator_id)
    return file_response(png, "image/png", f"qr-{name}.png")


@router.post("", response_model=OperatorOut, status_code=status.HTTP_201_CREATED)
async def create_operator(
    data: OperatorCreate, admin: AdminUserDep, service: OperatorServiceDep, meta: RequestMetaDep
) -> OperatorOut:
    """Add an operator; they get their QR token at once. Permits are added separately."""
    return await service.create_operator(admin, data, meta)


@router.patch("/{operator_id}", response_model=OperatorOut)
async def update_operator(
    operator_id: int, data: OperatorUpdate, admin: AdminUserDep, service: OperatorServiceDep, meta: RequestMetaDep
) -> OperatorOut:
    """Edit details; `is_active: false` when the person has left."""
    return await service.update_operator(admin, operator_id, data, meta)


@router.post("/{operator_id}/qr", response_model=OperatorOut)
async def reissue_operator_qr(
    operator_id: int, admin: AdminUserDep, service: OperatorServiceDep, meta: RequestMetaDep
) -> OperatorOut:
    """Issue a new QR code. The old card stops working immediately."""
    return await service.reissue_qr(admin, operator_id, meta)
