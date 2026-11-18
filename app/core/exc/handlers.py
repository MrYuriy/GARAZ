from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exc.base import (
    BadRequestException,
    ForbiddenException,
    InUseException,
    ObjectAlreadyExistsException,
    ObjectNotFoundException,
    RateLimitedException,
    ServiceUnavailableException,
    UnauthorizedException,
)

# Exception type -> HTTP status. Every one carries a `.message`.
_STATUS = {
    ObjectNotFoundException: 404,
    ObjectAlreadyExistsException: 409,
    BadRequestException: 400,
    UnauthorizedException: 401,
    ForbiddenException: 403,
    ServiceUnavailableException: 503,
}


async def _handle(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=_STATUS[type(exc)], content={"detail": exc.message})  # type: ignore[attr-defined]


async def _handle_rate_limited(_: Request, exc: RateLimitedException) -> JSONResponse:
    # Retry-After tells a well-behaved client exactly how long to back off.
    return JSONResponse(
        status_code=429,
        content={"detail": exc.message},
        headers={"Retry-After": str(exc.retry_after_seconds)},
    )


async def _handle_in_use(_: Request, exc: InUseException) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": exc.message, "trucks": exc.trucks})


def register_handlers(app: FastAPI) -> None:
    for exc_type in _STATUS:
        app.add_exception_handler(exc_type, _handle)
    app.add_exception_handler(RateLimitedException, _handle_rate_limited)
    app.add_exception_handler(InUseException, _handle_in_use)
