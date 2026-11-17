# Role-based access control: require_roles() dependency factory.
from fastapi import Depends

from app.core.exc import ForbiddenException
from app.enums.user import RoleEnum
from app.schemas.user import UserOut
from app.services.auth.dependencies import get_current_user

# May change things: statuses, trucks, permits, incidents.
ADMIN_ROLES = (RoleEnum.SUPER_ADMIN, RoleEnum.ADMIN)
# May look: everyone who signs in, managers included (read-only panel).
STAFF_ROLES = (RoleEnum.SUPER_ADMIN, RoleEnum.ADMIN, RoleEnum.MANAGER)

# Which roles a role may create or edit. Nobody manages a role above their own,
# so an ADMIN cannot mint another ADMIN and quietly widen who holds the keys.
MANAGEABLE_ROLES: dict[RoleEnum, frozenset[RoleEnum]] = {
    RoleEnum.SUPER_ADMIN: frozenset(RoleEnum),
    RoleEnum.ADMIN: frozenset({RoleEnum.MANAGER}),
    RoleEnum.MANAGER: frozenset(),
}


def require_roles(*roles: RoleEnum):
    """Dependency that lets the request through only for the given roles.

    Authentication is get_current_user's job — this only checks the role on
    top of it and hands the user through.
    """

    async def _check(current_user: UserOut = Depends(get_current_user)) -> UserOut:
        if current_user.role not in roles:
            raise ForbiddenException("Insufficient role")
        return current_user

    return _check
