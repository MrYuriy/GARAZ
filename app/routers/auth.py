from fastapi import APIRouter, Depends

from app.core.security.rate_limit import auth_rate_limit
from app.dependencies import AuthServiceDep, RequestMetaDep, SignedInUserDep
from app.schemas.auth import ChangePasswordRequest, LoginRequest, RefreshRequest, TokenPair
from app.schemas.user import UserOut

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenPair, dependencies=[Depends(auth_rate_limit)])
async def login(data: LoginRequest, service: AuthServiceDep, meta: RequestMetaDep) -> TokenPair:
    """Sign in with login (as in the WMS) + password."""
    return await service.login(data, meta)


@router.post("/refresh", response_model=TokenPair, dependencies=[Depends(auth_rate_limit)])
async def refresh(data: RefreshRequest, service: AuthServiceDep, meta: RequestMetaDep) -> TokenPair:
    """Trade a refresh token for a new pair. Each refresh token works once."""
    return await service.refresh(data.refresh_token, meta)


@router.post("/logout", status_code=204)
async def logout(data: RefreshRequest, service: AuthServiceDep) -> None:
    """End this session by retiring its refresh token."""
    await service.logout(data.refresh_token)


@router.post("/logout-all", status_code=204)
async def logout_everywhere(current_user: SignedInUserDep, service: AuthServiceDep, meta: RequestMetaDep) -> None:
    """End every session of the signed-in user — for a lost phone."""
    await service.logout_everywhere(current_user.id, meta)


@router.post("/change-password", response_model=TokenPair, dependencies=[Depends(auth_rate_limit)])
async def change_password(
    data: ChangePasswordRequest, current_user: SignedInUserDep, service: AuthServiceDep, meta: RequestMetaDep
) -> TokenPair:
    """Set a new password; every other session ends, this one gets a fresh pair.

    `current_password` may be left out only while the account must change its
    password (the user has just signed in with the starting one).
    """
    return await service.change_password(current_user.id, data, meta)


@router.get("/me", response_model=UserOut)
async def me(current_user: SignedInUserDep) -> UserOut:
    return current_user
