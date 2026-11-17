from datetime import datetime

from sqlalchemy import update

from app.models import RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=RefreshToken)

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        return await self.get_one(token_hash=token_hash)

    async def revoke_all_for_user(self, user_id: int, now: datetime) -> int:
        """Retire every live token of one user: logout everywhere, a disabled
        account, a changed password, or a token that leaked."""
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        result = await self.session.execute(stmt)
        return result.rowcount or 0
