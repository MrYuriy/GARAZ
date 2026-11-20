"""Reports ("raporty") and Excel exports of the registers.

Every Excel file that leaves the system is written to the audit log with who
took it and with which filters: the files carry personal data (RODO).
"""

from datetime import date, timedelta
from enum import Enum

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.core.exc import ObjectNotFoundException
from app.core.request_meta import RequestMeta
from app.core.time import local_today
from app.database.postgres import get_session
from app.enums.audit import AuditAction
from app.enums.incident import IncidentFlag, IncidentStatus, IncidentType
from app.enums.permit import PermitStatus
from app.enums.truck import TruckStatus
from app.models import Incident, Operator, Permit, Truck
from app.repositories.incident import IncidentRepository
from app.repositories.operator import OperatorRepository
from app.repositories.permit import PermitRepository
from app.repositories.report import ReportRepository
from app.repositories.truck import TruckRepository
from app.schemas.common import RefOut
from app.schemas.permit import PermitOut
from app.schemas.report import (
    CategoryIncidentsRow,
    ExpiringPermitsReport,
    IncidentsByCategoryReport,
    IncidentsByTruckReport,
    TruckIncidentsRow,
    TruckOfReport,
)
from app.schemas.user import UserOut
from app.services.audit import AuditService
from app.services.incidents import local_day_range, search_filters
from app.services.xlsx import Sheet, workbook

# ----- Polish labels, as the panel shows them -----

INCIDENT_TYPE = {
    IncidentType.AWARIA: "Awaria",
    IncidentType.USZKODZENIE: "Uszkodzenie",
    IncidentType.KOLIZJA: "Kolizja",
}
INCIDENT_STATUS = {
    IncidentStatus.NEW: "Nowe",
    IncidentStatus.IN_PROGRESS: "W trakcie",
    IncidentStatus.CLOSED: "Zamknięte",
}
INCIDENT_FLAG = {
    IncidentFlag.OPERATOR_INACTIVE: "Operator nieaktywny",
    IncidentFlag.NO_ACTIVE_PERMIT: "Brak ważnego uprawnienia",
    IncidentFlag.TRUCK_TYPE_NOT_PERMITTED: "Brak uprawnienia na ten typ wózka",
    IncidentFlag.UNREGISTERED_OPERATOR: "Osoba spoza rejestru operatorów",
    IncidentFlag.MTH_LOWER_THAN_LAST: "MTH niższe niż ostatnio",
}
PERMIT_STATUS = {
    PermitStatus.ACTIVE: "Aktywne",
    PermitStatus.SUSPENDED: "Zawieszone",
    PermitStatus.EXPIRED: "Wygasłe",
    PermitStatus.ARCHIVED: "Zarchiwizowane",
}
TRUCK_STATUS = {
    TruckStatus.ACTIVE: "Aktywny",
    TruckStatus.OUT_OF_SERVICE: "Wyłączony z eksploatacji",
    TruckStatus.INACTIVE: "Nieaktywny",
}


def _label(labels: dict, value: str | None) -> str | None:
    return labels.get(value, value) if value is not None else None


# ----- the columns of each sheet -----

INCIDENT_HEADERS = (
    "ID",
    "Data zdarzenia",
    "Wózek",
    "Rodzaj",
    "Kategoria",
    "Kierowca",
    "Operator z rejestru",
    "Status",
    "Wyłączony z eksploatacji",
    "MTH",
    "Uwagi",
    "Opis",
    "Zdjęcia",
    "Dodane w panelu przez",
    "Przyjęte",
)


def _incident_row(i: Incident) -> tuple:
    return (
        i.id,
        i.occurred_at,
        i.truck.number,
        _label(INCIDENT_TYPE, i.incident_type),
        i.category.name,
        i.operator.full_name if i.operator else i.operator_name,
        i.operator is not None,
        _label(INCIDENT_STATUS, i.status),
        i.out_of_service,
        i.mth,
        [_label(INCIDENT_FLAG, f) for f in i.flags or []],
        i.description,
        len(i.photos),
        i.created_by.login if i.created_by else None,
        i.created_at,
    )


