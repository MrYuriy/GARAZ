"""Checks shared by the registers that point at dictionary entries."""

from app.core.exc import BadRequestException
from app.enums.dictionary import DictionaryKind
from app.repositories.dictionary import DictionaryRepository


async def ensure_active(repo: DictionaryRepository, entry_id: int, what: str) -> None:
    """A new reference must be to an entry that exists and is switched on."""
    entry = await repo.get_by_id(entry_id)
    if entry is None:
        raise BadRequestException(f"{what} {entry_id} does not exist")
    if not entry.is_active:
        raise BadRequestException(f"{what} {entry.name!r} is switched off")


async def only_site(sites: DictionaryRepository) -> int:
    """With one active site there is nothing to choose; with more, the caller must say."""
    active = await sites.list_entries()
    if len(active) != 1:
        raise BadRequestException(
            f"site_id is required ({len(active)} active sites; manage them in {DictionaryKind.SITES.value})"
        )
    return active[0].id
