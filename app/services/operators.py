from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exc import BadRequestException, ObjectNotFoundException
from app.core.request_meta import RequestMeta
from app.core.security.qr_token import new_qr_token
from app.core.time import utcnow
from app.database.postgres import get_session
from app.enums.audit import AuditAction
from app.models import Operator
from app.models.dictionary import Employer, Site
from app.repositories.dictionary import DictionaryRepository
from app.repositories.operator import OperatorRepository
from app.schemas.operator import OperatorCreate, OperatorOut, OperatorUpdate
from app.schemas.pagination import Page
from app.schemas.user import UserOut
from app.services import qr
from app.services.audit import AuditService
from app.services.refs import ensure_active, only_site

MAX_CARDS = 200
_CARD_NOTE = ("Karta operatora wózka.", "Skanuj po kodzie wózka.")


class OperatorService:
    """The operators register and their QR cards."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.operators = OperatorRepository(session)
        self.sites = DictionaryRepository(session, Site)
        self.employers = DictionaryRepository(session, Employer)
        self.audit = AuditService(session)

    async def list_operators(
        self,
        page: int = 1,
        limit: int = 50,
        query: str | None = None,
        employer_id: int | None = None,
        is_active: bool | None = None,
    ) -> Page[OperatorOut]:
        rows, total = await self.operators.search(page, limit, query, employer_id, is_active)
        return Page(items=[OperatorOut.model_validate(r) for r in rows], total=total, page=page, limit=limit)

    async def get_operator(self, operator_id: int) -> OperatorOut:
        return OperatorOut.model_validate(await self.get_or_404(operator_id))

    async def create_operator(
        self, acting: UserOut, data: OperatorCreate, meta: RequestMeta | None = None
    ) -> OperatorOut:
        if data.employer_id is not None:
            await ensure_active(self.employers, data.employer_id, "Employer")
        site_id = data.site_id or await only_site(self.sites)
        if data.site_id:
            await ensure_active(self.sites, site_id, "Site")

        operator = await self.operators.create_one(
            {
                "full_name": data.full_name,
                "employer_id": data.employer_id,
                "hyster_card_number": data.hyster_card_number,
                "site_id": site_id,
                "is_active": True,
                "qr_token": new_qr_token(),
                "qr_issued_at": utcnow(),
            }
        )
        # Names are personal data: the log keeps the id, the record keeps the name.
        await self.audit.record(
            AuditAction.OPERATOR_CREATED,
            user_id=acting.id,
            resource_type="operator",
            resource_id=operator.id,
            payload={"employer_id": data.employer_id, "site_id": site_id},
            meta=meta,
        )
        await self.session.commit()
        return OperatorOut.model_validate(await self.operators.get_by_id(operator.id, fresh=True))

    async def update_operator(
        self, acting: UserOut, operator_id: int, data: OperatorUpdate, meta: RequestMeta | None = None
    ) -> OperatorOut:
        operator = await self.get_or_404(operator_id)
        changes = {}
        for key, value in data.model_dump(exclude_unset=True).items():
            # The employer and the card may be cleared; everything else ignores null.
            if value is None and key not in ("employer_id", "hyster_card_number"):
                continue
            if value != getattr(operator, key):
                changes[key] = value

        if changes.get("employer_id") is not None:
            await ensure_active(self.employers, changes["employer_id"], "Employer")
        if "site_id" in changes:
            await ensure_active(self.sites, changes["site_id"], "Site")

        if changes:
            await self.operators.update_one(operator, changes)
            payload = {k: v for k, v in changes.items() if k != "full_name"}
            if "full_name" in changes:
                payload["full_name_changed"] = True
            await self.audit.record(
                AuditAction.OPERATOR_UPDATED,
                user_id=acting.id,
                resource_type="operator",
                resource_id=operator.id,
                payload=payload,
                meta=meta,
            )
            await self.session.commit()
        return OperatorOut.model_validate(await self.operators.get_by_id(operator_id, fresh=True))

    async def reissue_qr(self, acting: UserOut, operator_id: int, meta: RequestMeta | None = None) -> OperatorOut:
        """New token: the printed card stops working at once (lost or copied card)."""
        operator = await self.get_or_404(operator_id)
        await self.operators.update_one(operator, {"qr_token": new_qr_token(), "qr_issued_at": utcnow()})
        await self.audit.record(
            AuditAction.OPERATOR_QR_REISSUED,
            user_id=acting.id,
            resource_type="operator",
            resource_id=operator.id,
            meta=meta,
        )
        await self.session.commit()
        return OperatorOut.model_validate(await self.operators.get_by_id(operator_id, fresh=True))

    async def qr_png(self, operator_id: int) -> tuple[str, bytes]:
        operator = await self.get_or_404(operator_id)
        return operator.full_name, qr.qr_png(operator.qr_token)

    async def cards_pdf(self, ids: list[int]) -> bytes:
        unique = list(dict.fromkeys(ids))
        if not unique:
            raise BadRequestException("Choose at least one operator")
        if len(unique) > MAX_CARDS:
            raise BadRequestException(f"At most {MAX_CARDS} cards at once")
        operators = await self.operators.get_by_ids(unique)
        missing = set(unique) - {o.id for o in operators}
        if missing:
            raise ObjectNotFoundException(sorted(missing)[0], "Operator")
        labels = [
            qr.Label(
                qr_data=o.qr_token,
                title=o.full_name,
                subtitle=o.employer.name if o.employer else "",
                note=_CARD_NOTE,
            )
            for o in operators
        ]
        return qr.labels_pdf(labels, title="GARAZ — karty QR operatorów")

    async def get_or_404(self, operator_id: int) -> Operator:
        operator = await self.operators.get_by_id(operator_id)
        if operator is None:
            raise ObjectNotFoundException(operator_id, "Operator")
        return operator


async def get_operator_service(session: AsyncSession = Depends(get_session)) -> OperatorService:
    return OperatorService(session)