PERMIT_HEADERS = (
    "Nr pozwolenia",
    "Operator",
    "Pracodawca",
    "Kategoria",
    "Rodzaje wózków",
    "Wydane",
    "Ważne do",
    "Dni do końca",
    "Status",
    "Dokument-podstawa",
    "Nr dokumentu",
    "Data dokumentu",
    "Skan",
)


def _permit_row(p: Permit, today: date) -> tuple:
    return (
        p.number,
        p.operator.full_name,
        p.operator.employer.name if p.operator.employer else None,
        p.category.name,
        [t.name for t in p.truck_types],
        p.issued_on,
        p.valid_until,
        (p.valid_until - today).days,
        _label(PERMIT_STATUS, p.status),
        p.basis_name,
        p.basis_number,
        p.basis_date,
        p.document_key is not None,
    )


OPERATOR_HEADERS = (
    "Imię i nazwisko",
    "Pracodawca",
    "Nr karty Hyster",
    "Aktywny",
    "Lokalizacja",
    "Aktywne uprawnienia",
    "Najbliższy koniec ważności",
    "Dodany",
)


def _operator_row(o: Operator) -> tuple:
    active = [p for p in o.permits if p.status == PermitStatus.ACTIVE.value]
    return (
        o.full_name,
        o.employer.name if o.employer else None,
        o.hyster_card_number,
        o.is_active,
        o.site.name,
        [p.number for p in active],
        min((p.valid_until for p in active), default=None),
        o.created_at,
    )


TRUCK_HEADERS = ("Nr wózka", "Producent", "Model", "Typ", "Status", "Lokalizacja", "Kod QR wydany", "Dodany")


def _truck_row(t: Truck) -> tuple:
    return (
        t.number,
        t.manufacturer.name if t.manufacturer else None,
        t.model.name if t.model else None,
        t.truck_type.name,
        _label(TRUCK_STATUS, t.status),
        t.site.name,
        t.qr_issued_at,
        t.created_at,
    )


def _counts_headers(first: tuple[str, ...]) -> tuple[str, ...]:
    return (*first, *INCIDENT_TYPE.values(), "Razem", "Wyłączony z eksploatacji", "Ostatnie zdarzenie")


def _counts_cells(row) -> tuple:
    return (*(row.by_type[t] for t in IncidentType), row.total, row.out_of_service, row.last_at)


def _group(rows: list, key) -> list[tuple[object, dict]]:
    """Rows per (thing, incident type) folded into one per thing, most incidents first."""
    groups: dict = {}
    for r in rows:
        g = groups.setdefault(key(r), {"by_type": dict.fromkeys(IncidentType, 0), "out_of_service": 0, "last_at": None})
        g["by_type"][IncidentType(r.incident_type)] += r.count
        g["out_of_service"] += r.out_of_service or 0
        g["last_at"] = r.last_at if g["last_at"] is None else max(g["last_at"], r.last_at)
    for g in groups.values():
        g["total"] = sum(g["by_type"].values())
    return sorted(groups.items(), key=lambda kv: (-kv[1]["total"], str(kv[0])))


def _filters_payload(filters: dict) -> dict:
    """The filters as the audit log keeps them (JSON)."""
    out = {}
    for key, value in filters.items():
        if value is None:
            continue
        out[key] = value.value if isinstance(value, Enum) else value.isoformat() if isinstance(value, date) else value
    return out


