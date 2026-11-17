from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exc import BadRequestException, ForbiddenException, ObjectAlreadyExistsException, ObjectNotFoundException
from app.core.request_meta import RequestMeta
from app.core.security.password import hash_password
from app.core.security.rbac import MANAGEABLE_ROLES
from app.core.time import utcnow
from app.database.postgres import get_session
from app.enums.audit import AuditAction
from app.enums.user import RoleEnum, UserStatus
from app.models import User
from app.repositories.auth import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.schemas.pagination import Page
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services.audit import AuditService


class UserService:
    """Panel accounts, managed by administrators.

    Guardrails: nobody manages a role above what MANAGEABLE_ROLES gives them,
    nobody edits their own account here (that would let an admin lift their
    own role or lock themselves out), and accounts are disabled, never deleted.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)
        self.audit = AuditService(session)

    async def list_users(
        self,
        page: int = 1,
        limit: int = 20,
        query: str | None = None,
        role: RoleEnum | None = None,
        status: UserStatus | None = None,
    ) -> Page[UserOut]:
        rows, total = await self.users.search(page, limit, query, role, status)
        return Page(items=[UserOut.model_validate(r) for r in rows], total=total, page=page, limit=limit)

    async def get_user(self, user_id: int) -> UserOut:
        return UserOut.model_validate(await self._get_or_404(user_id))

    async def create_user(self, acting: UserOut, data: UserCreate, meta: RequestMeta | None = None) -> UserOut:
        self._ensure_may_manage(acting, data.role)
        await self._ensure_login_free(data.login)

        user = await self.users.create_one(
            {
                "login": data.login,
                "email": str(data.email) if data.email else None,
                "hashed_password": hash_password(data.password),
                "full_name": data.full_name,
                "role": data.role.value,
                "status": UserStatus.ACTIVE.value,
                "must_change_password": data.must_change_password,
            }
        )
        await self.audit.record(
            AuditAction.USER_CREATED,
            user_id=acting.id,
            resource_type="user",
            resource_id=user.id,
            payload={"login": data.login, "role": data.role.value, "must_change_password": data.must_change_password},
            meta=meta,
        )
        await self.session.commit()
        return UserOut.model_validate(user)

    async def update_user(
        self, acting: UserOut, user_id: int, data: UserUpdate, meta: RequestMeta | None = None
    ) -> UserOut:
        if acting.id == user_id:
            raise BadRequestException("Use your own account settings, not user management")
        user = await self._get_or_404(user_id)
        self._ensure_may_manage(acting, RoleEnum(user.role))
        if data.role is not None:
            self._ensure_may_manage(acting, data.role)

        changes = self._changes(user, data)
        if "login" in changes:
            await self._ensure_login_free(changes["login"])
        for key, value in changes.items():
            setattr(user, key, value)
        if data.password is not None:
            user.hashed_password = hash_password(data.password)

        # A reset password or a disabled account must end the sessions it had:
        # that is usually the very reason for the change.
        if data.password is not None or changes.get("status") == UserStatus.DISABLED.value:
            await self.refresh_tokens.revoke_all_for_user(user.id, utcnow())

        if changes or data.password is not None:
            audited = dict(changes)
            if data.password is not None:
                audited["password"] = "reset"  # the fact, never the value
            await self.audit.record(
                AuditAction.USER_UPDATED,
                user_id=acting.id,
                resource_type="user",
                resource_id=user.id,
                payload=audited,
                meta=meta,
            )
            await self.session.flush()
            await self.session.refresh(user)
            await self.session.commit()
        return UserOut.model_validate(user)

    @staticmethod
    def _changes(user: User, data: UserUpdate) -> dict:
        """The plain fields that were sent and actually differ (password aside)."""
        wanted = {
            "login": data.login,
            "full_name": data.full_name,
            "role": data.role.value if data.role is not None else None,
            "status": data.status.value if data.status is not None else None,
            "must_change_password": data.must_change_password,
        }
        changes = {key: value for key, value in wanted.items() if value is not None and value != getattr(user, key)}
        # Email may be cleared, so for it "sent" matters, not "not None".
        if "email" in data.model_fields_set:
            email = str(data.email) if data.email else None
            if email != user.email:
                changes["email"] = email
        return changes

    async def _ensure_login_free(self, login: str) -> None:
        if await self.users.get_by_login(login):
            raise ObjectAlreadyExistsException(login, "User")

    async def _get_or_404(self, user_id: int) -> User:
        user = await self.users.get_by_id(user_id)
        if not user:
            raise ObjectNotFoundException(user_id, "User")
        return user

    @staticmethod
    def _ensure_may_manage(acting: UserOut, role: RoleEnum) -> None:
        if role not in MANAGEABLE_ROLES[acting.role]:
            raise ForbiddenException(f"A {acting.role.value} cannot manage {role.value} accounts")


async def get_user_service(session: AsyncSession = Depends(get_session)) -> UserService:
    return UserService(session)
