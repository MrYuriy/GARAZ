from datetime import date

from fastapi import APIRouter, Query, Response

from app.dependencies import AdminUserDep, IncidentServiceDep, RequestMetaDep, StaffUserDep
from app.enums.incident import IncidentStatus, IncidentType
from app.schemas.incident import IncidentBrief, IncidentOut, IncidentUpdate
from app.schemas.pagination import Page

router = APIRouter(prefix="/incidents", tags=["Incidents"])


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
