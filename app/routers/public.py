"""What an operator's phone calls: no sign-in, only the printed QR codes.

Every call is rate-limited per IP and the report itself is audited with the
IP and device. A truck's code opens the form; an operator's card means
nothing without a truck's code next to it.
"""

from fastapi import APIRouter, Depends, File, Form, Path, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core import settings
from app.core.exc import BadRequestException
from app.core.security.rate_limit import RateLimiter
from app.dependencies import IncidentServiceDep, RequestMetaDep
from app.schemas.incident import IncidentSubmit, OperatorCheck, PublicIncidentOut, PublicOperatorOut, PublicTruckOut

public_rate_limit = RateLimiter(
    "public",
    settings.incidents.RATE_LIMIT_PUBLIC_ATTEMPTS,
    settings.incidents.RATE_LIMIT_PUBLIC_WINDOW_SECONDS,
)

router = APIRouter(prefix="/public", tags=["Public (operator's phone)"], dependencies=[Depends(public_rate_limit)])

_TOKEN = Path(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


@router.get("/trucks/{token}", response_model=PublicTruckOut)
async def scanned_truck(service: IncidentServiceDep, token: str = _TOKEN) -> PublicTruckOut:
    """The truck behind a sticker, with the categories the form offers. 404 for an unknown
    code, a re-issued one, or a truck out of the fleet."""
    return await service.public_truck(token)


@router.post("/operators/check", response_model=PublicOperatorOut)
async def scanned_operator(data: OperatorCheck, service: IncidentServiceDep) -> PublicOperatorOut:
    """Who the operator card belongs to ("Jan K."), so the operator sees the right card was read."""
    return await service.public_operator(data)


@router.post("/incidents", response_model=PublicIncidentOut, status_code=status.HTTP_201_CREATED)
async def report_incident(
    service: IncidentServiceDep,
    meta: RequestMetaDep,
    data: str = Form(..., description="IncidentSubmit as JSON"),
    photos: list[UploadFile] = File(...),
) -> PublicIncidentOut:
    """The report with its photos (at least one), in one multipart request.

    Sending the same `client_uuid` again returns the first report (`created: false`),
    so a phone may retry after a dropped connection without filing it twice.
    """
    try:
        report = IncidentSubmit.model_validate_json(data)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
    cap = settings.incidents.MAX_PHOTO_MB * 1024 * 1024
    if len(photos) > settings.incidents.MAX_PHOTOS:
        raise BadRequestException(f"At most {settings.incidents.MAX_PHOTOS} photos")
    contents = [await photo.read(cap + 1) for photo in photos]
    return await service.submit(report, contents, meta)
