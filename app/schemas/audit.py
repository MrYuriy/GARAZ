from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    uuid: UUID
    user_id: int | None
    action: str
    resource_type: str | None
    resource_id: str | None
    ip_address: str | None
    payload: dict | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
