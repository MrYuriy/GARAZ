import hashlib
import logging
from datetime import timedelta

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.core.exc import BadRequestException, RateLimitedException, UnauthorizedException
from app.core.request_meta import RequestMeta
from app.core.security.password import hash_password, verify_password
from app.core.security.rate_limit import login_locked, record_login_failure
from app.core.security.tokens import create_access_token, create_refresh_token, decode_token
from app.core.time import utcnow
from app.database.postgres import get_session
from app.enums.audit import AuditAction
from app.enums.auth import TokenType
from app.enums.user import UserStatus
from app.models import RefreshToken
from app.repositories.auth import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.schemas.auth import ChangePasswordRequest, LoginRequest, TokenPair
from app.services.audit import AuditService

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "Invalid login or password"


def _fingerprint(token: str) -> str:
    """What is stored instead of the token itself.

    Plain SHA-256 is right here, unlike for passwords: the token already has
    full entropy, and it must be looked up by value on every refresh.
    """
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    """Sign-in, rotating refresh and sign-out for panel users.

    There is no sign-up: accounts are created by administrators.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)
        self.audit = AuditService(session)

    async def login(self, data: LoginRequest, meta: RequestMeta | None = None) -> TokenPair:
        """One generic 401 for an unknown login and a wrong password, so the
        response never reveals whether an account exists."""
        login = data.login
        if await login_locked(login):
            raise RateLimitedException(settings.rate_limit.RATE_LIMIT_LOGIN_PER_ACCOUNT_WINDOW_SECONDS)

        user = await self.users.get_by_login(login)
        if not user or not verify_password(data.password, user.hashed_password):
            await record_login_failure(login)
            raise UnauthorizedException(INVALID_CREDENTIALS)
        # Checked only after the password, so a disabled account is not
        # confirmed to exist to someone who does not know its password.
        if user.status != UserStatus.ACTIVE:
            raise UnauthorizedException("Account is disabled")

        user.last_login_at = utcnow()
        tokens, _ = await self._issue_tokens(user.id)
        await self.audit.record(AuditAction.AUTH_LOGIN, user_id=user.id, meta=meta)
        await self.session.commit()
        return tokens

    async def refresh(self, refresh_token: str, meta: RequestMeta | None = None) -> TokenPair:
        """Exchange a refresh token for a new pair, retiring the old one.

        A valid signature is not enough: the token must still be live in the
        database, which is what makes logout and revocation real.
        """
        payload = decode_token(refresh_token, settings.jwt.REFRESH_SECRET_KEY, TokenType.REFRESH)
        stored = await self.refresh_tokens.get_by_hash(_fingerprint(refresh_token))
        if not stored:
            raise UnauthorizedException("Refresh token is not recognised")

        now = utcnow()
        if stored.revoked_at is not None:
            if stored.replaced_by is None:
                # Retired by logout, logout-everywhere, a password change or a
                # disabled account — dead the instant it is. Not theft: after
                # "sign out everywhere" every other device still holds its token
                # and will innocently try it, and treating that as a leak would
                # end the session the user just kept.
                raise UnauthorizedException("Refresh token has been revoked")
            grace = timedelta(seconds=settings.auth.REFRESH_REUSE_GRACE_SECONDS)
            if now - stored.revoked_at > grace:
                # Only rotation sets replaced_by, so this token was already
                # traded for a new one. A replay long after that means it
                # leaked, and which copy is the thief's is unknowable — so end
                # every session.
                logger.warning("Reuse of a revoked refresh token for user %s", stored.user_id)
                await self.refresh_tokens.revoke_all_for_user(stored.user_id, now)
                await self.audit.record(
                    AuditAction.AUTH_TOKEN_REUSE,
                    user_id=stored.user_id,
                    resource_type="user",
                    resource_id=stored.user_id,
                    meta=meta,
                )
                await self.session.commit()
                raise UnauthorizedException("Refresh token has been revoked")
            # Inside the window it is two of the user's own tabs refreshing at
            # the same moment, which must not sign them out.

        if stored.expires_at <= now:
            raise UnauthorizedException("Refresh token has expired")

        user = await self.users.get_by_id(int(payload["sub"]))
        if not user or user.status != UserStatus.ACTIVE:
            raise UnauthorizedException("Account is not available")

        tokens, issued = await self._issue_tokens(user.id)
        if stored.revoked_at is None:
            stored.revoked_at = now
            stored.replaced_by = issued.uuid
        await self.session.commit()
        return tokens

    async def logout(self, refresh_token: str) -> None:
        """Retire one session. Unknown or already-dead tokens pass quietly:
        the caller wanted them gone, and they are."""
        stored = await self.refresh_tokens.get_by_hash(_fingerprint(refresh_token))
        if stored and stored.revoked_at is None:
            stored.revoked_at = utcnow()
            await self.session.commit()

    async def logout_everywhere(self, user_id: int, meta: RequestMeta | None = None) -> int:
        """Retire every session of a user; returns how many were live."""
        count = await self.refresh_tokens.revoke_all_for_user(user_id, utcnow())
        await self.audit.record(AuditAction.AUTH_LOGOUT_ALL, user_id=user_id, meta=meta)
        await self.session.commit()
        return count

    async def change_password(
        self, user_id: int, data: ChangePasswordRequest, meta: RequestMeta | None = None
    ) -> TokenPair:
        """Set a new password and end every other session.

        A password is changed because it may have leaked, so whatever signed in
        with the old one is signed out. The caller gets a fresh pair and stays in.
        """
        user = await self.users.get_by_id(user_id)
        if not user:
            raise UnauthorizedException("Current password is incorrect")
        # A forced change follows a sign-in with the starting password, so it
        # is not asked again; any other change must prove the current one.
        if not user.must_change_password and not verify_password(data.current_password or "", user.hashed_password):
            raise UnauthorizedException("Current password is incorrect")
        # Keeping the old password would make a forced change a no-op.
        if verify_password(data.new_password, user.hashed_password):
            raise BadRequestException("The new password must differ from the current one")

        user.hashed_password = hash_password(data.new_password)
        user.must_change_password = False
        await self.refresh_tokens.revoke_all_for_user(user.id, utcnow())
        tokens, _ = await self._issue_tokens(user.id)
        await self.audit.record(AuditAction.AUTH_PASSWORD_CHANGED, user_id=user.id, meta=meta)
        await self.session.commit()
        return tokens

    async def _issue_tokens(self, user_id: int) -> tuple[TokenPair, RefreshToken]:
        refresh_token = create_refresh_token(user_id)
        row = await self.refresh_tokens.create_one(
            {
                "user_id": user_id,
                "token_hash": _fingerprint(refresh_token),
                "expires_at": utcnow() + timedelta(days=settings.jwt.REFRESH_EXPIRE_DAYS),
            }
        )
        return TokenPair(access_token=create_access_token(user_id), refresh_token=refresh_token), row


async def get_auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    return AuthService(session)
