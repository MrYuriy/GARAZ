from fastapi import APIRouter, Query, Response, status

from app.dependencies import AdminUserDep, RequestMetaDep, StaffUserDep, TruckServiceDep
from app.enums.truck import TruckStatus
from app.routers.files import file_response as _download
from app.schemas.pagination import Page
from app.schemas.truck import TruckCreate, TruckOut, TruckUpdate

router = APIRouter(prefix="/trucks", tags=["Trucks"])


@router.get("", response_model=Page[TruckOut])
async def list_trucks(
    staff: StaffUserDep,
    service: TruckServiceDep,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    query: str | None = Query(None, max_length=64),
    status: TruckStatus | None = None,
    truck_type_id: int | None = None,
    site_id: int | None = None,
) -> Page[TruckOut]:
    """The fleet, by number; `query` matches number, manufacturer or model."""
    return await service.list_trucks(page, limit, query, status, truck_type_id, site_id)


@router.get("/labels.pdf", response_class=Response)
async def labels_pdf(
    staff: StaffUserDep, service: TruckServiceDep, ids: list[int] = Query(..., max_length=200)
) -> Response:
    """QR stickers for the chosen trucks, 8 per A4 sheet, ready to print."""
    return _download(await service.labels_pdf(ids), "application/pdf", "etykiety-wozkow.pdf")


@router.get("/{truck_id}", response_model=TruckOut)
async def get_truck(truck_id: int, staff: StaffUserDep, service: TruckServiceDep) -> TruckOut:
    return await service.get_truck(truck_id)


@router.get("/{truck_id}/qr.png", response_class=Response)
async def truck_qr_png(truck_id: int, staff: StaffUserDep, service: TruckServiceDep) -> Response:
    number, png = await service.qr_png(truck_id)
    return _download(png, "image/png", f"qr-{number}.png")


@router.post("", response_model=TruckOut, status_code=status.HTTP_201_CREATED)
async def create_truck(
    data: TruckCreate, admin: AdminUserDep, service: TruckServiceDep, meta: RequestMetaDep
) -> TruckOut:
    """Add a truck; it gets its QR token at once."""
    return await service.create_truck(admin, data, meta)


@router.patch("/{truck_id}", response_model=TruckOut)
async def update_truck(
    truck_id: int, data: TruckUpdate, admin: AdminUserDep, service: TruckServiceDep, meta: RequestMetaDep
) -> TruckOut:
    """Edit details or change the status (e.g. back to ACTIVE after a repair, with a `comment`)."""
    return await service.update_truck(admin, truck_id, data, meta)


@router.post("/{truck_id}/qr", response_model=TruckOut)
async def reissue_qr(truck_id: int, admin: AdminUserDep, service: TruckServiceDep, meta: RequestMetaDep) -> TruckOut:
    """Issue a new QR code. The old sticker stops working immediately."""
    return await service.reissue_qr(admin, truck_id, meta)


@router.delete("/{truck_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_truck(truck_id: int, admin: AdminUserDep, service: TruckServiceDep, meta: RequestMetaDep) -> None:
    """For a truck added by mistake; one that left the fleet should be set INACTIVE to keep its history."""
    await service.delete_truck(admin, truck_id, meta)
