from fastapi import APIRouter, Query

from app.dependencies import AdminUserDep, AuditServiceDep
from app.schemas.audit import AuditLogOut
from app.schemas.pagination import Page

router = APIRouter(prefix="/audit-logs", tags=["Audit"])


@router.get("", response_model=Page[AuditLogOut])
async def list_audit_logs(
    admin: AdminUserDep,
    service: AuditServiceDep,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    action: str | None = Query(None, max_length=64),
    resource_type: str | None = Query(None, max_length=64),
    resource_id: str | None = Query(None, max_length=64),
    user_id: int | None = None,
) -> Page[AuditLogOut]:
    """Who changed what, newest first; narrow by action, resource or actor."""
    return await service.search(page, limit, action, resource_type, resource_id, user_id)
