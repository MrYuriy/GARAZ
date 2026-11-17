from fastapi import APIRouter, Query, status

from app.dependencies import AdminUserDep, RequestMetaDep, UserServiceDep
from app.enums.user import RoleEnum, UserStatus
from app.schemas.pagination import Page
from app.schemas.user import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=Page[UserOut])
async def list_users(
    admin: AdminUserDep,
    service: UserServiceDep,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    query: str | None = Query(None, max_length=128),
    role: RoleEnum | None = None,
    status: UserStatus | None = None,
) -> Page[UserOut]:
    """Panel accounts, newest first; `query` matches login, name or email."""
    return await service.list_users(page, limit, query, role, status)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: int, admin: AdminUserDep, service: UserServiceDep) -> UserOut:
    return await service.get_user(user_id)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, admin: AdminUserDep, service: UserServiceDep, meta: RequestMetaDep) -> UserOut:
    """Create an account. An ADMIN may create managers; only a SUPER_ADMIN may create administrators."""
    return await service.create_user(admin, data, meta)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int, data: UserUpdate, admin: AdminUserDep, service: UserServiceDep, meta: RequestMetaDep
) -> UserOut:
    """Change name, role, status or password. Disabling or resetting a password signs the user out everywhere."""
    return await service.update_user(admin, user_id, data, meta)
