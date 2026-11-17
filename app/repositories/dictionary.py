from sqlalchemy import func, select

from app.models.dictionary import DictionaryMixin
from app.repositories.base import BaseRepository


class DictionaryRepository(BaseRepository):
    """Any one of the dictionary tables; the model is chosen by the service."""

    async def list_entries(self, include_inactive: bool = False) -> list[DictionaryMixin]:
        query = select(self.model).order_by(self.model.sort_order, self.model.name)
        if not include_inactive:
            query = query.where(self.model.is_active.is_(True))
        return list((await self.session.execute(query)).scalars().all())

    async def get_by_id(self, entry_id: int) -> DictionaryMixin | None:
        return await self.session.get(self.model, entry_id)

    async def get_by_name(self, name: str) -> DictionaryMixin | None:
        """Case-insensitive: "Bateria" and "bateria" are one entry to a person."""
        query = select(self.model).where(func.lower(self.model.name) == name.lower())
        return (await self.session.execute(query)).scalar_one_or_none()
