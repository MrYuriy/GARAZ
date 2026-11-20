from datetime import date, timedelta
from uuid import uuid4

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.core.exc import BadRequestException, ObjectAlreadyExistsException, ObjectNotFoundException
from app.core.request_meta import RequestMeta
from app.core.time import local_today
from app.database.postgres import get_session
from app.enums.audit import AuditAction
from app.enums.permit import PermitStatus
from app.models import Permit
from app.models.dictionary import PermitCategory, TruckType
from app.repositories.dictionary import DictionaryRepository
from app.repositories.operator import OperatorRepository
from app.repositories.permit import PermitRepository
from app.schemas.pagination import Page
from app.schemas.permit import PermitCreate, PermitOut, PermitRenew, PermitUpdate
from app.schemas.user import UserOut
from app.services.audit import AuditService
from app.services.permit_card import Card, Form, cards_pdf
from app.services.refs import ensure_active
from app.services.storage import FileStorage

# What a scan may be, told by its first bytes rather than by what the browser claims.
_SIGNATURES = (
    (b"%PDF-", "application/pdf", "pdf"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
)


def _sniff(content: bytes) -> tuple[str, str] | None:
    for magic, content_type, ext in _SIGNATURES:
        if content.startswith(magic):
            return content_type, ext
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def status_for(wanted: PermitStatus, valid_until: date, today: date | None = None) -> PermitStatus:
    """What a permit's status is once the date has its say: an active permit
    past its last day is expired; a suspension stands whatever the date."""
    if wanted == PermitStatus.ACTIVE and valid_until < (today or local_today()):
        return PermitStatus.EXPIRED
    return wanted


def _next_status(current: PermitStatus, wanted: PermitStatus | None, valid_until: date) -> PermitStatus:
    """After an edit. An expired permit comes back by itself when its date moves
    forward; anything else keeps its status unless one is asked for. Lifting a
    suspension on an outdated permit lands on EXPIRED, which is the truth."""
    if wanted is None:
        wanted = PermitStatus.ACTIVE if current == PermitStatus.EXPIRED else current
    return status_for(wanted, valid_until)


def number_sequence(number: str, year: int) -> int | None:
    """The running number in "007/2026" when it is of `year`, else None."""
    head, sep, tail = number.partition("/")
    if not sep or tail != str(year) or not head.isdigit():
        return None
    return int(head)


def format_number(sequence: int, year: int) -> str:
    return f"{sequence:03d}/{year}"


def _jsonable(changes: dict) -> dict:
    return {k: v.isoformat() if isinstance(v, date) else v for k, v in changes.items()}


class PermitService:
    """The permits register ("uprawnienia"), their statuses and scanned documents."""

    def __init__(self, session: AsyncSession, storage: FileStorage | None = None) -> None:
        self.session = session
        self.permits = PermitRepository(session)
        self.operators = OperatorRepository(session)
        self.categories = DictionaryRepository(session, PermitCategory)
        self.types = DictionaryRepository(session, TruckType)
        self.audit = AuditService(session)
        self.storage = storage or FileStorage()

    async def list_permits(
        self,
        page: int = 1,
        limit: int = 50,
        query: str | None = None,
        status: PermitStatus | None = None,
        operator_id: int | None = None,
        category_id: int | None = None,
        truck_type_id: int | None = None,
        expiring_within_days: int | None = None,
    ) -> Page[PermitOut]:
        before = local_today() + timedelta(days=expiring_within_days) if expiring_within_days is not None else None
        rows, total = await self.permits.search(
            page, limit, query, status.value if status else None, operator_id, category_id, truck_type_id, before
        )
        return Page(items=[PermitOut.model_validate(r) for r in rows], total=total, page=page, limit=limit)

    async def get_permit(self, permit_id: int) -> PermitOut:
        return PermitOut.model_validate(await self._get_or_404(permit_id))

    async def create_permit(self, acting: UserOut, data: PermitCreate, meta: RequestMeta | None = None) -> PermitOut:
        if await self.operators.get_by_id(data.operator_id) is None:
            raise BadRequestException(f"Operator {data.operator_id} does not exist")
        if data.number:
            await self._ensure_number_free(data.number)
        await ensure_active(self.categories, data.category_id, "Permit category")
        truck_types = await self._truck_types(data.truck_type_ids, keep=[])

        status = status_for(PermitStatus.ACTIVE, data.valid_until)
        permit = await self._insert(
            data.number,
            data.issued_on.year,
            operator_id=data.operator_id,
            category_id=data.category_id,
            issued_on=data.issued_on,
            valid_until=data.valid_until,
            status=status.value,
            udt_number=data.udt_number,
            basis_name=data.basis_name,
            basis_number=data.basis_number,
            basis_date=data.basis_date,
            truck_types=truck_types,
        )
        await self.audit.record(
            AuditAction.PERMIT_CREATED,
            user_id=acting.id,
            resource_type="permit",
            resource_id=permit.id,
            payload=_jsonable(
                {
                    "number": permit.number,
                    "operator_id": data.operator_id,
                    "category_id": data.category_id,
                    "truck_type_ids": [t.id for t in truck_types],
                    "valid_until": data.valid_until,
                    "status": status.value,
                }
            ),
            meta=meta,
        )
        await self.session.commit()
        return await self._fresh(permit.id)

    async def update_permit(
        self, acting: UserOut, permit_id: int, data: PermitUpdate, meta: RequestMeta | None = None
    ) -> PermitOut:
        permit = await self._get_or_404(permit_id)
        _refuse_archived(permit)
        sent = data.model_dump(exclude_unset=True)
        comment = sent.pop("comment", None)
        wanted_status = sent.pop("status", None)
        type_ids = sent.pop("truck_type_ids", None)

        changes = {}
        for key, value in sent.items():
            # The basis fields may be cleared; everything else ignores null.
            if value is None and not key.startswith(("basis_", "udt_")):
                continue
            if value != getattr(permit, key):
                changes[key] = value

        await self._check_changes(permit, changes)
        if type_ids is not None:
            current = {t.id for t in permit.truck_types}
            if set(type_ids) != current:
                permit.truck_types = await self._truck_types(type_ids, keep=list(current))
                changes["truck_type_ids"] = [t.id for t in permit.truck_types]

        status = _next_status(
            PermitStatus(permit.status), wanted_status, changes.get("valid_until", permit.valid_until)
        )
        if status.value != permit.status:
            changes["status"] = status.value
        if changes:
            columns = {k: v for k, v in changes.items() if k != "truck_type_ids"}
            await self.permits.update_one(permit, columns)
            payload = _jsonable(changes)
            if comment:
                payload["comment"] = comment
            await self.audit.record(
                AuditAction.PERMIT_UPDATED,
                user_id=acting.id,
                resource_type="permit",
                resource_id=permit.id,
                payload=payload,
                meta=meta,
            )
            await self.session.commit()
        return await self._fresh(permit_id)

    async def renew_permit(
        self, acting: UserOut, permit_id: int, data: PermitRenew, meta: RequestMeta | None = None
    ) -> PermitOut:
        """A new permit with the next number; the old one is archived, unchanged otherwise."""
        old = await self._get_or_404(permit_id)
        _refuse_archived(old)
        issued_on = data.issued_on or local_today()
        if data.valid_until < issued_on:
            raise BadRequestException("valid_until must not be before issued_on")
        category_id = data.category_id or old.category_id
        if data.category_id and data.category_id != old.category_id:
            await ensure_active(self.categories, data.category_id, "Permit category")
        current = [t.id for t in old.truck_types]
        truck_types = await self._truck_types(data.truck_type_ids or current, keep=current)
        sent = data.model_dump(exclude_unset=True)

        def kept(field: str):
            return sent[field] if field in sent else getattr(old, field)

        status = status_for(PermitStatus.ACTIVE, data.valid_until)
        new = await self._insert(
            None,
            issued_on.year,
            operator_id=old.operator_id,
            category_id=category_id,
            issued_on=issued_on,
            valid_until=data.valid_until,
            status=status.value,
            udt_number=kept("udt_number"),
            basis_name=kept("basis_name"),
            basis_number=kept("basis_number"),
            basis_date=kept("basis_date"),
            truck_types=truck_types,
        )
        old.status = PermitStatus.ARCHIVED.value
        old.replaced_by_id = new.id
        await self.audit.record(
            AuditAction.PERMIT_RENEWED,
            user_id=acting.id,
            resource_type="permit",
            resource_id=new.id,
            payload=_jsonable(
                {
                    "number": new.number,
                    "replaces_id": old.id,
                    "replaces_number": old.number,
                    "operator_id": old.operator_id,
                    "valid_until": data.valid_until,
                    "status": status.value,
                }
            ),
            meta=meta,
        )
        await self.session.commit()
        return await self._fresh(new.id)

    async def next_number(self, year: int) -> str:
        """The next free "NNN/year": one past the highest of that year."""
        numbers = (await self.session.execute(select(Permit.number).where(Permit.number.like(f"%/{year}")))).scalars()
        highest = max((n for n in (number_sequence(x, year) for x in numbers) if n is not None), default=0)
        return format_number(highest + 1, year)

    async def _insert(self, number: str | None, year: int, **fields) -> Permit:
        """Add the permit, numbering it when `number` is None. Two permits numbered
        at the same moment collide on the unique number: the loser takes the next one."""
        for attempt in range(5):
            permit = Permit(number=number or await self.next_number(year), **fields)
            self.session.add(permit)
            try:
                async with self.session.begin_nested():
                    await self.session.flush()
                return permit
            except IntegrityError:
                self.session.expunge(permit)
                if number or attempt == 4:
                    raise ObjectAlreadyExistsException(permit.number, "Permit") from None
        raise AssertionError("unreachable")

    # ----- the printed card -----

    async def cards_pdf(self, permit_ids: list[int]) -> bytes:
        """The permits as form PL-FORM-QHSE-009, eight to a sheet, in the order asked."""
        ids = list(dict.fromkeys(permit_ids))
        rows = (await self.session.execute(select(Permit).where(Permit.id.in_(ids)))).unique().scalars().all()
        found = {p.id: p for p in rows}
        for permit_id in ids:
            permit = found.get(permit_id)
            if permit is None:
                raise ObjectNotFoundException(permit_id, "Permit")
            if permit.status == PermitStatus.ARCHIVED.value:
                raise BadRequestException(f"Permit {permit.number} is archived; print its renewal")
        listed = await self.types.list_entries()
        cards = []
        for permit_id in ids:
            permit = found[permit_id]
            covered = {t.id for t in permit.truck_types}
            # Every type in use, plus any switched off since that this permit still names.
            names = [(t.name, t.id in covered) for t in listed]
            names += [(t.name, True) for t in permit.truck_types if t.id not in {x.id for x in listed}]
            operator = permit.operator
            cards.append(
                Card(
                    number=permit.number,
                    issued_on=permit.issued_on,
                    valid_until=permit.valid_until,
                    full_name=operator.full_name,
                    location=operator.site.name if operator.site else "",
                    employer=operator.employer.name if operator.employer else "",
                    category=permit.category.name,
                    udt_number=permit.udt_number,
                    truck_types=names,
                )
            )
        config = settings.permits
        try:
            logo = await self.storage.read(config.PERMIT_LOGO_KEY)
        except ObjectNotFoundException:
            logo = None
        form = Form(config.PERMIT_FORM_CODE, config.PERMIT_FORM_VERSION, config.PERMIT_FORM_DATE, logo)
        return cards_pdf(cards, form)

    # ----- the scanned document -----

    async def attach_document(
        self,
        acting: UserOut,
        permit_id: int,
        filename: str | None,
        content: bytes,
        meta: RequestMeta | None = None,
    ) -> PermitOut:
        permit = await self._get_or_404(permit_id)
        _refuse_archived(permit)
        limit = settings.storage.MAX_DOCUMENT_MB * 1024 * 1024
        if not content:
            raise BadRequestException("The file is empty")
        if len(content) > limit:
            raise BadRequestException(f"The file is larger than {settings.storage.MAX_DOCUMENT_MB} MB")
        kind = _sniff(content)
        if kind is None:
            raise BadRequestException("Only PDF, JPEG, PNG or WebP files")
        content_type, ext = kind

        old_key = permit.document_key
        key = f"permits/{permit.id}/{uuid4().hex}.{ext}"
        await self.storage.save(key, content)
        try:
            await self.permits.update_one(
                permit,
                {
                    "document_key": key,
                    "document_filename": _safe_name(filename, ext),
                    "document_content_type": content_type,
                    "document_size": len(content),
                },
            )
            await self.audit.record(
                AuditAction.PERMIT_DOCUMENT_ATTACHED,
                user_id=acting.id,
                resource_type="permit",
                resource_id=permit.id,
                payload={"content_type": content_type, "size": len(content), "replaced": old_key is not None},
                meta=meta,
            )
            await self.session.commit()
        except Exception:
            await self.storage.delete(key)  # no orphan file for a change that did not happen
            raise
        if old_key:
            await self.storage.delete(old_key)
        return await self._fresh(permit_id)

    async def read_document(self, permit_id: int) -> tuple[bytes, str, str]:
        permit = await self._get_or_404(permit_id)
        if not permit.document_key:
            raise ObjectNotFoundException(None, "Document")
        content = await self.storage.read(permit.document_key)
        return (
            content,
            permit.document_content_type or "application/octet-stream",
            permit.document_filename or "dokument",
        )

    async def remove_document(self, acting: UserOut, permit_id: int, meta: RequestMeta | None = None) -> PermitOut:
        permit = await self._get_or_404(permit_id)
        _refuse_archived(permit)
        key = permit.document_key
        if key is None:
            return PermitOut.model_validate(permit)
        await self.permits.update_one(
            permit,
            {"document_key": None, "document_filename": None, "document_content_type": None, "document_size": None},
        )
        await self.audit.record(
            AuditAction.PERMIT_DOCUMENT_REMOVED,
            user_id=acting.id,
            resource_type="permit",
            resource_id=permit.id,
            meta=meta,
        )
        await self.session.commit()
        await self.storage.delete(key)
        return await self._fresh(permit_id)

    # ----- helpers -----

    async def _get_or_404(self, permit_id: int) -> Permit:
        permit = await self.permits.get_by_id(permit_id)
        if permit is None:
            raise ObjectNotFoundException(permit_id, "Permit")
        return permit

    async def _fresh(self, permit_id: int) -> PermitOut:
        return PermitOut.model_validate(await self.permits.get_by_id(permit_id, fresh=True))

    async def _check_changes(self, permit: Permit, changes: dict) -> None:
        issued_on = changes.get("issued_on", permit.issued_on)
        valid_until = changes.get("valid_until", permit.valid_until)
        if valid_until < issued_on:
            raise BadRequestException("valid_until must not be before issued_on")
        if "number" in changes and changes["number"].lower() != permit.number.lower():
            await self._ensure_number_free(changes["number"])
        if "category_id" in changes:
            await ensure_active(self.categories, changes["category_id"], "Permit category")

    async def _ensure_number_free(self, number: str) -> None:
        if await self.permits.get_by_number(number):
            raise ObjectAlreadyExistsException(number, "Permit")

    async def _truck_types(self, ids: list[int], keep: list[int]) -> list[TruckType]:
        """The chosen truck types. New ones must be switched on; ones the permit
        already had may stay even if switched off since."""
        unique = list(dict.fromkeys(ids))
        rows = (await self.session.execute(select(TruckType).where(TruckType.id.in_(unique)))).scalars().all()
        found = {t.id: t for t in rows}
        for type_id in unique:
            entry = found.get(type_id)
            if entry is None:
                raise BadRequestException(f"Truck type {type_id} does not exist")
            if not entry.is_active and type_id not in keep:
                raise BadRequestException(f"Truck type {entry.name!r} is switched off")
        return [found[i] for i in unique]


def _refuse_archived(permit: Permit) -> None:
    if permit.status == PermitStatus.ARCHIVED.value:
        raise BadRequestException("An archived permit cannot be changed; its renewal is the current one")


def _safe_name(filename: str | None, ext: str) -> str:
    """The uploaded name, kept for the download; trimmed and with the real extension."""
    stem = (filename or "dokument").replace("\\", "/").rsplit("/", 1)[-1]
    stem = stem.rsplit(".", 1)[0].strip() or "dokument"
    return f"{stem[:200]}.{ext}"


async def get_permit_service(session: AsyncSession = Depends(get_session)) -> PermitService:
    return PermitService(session)
