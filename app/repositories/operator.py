from sqlalchemy import func, or_, select

from app.models import Operator
from app.repositories.base import BaseRepository


class OperatorRepository(BaseRepository[Operator]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=Operator)

    async def get_by_id(self, operator_id: int, fresh: bool = False) -> Operator | None:
        """`fresh` reloads it, permits included, after a commit changed them."""
        stmt = select(Operator).where(Operator.id == operator_id)
        if fresh:
            stmt = stmt.execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).unique().scalar_one_or_none()

    async def get_by_qr_token(self, token: str) -> Operator | None:
        stmt = select(Operator).where(Operator.qr_token == token)
        return (await self.session.execute(stmt)).unique().scalar_one_or_none()

    async def get_by_ids(self, ids: list[int]) -> list[Operator]:
        stmt = select(Operator).where(Operator.id.in_(ids)).order_by(Operator.full_name)
        return list((await self.session.execute(stmt)).unique().scalars().all())

    async def search(
        self,
        page: int = 1,
        limit: int = 50,
        query: str | None = None,
        employer_id: int | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[Operator], int]:
        """By name; `query` matches the name or the Hyster card number."""
        conditions = []
        if query:
            like = f"%{query}%"
            conditions.append(or_(Operator.full_name.ilike(like), Operator.hyster_card_number.ilike(like)))
        if employer_id:
            conditions.append(Operator.employer_id == employer_id)
        if is_active is not None:
            conditions.append(Operator.is_active == is_active)

        stmt = (
            select(Operator)
            .where(*conditions)
            .order_by(Operator.full_name, Operator.id)
            .offset((page - 1) * limit)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).unique().scalars().all()
        total = (
            await self.session.execute(select(func.count()).select_from(Operator).where(*conditions))
        ).scalar() or 0
        return list(rows), total
