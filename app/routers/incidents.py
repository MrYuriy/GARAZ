from datetime import date

from fastapi import APIRouter, File, Form, Path, Query, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core import settings
from app.core.exc import BadRequestException
from app.dependencies import AdminUserDep, IncidentServiceDep, RequestMetaDep, StaffUserDep
from app.enums.incident import IncidentStatus, IncidentType
from app.schemas.incident import (
    IncidentBrief,
    IncidentOut,
    IncidentUpdate,
    OperatorRef,
    StaffIncidentCreate,
    StaffTruckOut,
)
from app.schemas.pagination import Page

router = APIRouter(prefix="/incidents", tags=["Incidents"])

_TOKEN = Path(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


@router.get("", response_model=Page[IncidentBrief])
async def list_incidents(
    staff: StaffUserDep,
    service: IncidentServiceDep,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    query: str | None = Query(None, max_length=64),
    status: IncidentStatus | None = None,
    incident_type: IncidentType | None = None,
    truck_id: int | None = None,
    operator_id: int | None = None,
    category_id: int | None = None,
    flagged: bool | None = None,
    open: bool = Query(False, description="Only Nowe and W trakcie"),
    date_from: date | None = None,
    date_to: date | None = None,
) -> Page[IncidentBrief]:
    """Newest first. `query` matches the truck number or the operator's name; `flagged=true`
    keeps reports with a mark (permit problem, hour meter going back). Dates are local days."""
    return await service.list_incidents(
        page,
        limit,
        query=query,
        status=status,
        incident_type=incident_type,
        truck_id=truck_id,
        operator_id=operator_id,
        category_id=category_id,
        flagged=flagged,
        open_only=open,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/{incident_id}", response_model=IncidentOut)
async def get_incident(incident_id: int, staff: StaffUserDep, service: IncidentServiceDep) -> IncidentOut:
    return await service.get_incident(incident_id)


@router.get("/{incident_id}/photos/{photo_id}", response_class=Response)
async def get_photo(
    incident_id: int, photo_id: int, staff: StaffUserDep, service: IncidentServiceDep, thumb: bool = False
) -> Response:
    """A JPEG (`thumb=true`: the small one for lists)."""
    content = await service.read_photo(incident_id, photo_id, thumb)
    return Response(content, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.patch("/{incident_id}", response_model=IncidentOut)
async def update_incident(
    incident_id: int, data: IncidentUpdate, admin: AdminUserDep, service: IncidentServiceDep, meta: RequestMetaDep
) -> IncidentOut:
    """Move it along Nowe → W trakcie → Zamknięte (or back), with an optional comment.
    A truck stopped by the report goes back to work through PATCH /trucks/{id}."""
    return await service.update_incident(admin, incident_id, data, meta)


# ----- entering a report in the panel, for someone else -----


@router.get("/form/trucks/{truck_id}", response_model=StaffTruckOut)
async def form_truck(truck_id: int, staff: StaffUserDep, service: IncidentServiceDep) -> StaffTruckOut:
    """A truck picked from the list, with the categories the form offers and its last hour meter."""
    return await service.staff_truck(truck_id=truck_id)


@router.get("/form/trucks/by-qr/{token}", response_model=StaffTruckOut)
async def form_truck_by_qr(staff: StaffUserDep, service: IncidentServiceDep, token: str = _TOKEN) -> StaffTruckOut:
    """The same, for a scanned truck sticker."""
    return await service.staff_truck(token=token)


@router.get("/form/operators/by-qr/{token}", response_model=OperatorRef)
async def form_operator_by_qr(staff: StaffUserDep, service: IncidentServiceDep, token: str = _TOKEN) -> OperatorRef:
    """Who a scanned operator card belongs to."""
    return await service.staff_operator(token)


@router.post("", response_model=IncidentOut, status_code=status.HTTP_201_CREATED)
async def create_incident(
    staff: StaffUserDep,
    service: IncidentServiceDep,
    meta: RequestMetaDep,
    data: str = Form(..., description="StaffIncidentCreate as JSON"),
    photos: list[UploadFile] = File(default=[]),
) -> IncidentOut:
    """A report entered by any signed-in user for someone else, e.g. after a phone call.

    The driver is a registered operator (`operator_id`) or just a name (`operator_name`)
    for a person outside the register; that one is marked. Photos are optional (0–30);
    `occurred_at` may be in the past. Re-sending the same `client_uuid` returns the first one.
    """
    try:
        report = StaffIncidentCreate.model_validate_json(data)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
    cap = settings.incidents.MAX_PHOTO_MB * 1024 * 1024
    if len(photos) > settings.incidents.MAX_PHOTOS:
        raise BadRequestException(f"At most {settings.incidents.MAX_PHOTOS} photos")
    contents = [await photo.read(cap + 1) for photo in photos]
    return await service.create_by_staff(staff, report, contents, meta)
