from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.core.time import local_today
from app.enums.permit import PermitStatus
from app.schemas.common import RefOut, clean, required


class PermitBrief(BaseModel):
    """A permit as its operator's record lists it."""

    id: int
    number: str
    status: PermitStatus
    category: RefOut
    valid_until: date
    truck_types: list[RefOut]

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def days_left(self) -> int:
        """Days of validity left, local time: 0 on the last valid day, negative once past."""
        return (self.valid_until - local_today()).days


class OperatorRef(BaseModel):
    id: int
    full_name: str
    employer: RefOut | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class DocumentOut(BaseModel):
    filename: str
    content_type: str
    size: int


class PermitOut(PermitBrief):
    operator: OperatorRef
    issued_on: date
    basis_name: str | None
    basis_number: str | None
    basis_date: date | None
    created_at: datetime
    updated_at: datetime
    # Not sent as such; used to describe the scan.
    document_key: str | None = Field(exclude=True)
    document_filename: str | None = Field(exclude=True)
    document_content_type: str | None = Field(exclude=True)
    document_size: int | None = Field(exclude=True)

    @computed_field
    @property
    def document(self) -> DocumentOut | None:
        """The attached scan, if any; fetch it from /permits/{id}/document."""
        if not self.document_key:
            return None
        return DocumentOut(
            filename=self.document_filename or "dokument",
            content_type=self.document_content_type or "application/octet-stream",
            size=self.document_size or 0,
        )


class _BasisFields(BaseModel):
    basis_name: str | None = Field(None, max_length=128)
    basis_number: str | None = Field(None, max_length=64)
    basis_date: date | None = None

    _basis = field_validator("basis_name", "basis_number")(clean)


class PermitCreate(_BasisFields):
    operator_id: int
    number: str = Field(max_length=32)
    category_id: int
    truck_type_ids: list[int] = Field(min_length=1, max_length=50)
    issued_on: date
    valid_until: date

    _number = field_validator("number")(required)

    @model_validator(mode="after")
    def _dates(self) -> "PermitCreate":
        if self.valid_until < self.issued_on:
            raise ValueError("valid_until must not be before issued_on")
        return self


class PermitUpdate(_BasisFields):
    """Only what is sent changes; null or "" clears the basis fields.

    `status` takes ACTIVE or SUSPENDED. EXPIRED follows from the date: move
    `valid_until` forward to bring an expired permit back.
    """

    number: str | None = Field(None, max_length=32)
    category_id: int | None = None
    truck_type_ids: list[int] | None = Field(None, min_length=1, max_length=50)
    issued_on: date | None = None
    valid_until: date | None = None
    status: PermitStatus | None = None
    # Why — e.g. "zawieszone do szkolenia". Goes to the audit log.
    comment: str | None = Field(None, max_length=500)

    @field_validator("number")
    @classmethod
    def _number(cls, value: str | None) -> str | None:
        return required(value) if value is not None else None

    _comment = field_validator("comment")(clean)

    @field_validator("status")
    @classmethod
    def _settable(cls, value: PermitStatus | None) -> PermitStatus | None:
        if value == PermitStatus.EXPIRED:
            raise ValueError("EXPIRED follows from valid_until and cannot be set by hand")
        return value
