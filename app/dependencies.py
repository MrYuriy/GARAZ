from typing import Annotated

from fastapi import Depends

from app.core.request_meta import RequestMeta, get_request_meta
from app.core.security.rbac import ADMIN_ROLES, STAFF_ROLES, require_roles
from app.schemas.user import UserOut
from app.services.audit import AuditService, get_audit_service
from app.services.auth.auth import AuthService, get_auth_service
from app.services.auth.dependencies import get_current_user, get_signed_in_user
from app.services.dictionaries import DictionaryService, get_dictionary_service
from app.services.incidents import IncidentService, get_incident_service
from app.services.operators import OperatorService, get_operator_service
from app.services.permits import PermitService, get_permit_service
from app.services.truck_catalog import TruckCatalogService, get_truck_catalog_service
from app.services.trucks import TruckService, get_truck_service
from app.services.users import UserService, get_user_service

AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
DictionaryServiceDep = Annotated[DictionaryService, Depends(get_dictionary_service)]
TruckServiceDep = Annotated[TruckService, Depends(get_truck_service)]
IncidentServiceDep = Annotated[IncidentService, Depends(get_incident_service)]
TruckCatalogServiceDep = Annotated[TruckCatalogService, Depends(get_truck_catalog_service)]
OperatorServiceDep = Annotated[OperatorService, Depends(get_operator_service)]
PermitServiceDep = Annotated[PermitService, Depends(get_permit_service)]

RequestMetaDep = Annotated[RequestMeta, Depends(get_request_meta)]

# Any signed-in, active user who does not owe a password change.
CurrentUserDep = Annotated[UserOut, Depends(get_current_user)]
# Signed in, possibly still on the starting password: only for /auth/me,
# change-password and logout-all.
SignedInUserDep = Annotated[UserOut, Depends(get_signed_in_user)]
# May look at the panel: SUPER_ADMIN, ADMIN, MANAGER.
StaffUserDep = Annotated[UserOut, Depends(require_roles(*STAFF_ROLES))]
# May change things: SUPER_ADMIN, ADMIN.
AdminUserDep = Annotated[UserOut, Depends(require_roles(*ADMIN_ROLES))]
