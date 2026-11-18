from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.enums.permit import PermitStatus
from app.schemas.common import RefOut, clean, required
from app.schemas.permit import PermitBrief


class OperatorOut(BaseModel):
    id: int
    full_name: str
    employer: RefOut | None
    hyster_card_number: str | None
    is_active: bool
    site: RefOut
    qr_issued_at: datetime
    created_at: datetime
    updated_at: datetime
    # Newest first.
    permits: list[PermitBrief]

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def permit_status(self) -> PermitStatus | None:
        """The best of their permits: ACTIVE if any is, then SUSPENDED, then EXPIRED; null with none."""
        statuses = {p.status for p in self.permits}
        for status in (PermitStatus.ACTIVE, PermitStatus.SUSPENDED, PermitStatus.EXPIRED):
            if status in statuses:
                return status
        return None


class OperatorCreate(BaseModel):
    full_name: str = Field(max_length=128)
    employer_id: int | None = None
    hyster_card_number: str | None = Field(None, max_length=32)
    # May be left out while there is a single site.
    site_id: int | None = None

    _name = field_validator("full_name")(required)
    _card = field_validator("hyster_card_number")(clean)


class OperatorUpdate(BaseModel):
    """Only what is sent changes; employer_id and hyster_card_number may be cleared with null."""

    full_name: str | None = Field(None, max_length=128)
    employer_id: int | None = None
    hyster_card_number: str | None = Field(None, max_length=32)
    site_id: int | None = None
    is_active: bool | None = None

    @field_validator("full_name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return required(value) if value is not None else None

    _card = field_validator("hyster_card_number")(clean)
