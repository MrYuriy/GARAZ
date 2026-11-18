# Importing every model here registers it on Base.metadata (alembic, tests).
from app.models.audit_log import AuditLog
from app.models.auth import RefreshToken
from app.models.base import Base
from app.models.dictionary import Employer, IncidentCategory, PermitCategory, Site, TruckType
from app.models.operator import Operator
from app.models.permit import Permit, permit_truck_types
from app.models.truck import Truck
from app.models.truck_catalog import TruckManufacturer, TruckModel
from app.models.user import User

__all__ = [
    "AuditLog",
    "Base",
    "Employer",
    "IncidentCategory",
    "Operator",
    "Permit",
    "PermitCategory",
    "RefreshToken",
    "Site",
    "Truck",
    "TruckManufacturer",
    "TruckModel",
    "TruckType",
    "User",
    "permit_truck_types",
]
