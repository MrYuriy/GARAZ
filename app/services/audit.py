from typing import Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_meta import RequestMeta
from app.database.postgres import get_session
from app.enums.audit import AuditAction
from app.repositories.audit_log import AuditLogRepository
from app.schemas.audit import AuditLogOut
from app.schemas.pagination import Page


class AuditService:
    """Writes and reads the audit log.

    `record` only adds the entry to the caller's session — it never commits —
    so the entry lands in the same transaction as the change it describes.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.logs = AuditLogRepository(session)

    async def record(
        self,
        action: AuditAction,
        *,
        user_id: int | None = None,
        resource_type: str | None = None,
        resource_id: Any = None,
        payload: dict | None = None,
        meta: RequestMeta | None = None,
    ) -> None:
        await self.logs.create_one(
            {
                "action": action.value,
                "user_id": user_id,
                "resource_type": resource_type,
                "resource_id": str(resource_id) if resource_id is not None else None,
                "payload": payload,
                "ip_address": meta.ip_address if meta else None,
                "user_agent": meta.user_agent if meta else None,
            }
        )

    async def search(
        self,
        page: int = 1,
        limit: int = 50,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        user_id: int | None = None,
    ) -> Page[AuditLogOut]:
        rows, total = await self.logs.search(page, limit, action, resource_type, resource_id, user_id)
        return Page(items=[AuditLogOut.model_validate(r) for r in rows], total=total, page=page, limit=limit)


async def get_audit_service(session: AsyncSession = Depends(get_session)) -> AuditService:
    return AuditService(session)
