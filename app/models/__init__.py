# Importing every model here registers it on Base.metadata (alembic, tests).
from app.models.audit_log import AuditLog
from app.models.auth import RefreshToken
from app.models.base import Base
from app.models.dictionary import Employer, IncidentCategory, PermitCategory, Site, TruckType
from app.models.user import User

__all__ = [
    "AuditLog",
    "Base",
    "Employer",
    "IncidentCategory",
    "PermitCategory",
    "RefreshToken",
    "Site",
    "TruckType",
    "User",
]
