from urllib.parse import quote

from fastapi import Response


def file_response(content: bytes, media_type: str, filename: str, inline: bool = False) -> Response:
    """Bytes as a file. `inline` lets a browser show it (a scan) instead of saving it."""
    disposition = "inline" if inline else "attachment"
    return Response(
        content,
        media_type=media_type,
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(filename)}",
            # Uploaded content is never run as a page, whatever it claims to be.
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
