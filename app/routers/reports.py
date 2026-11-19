from datetime import date

from fastapi import APIRouter, Query, Response

from app.dependencies import ReportServiceDep, RequestMetaDep, StaffUserDep
from app.enums.incident import IncidentStatus, IncidentType
from app.enums.permit import PermitStatus
from app.enums.truck import TruckStatus
from app.routers.files import file_response
from app.schemas.report import ExpiringPermitsReport, IncidentsByCategoryReport, IncidentsByTruckReport
from app.services.xlsx import MEDIA_TYPE

router = APIRouter(prefix="/reports", tags=["Reports"])

_DAYS = Query(None, ge=0, le=3650, description="Default: REPORT_EXPIRING_DAYS (30)")


def _xlsx(result: tuple[bytes, str]) -> Response:
    content, filename = result
    return file_response(content, MEDIA_TYPE, filename)


# ----- reports: JSON for the panel, .xlsx for Excel -----


@router.get("/expiring-permits", response_model=ExpiringPermitsReport)
async def expiring_permits(staff: StaffUserDep, service: ReportServiceDep, days: int | None = _DAYS):
    """Wygasające uprawnienia: active permits whose last day is at most `days` away, soonest first."""
    return await service.expiring_permits(days)


@router.get("/expiring-permits.xlsx", response_class=Response)
async def expiring_permits_xlsx(
    staff: StaffUserDep, service: ReportServiceDep, meta: RequestMetaDep, days: int | None = _DAYS
) -> Response:
    return _xlsx(await service.expiring_permits_xlsx(staff, meta, days))


@router.get("/incidents-by-truck", response_model=IncidentsByTruckReport)
async def incidents_by_truck(
    staff: StaffUserDep, service: ReportServiceDep, date_from: date | None = None, date_to: date | None = None
):
    """Incidents per truck and type in the period (local days, both included), most first."""
    return await service.incidents_by_truck(date_from, date_to)


@router.get("/incidents-by-truck.xlsx", response_class=Response)
async def incidents_by_truck_xlsx(
    staff: StaffUserDep,
    service: ReportServiceDep,
    meta: RequestMetaDep,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Response:
    return _xlsx(await service.incidents_by_truck_xlsx(staff, meta, date_from, date_to))


@router.get("/incidents-by-category", response_model=IncidentsByCategoryReport)
async def incidents_by_category(
    staff: StaffUserDep, service: ReportServiceDep, date_from: date | None = None, date_to: date | None = None
):
    """Incidents per category and type in the period, most first."""
    return await service.incidents_by_category(date_from, date_to)


@router.get("/incidents-by-category.xlsx", response_class=Response)
async def incidents_by_category_xlsx(
    staff: StaffUserDep,
    service: ReportServiceDep,
    meta: RequestMetaDep,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Response:
    return _xlsx(await service.incidents_by_category_xlsx(staff, meta, date_from, date_to))


@router.get("/operators/{operator_id}/history.xlsx", response_class=Response)
async def operator_history_xlsx(
    operator_id: int, staff: StaffUserDep, service: ReportServiceDep, meta: RequestMetaDep
) -> Response:
    """Historia operatora: their card, every permit and every incident they drove in."""
    return _xlsx(await service.operator_history_xlsx(staff, meta, operator_id))


# ----- the registers, with the same filters as their lists -----


@router.get("/incidents.xlsx", response_class=Response)
async def incidents_xlsx(
    staff: StaffUserDep,
    service: ReportServiceDep,
    meta: RequestMetaDep,
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
) -> Response:
    return _xlsx(
        await service.incidents_xlsx(
            staff,
            meta,
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
    )


@router.get("/permits.xlsx", response_class=Response)
async def permits_xlsx(
    staff: StaffUserDep,
    service: ReportServiceDep,
    meta: RequestMetaDep,
    query: str | None = Query(None, max_length=64),
    status: PermitStatus | None = None,
    operator_id: int | None = None,
    category_id: int | None = None,
    truck_type_id: int | None = None,
    expiring_within_days: int | None = Query(None, ge=0, le=3650),
) -> Response:
    return _xlsx(
        await service.permits_xlsx(
            staff,
            meta,
            expiring_within_days=expiring_within_days,
            query=query,
            status=status,
            operator_id=operator_id,
            category_id=category_id,
            truck_type_id=truck_type_id,
        )
    )


@router.get("/operators.xlsx", response_class=Response)
async def operators_xlsx(
    staff: StaffUserDep,
    service: ReportServiceDep,
    meta: RequestMetaDep,
    query: str | None = Query(None, max_length=64),
    employer_id: int | None = None,
    is_active: bool | None = None,
) -> Response:
    return _xlsx(await service.operators_xlsx(staff, meta, query, employer_id, is_active))


@router.get("/trucks.xlsx", response_class=Response)
async def trucks_xlsx(
    staff: StaffUserDep,
    service: ReportServiceDep,
    meta: RequestMetaDep,
    query: str | None = Query(None, max_length=64),
    status: TruckStatus | None = None,
    truck_type_id: int | None = None,
) -> Response:
    return _xlsx(await service.trucks_xlsx(staff, meta, query, status, truck_type_id))
