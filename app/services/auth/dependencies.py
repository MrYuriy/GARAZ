from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.core.exc import ForbiddenException, UnauthorizedException
from app.core.security.tokens import decode_token
from app.database.postgres import get_session
from app.enums.auth import TokenType
from app.enums.user import UserStatus
from app.repositories.user import UserRepository
from app.schemas.user import UserOut

_bearer = HTTPBearer(auto_error=False)


async def get_signed_in_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    """The signed-in user, re-read from the database on every request.

    Re-reading is what makes disabling an account take effect at once, instead
    of when its access token happens to expire.
    """
    if credentials is None:
        raise UnauthorizedException("Missing bearer token")
    payload = decode_token(credentials.credentials, settings.jwt.ACCESS_SECRET_KEY, TokenType.ACCESS)
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise UnauthorizedException("Invalid token") from None
    user = await UserRepository(session).get_by_id(user_id)
    if not user:
        raise UnauthorizedException("User not found")
    if user.status != UserStatus.ACTIVE:
        raise UnauthorizedException("Account is disabled")
    return UserOut.model_validate(user)


PASSWORD_CHANGE_REQUIRED = "Password change required"


async def get_current_user(user: UserOut = Depends(get_signed_in_user)) -> UserOut:
    """A signed-in user who does not owe a password change.

    Everything except /auth/me, /auth/change-password and logout uses this, so
    the starting password an administrator handed out opens nothing but the
    screen that replaces it.
    """
    if user.must_change_password:
        raise ForbiddenException(PASSWORD_CHANGE_REQUIRED)
    return user
