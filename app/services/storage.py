"""Uploaded files, addressed by key ("permits/12/3f9c….pdf").

A directory on a Docker volume for now: one server, a few thousand files.
Callers only ever see keys, so moving to S3-compatible storage is a new class
with the same three methods.
"""

import asyncio
import re
from pathlib import Path

from app.core import settings
from app.core.exc import ObjectNotFoundException

_KEY = re.compile(r"^[a-z0-9_-]+(/[a-z0-9_-]+)*\.[a-z0-9]+$")


class FileStorage:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or settings.storage.STORAGE_DIR).resolve()

    def _path(self, key: str) -> Path:
        # Keys are made by the server, never taken from a request — this only
        # makes sure a bug cannot write outside the storage directory.
        if not _KEY.match(key):
            raise ValueError(f"Bad storage key {key!r}")
        return self.root / key

    async def save(self, key: str, content: bytes) -> None:
        path = self._path(key)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_bytes(content)
            tmp.replace(path)  # never a half-written file under the real name

        await asyncio.to_thread(write)

    async def read(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise ObjectNotFoundException(None, "File")
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, missing_ok=True)


def get_file_storage() -> FileStorage:
    return FileStorage()