def _period_name(date_from: date | None, date_to: date | None) -> str:
    return f"{date_from or 'od-poczatku'}_{date_to or local_today()}"


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.reports = ReportRepository(session)
        self.incidents = IncidentRepository(session)
        self.permits = PermitRepository(session)
        self.operators = OperatorRepository(session)
        self.trucks = TruckRepository(session)
        self.audit = AuditService(session)

    @property
    def _max(self) -> int:
        return settings.reports.REPORT_MAX_ROWS

    async def _export(self, user: UserOut, meta: RequestMeta, report: str, filters: dict, *sheets: Sheet) -> bytes:
        content = workbook(*sheets)
        await self.audit.record(
            AuditAction.REPORT_EXPORTED,
            user_id=user.id,
            resource_type=report,
            payload=_filters_payload(filters),
            meta=meta,
        )
        await self.session.commit()
        return content

    # ----- wygasające uprawnienia -----

    async def _expiring(self, days: int | None) -> tuple[int, date, list[Permit]]:
        days = settings.reports.REPORT_EXPIRING_DAYS if days is None else days
        until = local_today() + timedelta(days=days)
        rows, _ = await self.permits.search(1, self._max, status=PermitStatus.ACTIVE.value, valid_until_before=until)
        return days, until, rows

    async def expiring_permits(self, days: int | None = None) -> ExpiringPermitsReport:
        days, until, rows = await self._expiring(days)
        return ExpiringPermitsReport(days=days, until=until, items=[PermitOut.model_validate(p) for p in rows])

    async def expiring_permits_xlsx(self, user: UserOut, meta: RequestMeta, days: int | None) -> tuple[bytes, str]:
        days, _, rows = await self._expiring(days)
        today = local_today()
        sheet = Sheet(f"Wygasające ({days} dni)", PERMIT_HEADERS, (_permit_row(p, today) for p in rows))
        content = await self._export(user, meta, "expiring-permits", {"days": days}, sheet)
        return content, f"wygasajace-uprawnienia-{today}.xlsx"

    # ----- zdarzenia wg wózków / wg kategorii -----

    async def incidents_by_truck(self, date_from: date | None, date_to: date | None) -> IncidentsByTruckReport:
        rows = await self.reports.by_truck(*local_day_range(date_from, date_to))
        grouped = _group(rows, key=lambda r: (r.number, r.id, r.status, r.truck_type))
        return IncidentsByTruckReport(
            date_from=date_from,
            date_to=date_to,
            rows=[
                TruckIncidentsRow(truck=TruckOfReport(id=k[1], number=k[0], status=k[2], truck_type=k[3]), **g)
                for k, g in grouped
            ],
        )

    async def incidents_by_category(self, date_from: date | None, date_to: date | None) -> IncidentsByCategoryReport:
        rows = await self.reports.by_category(*local_day_range(date_from, date_to))
        grouped = _group(rows, key=lambda r: (r.name, r.id))
        return IncidentsByCategoryReport(
            date_from=date_from,
            date_to=date_to,
            rows=[CategoryIncidentsRow(category=RefOut(id=k[1], name=k[0]), **g) for k, g in grouped],
        )

    async def incidents_by_truck_xlsx(
        self, user: UserOut, meta: RequestMeta, date_from: date | None, date_to: date | None
    ) -> tuple[bytes, str]:
        report = await self.incidents_by_truck(date_from, date_to)
        sheet = Sheet(
            "Zdarzenia wg wózków",
            _counts_headers(("Wózek", "Typ", "Status wózka")),
            (
                (r.truck.number, r.truck.truck_type, _label(TRUCK_STATUS, r.truck.status), *_counts_cells(r))
                for r in report.rows
            ),
        )
        filters = {"date_from": date_from, "date_to": date_to}
        content = await self._export(user, meta, "incidents-by-truck", filters, sheet)
        return content, f"zdarzenia-wg-wozkow-{_period_name(date_from, date_to)}.xlsx"

    async def incidents_by_category_xlsx(
        self, user: UserOut, meta: RequestMeta, date_from: date | None, date_to: date | None
    ) -> tuple[bytes, str]:
        report = await self.incidents_by_category(date_from, date_to)
        sheet = Sheet(
            "Zdarzenia wg kategorii",
            _counts_headers(("Kategoria",)),
            ((r.category.name, *_counts_cells(r)) for r in report.rows),
        )
        filters = {"date_from": date_from, "date_to": date_to}
        content = await self._export(user, meta, "incidents-by-category", filters, sheet)
        return content, f"zdarzenia-wg-kategorii-{_period_name(date_from, date_to)}.xlsx"

    # ----- historia operatora -----

    async def operator_history_xlsx(self, user: UserOut, meta: RequestMeta, operator_id: int) -> tuple[bytes, str]:
        operator = await self.operators.get_by_id(operator_id)
        if operator is None:
            raise ObjectNotFoundException(operator_id, "Operator")
        incidents, _ = await self.incidents.search(1, self._max, operator_id=operator_id)
        today = local_today()
        card = Sheet(
            "Operator",
            ("Pole", "Wartość"),
            [
                ("Imię i nazwisko", operator.full_name),
                ("Pracodawca", operator.employer.name if operator.employer else None),
                ("Nr karty Hyster", operator.hyster_card_number),
                ("Aktywny", operator.is_active),
                ("Lokalizacja", operator.site.name),
                ("Dodany", operator.created_at),
                ("Stan na dzień", today),
            ],
        )
        permits = Sheet("Uprawnienia", PERMIT_HEADERS, (_permit_row(p, today) for p in operator.permits))
        events = Sheet("Zdarzenia", INCIDENT_HEADERS, (_incident_row(i) for i in incidents))
        content = await self._export(
            user, meta, "operator-history", {"operator_id": operator_id}, card, permits, events
        )
        slug = "-".join(operator.full_name.lower().split()) or str(operator_id)
        return content, f"historia-operatora-{slug}-{today}.xlsx"

    # ----- the registers as Excel -----

    async def incidents_xlsx(self, user: UserOut, meta: RequestMeta, **filters) -> tuple[bytes, str]:
        rows, _ = await self.incidents.search(1, self._max, **search_filters(**dict(filters)))
        sheet = Sheet("Zdarzenia", INCIDENT_HEADERS, (_incident_row(i) for i in rows))
        content = await self._export(user, meta, "incidents", filters, sheet)
        return content, f"zdarzenia-{local_today()}.xlsx"

    async def permits_xlsx(
        self, user: UserOut, meta: RequestMeta, *, expiring_within_days: int | None = None, **filters
    ) -> tuple[bytes, str]:
        today = local_today()
        before = today + timedelta(days=expiring_within_days) if expiring_within_days is not None else None
        status = filters.get("status")
        rows, _ = await self.permits.search(
            1,
            self._max,
            filters.get("query"),
            status.value if status else None,
            filters.get("operator_id"),
            filters.get("category_id"),
            filters.get("truck_type_id"),
            before,
        )
        sheet = Sheet("Uprawnienia", PERMIT_HEADERS, (_permit_row(p, today) for p in rows))
        payload = {**filters, "expiring_within_days": expiring_within_days}
        content = await self._export(user, meta, "permits", payload, sheet)
        return content, f"uprawnienia-{today}.xlsx"

    async def operators_xlsx(
        self, user: UserOut, meta: RequestMeta, query: str | None, employer_id: int | None, is_active: bool | None
    ) -> tuple[bytes, str]:
        rows, _ = await self.operators.search(1, self._max, query, employer_id, is_active)
        sheet = Sheet("Operatorzy", OPERATOR_HEADERS, (_operator_row(o) for o in rows))
        filters = {"query": query, "employer_id": employer_id, "is_active": is_active}
        content = await self._export(user, meta, "operators", filters, sheet)
        return content, f"operatorzy-{local_today()}.xlsx"

    async def trucks_xlsx(
        self,
        user: UserOut,
        meta: RequestMeta,
        query: str | None,
        status: TruckStatus | None,
        truck_type_id: int | None,
    ) -> tuple[bytes, str]:
        rows, _ = await self.trucks.search(1, self._max, query, status.value if status else None, truck_type_id)
        sheet = Sheet("Wózki", TRUCK_HEADERS, (_truck_row(t) for t in rows))
        filters = {"query": query, "status": status, "truck_type_id": truck_type_id}
        content = await self._export(user, meta, "trucks", filters, sheet)
        return content, f"wozki-{local_today()}.xlsx"


async def get_report_service(session: AsyncSession = Depends(get_session)) -> ReportService:
    return ReportService(session)
