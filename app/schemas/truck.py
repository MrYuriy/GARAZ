from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.core.security.qr_token import truck_qr_url
from app.enums.truck import TruckStatus


def _clean(value: str | None) -> str | None:
    """Tidy spaces; an empty field means "none"."""
    if value is None:
        return None
    return " ".join(value.split()) or None


def _required(value: str) -> str:
    value = _clean(value)
    if not value:
        raise ValueError("Must not be empty")
    return value


class RefOut(BaseModel):
    """A dictionary entry as another record shows it."""

    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class TruckOut(BaseModel):
    id: int
    number: str
    manufacturer: str | None
    model: str | None
    status: TruckStatus
    site: RefOut
    truck_type: RefOut
    qr_issued_at: datetime
    created_at: datetime
    updated_at: datetime
    # Not sent as such; used to build qr_url.
    qr_token: str = Field(exclude=True)

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def qr_url(self) -> str:
        """What the sticker encodes."""
        return truck_qr_url(self.qr_token)


class TruckCreate(BaseModel):
    number: str = Field(max_length=32)
    manufacturer: str | None = Field(None, max_length=64)
    model: str | None = Field(None, max_length=64)
    truck_type_id: int
    # May be left out while there is a single site.
    site_id: int | None = None

    _number = field_validator("number")(_required)
    _text = field_validator("manufacturer", "model")(_clean)


class TruckUpdate(BaseModel):
    """Only what is sent changes; for manufacturer and model, null or "" clears them."""

    number: str | None = Field(None, max_length=32)
    manufacturer: str | None = Field(None, max_length=64)
    model: str | None = Field(None, max_length=64)
    truck_type_id: int | None = None
    site_id: int | None = None
    status: TruckStatus | None = None
    # Why the status changed — e.g. "naprawa zakończona". Goes to the audit log.
    comment: str | None = Field(None, max_length=500)

    @field_validator("number")
    @classmethod
    def _number(cls, value: str | None) -> str | None:
        return _required(value) if value is not None else None

    _text = field_validator("manufacturer", "model", "comment")(_clean)
