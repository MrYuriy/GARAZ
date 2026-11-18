from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.core.security.qr_token import truck_qr_url
from app.enums.truck import TruckStatus
from app.schemas.common import RefOut
from app.schemas.common import clean as _clean
from app.schemas.common import required as _required


class TruckOut(BaseModel):
    id: int
    number: str
    manufacturer: RefOut | None
    model: RefOut | None
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
    # From /truck-manufacturers. A model alone is enough: its manufacturer is implied.
    manufacturer_id: int | None = None
    model_id: int | None = None
    truck_type_id: int
    # May be left out while there is a single site.
    site_id: int | None = None

    _number = field_validator("number")(_required)


class TruckUpdate(BaseModel):
    """Only what is sent changes; manufacturer_id and model_id may be cleared with null.
    A new manufacturer without a model_id clears the old model (it was the old maker's)."""

    number: str | None = Field(None, max_length=32)
    manufacturer_id: int | None = None
    model_id: int | None = None
    truck_type_id: int | None = None
    site_id: int | None = None
    status: TruckStatus | None = None
    # Why the status changed — e.g. "naprawa zakończona". Goes to the audit log.
    comment: str | None = Field(None, max_length=500)

    @field_validator("number")
    @classmethod
    def _number(cls, value: str | None) -> str | None:
        return _required(value) if value is not None else None

    _text = field_validator("comment")(_clean)
