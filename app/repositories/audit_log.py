from sqlalchemy import func, select

from app.models import AuditLog
from app.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=AuditLog)

    async def search(
        self,
        page: int = 1,
        limit: int = 50,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        user_id: int | None = None,
    ) -> tuple[list[AuditLog], int]:
        """Newest first, optionally narrowed to one action, resource or actor."""
        conditions = []
        if action:
            conditions.append(AuditLog.action == action)
        if resource_type:
            conditions.append(AuditLog.resource_type == resource_type)
        if resource_id:
            conditions.append(AuditLog.resource_id == resource_id)
        if user_id is not None:
            conditions.append(AuditLog.user_id == user_id)

        stmt = select(AuditLog).where(*conditions).order_by(AuditLog.created_at.desc())
        rows = (await self.session.execute(stmt.offset((page - 1) * limit).limit(limit))).scalars().all()
        count = select(func.count()).select_from(AuditLog).where(*conditions)
        total = (await self.session.execute(count)).scalar() or 0
        return list(rows), total
