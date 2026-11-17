from sqlalchemy import func, or_, select

from app.core.security.login import normalize_login
from app.models import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=User)

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.get_one(id=user_id)

    async def get_by_login(self, login: str) -> User | None:
        return await self.get_one(login=normalize_login(login))

    async def any_with_role(self, roles: tuple[str, ...]) -> bool:
        stmt = select(User.id).where(User.role.in_(roles)).limit(1)
        return (await self.session.execute(stmt)).first() is not None

    async def search(
        self,
        page: int = 1,
        limit: int = 20,
        query: str | None = None,
        role: str | None = None,
        status: str | None = None,
    ) -> tuple[list[User], int]:
        """Paginated listing for the panel, newest first; `query` matches login, name or email."""
        conditions = []
        if query:
            like = f"%{query}%"
            conditions.append(or_(User.login.ilike(like), User.full_name.ilike(like), User.email.ilike(like)))
        if role:
            conditions.append(User.role == role)
        if status:
            conditions.append(User.status == status)

        stmt = select(User).where(*conditions).order_by(User.created_at.desc(), User.id.desc())
        rows = (await self.session.execute(stmt.offset((page - 1) * limit).limit(limit))).scalars().all()
        total = (await self.session.execute(select(func.count()).select_from(User).where(*conditions))).scalar() or 0
        return list(rows), total
