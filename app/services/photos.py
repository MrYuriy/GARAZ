"""Incident photos: checked, turned upright, re-encoded and thumbnailed.

Re-encoding is the point: the stored file is a JPEG we wrote, never the bytes
a phone sent, so it carries no EXIF (GPS position, device serial) and no
payload hidden behind an image header.
"""

import asyncio
import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core import settings
from app.core.exc import BadRequestException

# Well above a phone camera (~50 MP), well below what would exhaust memory.
_MAX_PIXELS = 80_000_000


@dataclass(frozen=True)
class Photo:
    full: bytes
    thumb: bytes
    width: int
    height: int


def is_image(content: bytes) -> bool:
    return (
        content.startswith(b"\xff\xd8\xff")
        or content.startswith(b"\x89PNG\r\n\x1a\n")
        or (content[:4] == b"RIFF" and content[8:12] == b"WEBP")
    )


def _encode(image: Image.Image, side: int, quality: int) -> bytes:
    copy = image.copy()
    copy.thumbnail((side, side), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    copy.save(out, "JPEG", quality=quality, optimize=True)
    return out.getvalue()


def _process(content: bytes) -> Photo:
    if not is_image(content):
        raise BadRequestException("A photo must be a JPEG, PNG or WebP image")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.width * image.height > _MAX_PIXELS:
                raise BadRequestException("The photo is too large")
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGB")
            cfg = settings.incidents
            full = _encode(image, cfg.PHOTO_MAX_SIDE, 85)
            thumb = _encode(image, cfg.THUMB_SIDE, 75)
            with Image.open(io.BytesIO(full)) as stored:
                width, height = stored.size
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise BadRequestException("The photo could not be read") from exc
    return Photo(full=full, thumb=thumb, width=width, height=height)


async def process_photo(content: bytes) -> Photo:
    """Off the event loop: decoding a 12 MP photo takes a moment."""
    return await asyncio.to_thread(_process, content)
