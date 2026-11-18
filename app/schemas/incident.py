from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.enums.incident import IncidentFlag, IncidentStatus, IncidentType
from app.enums.truck import TruckStatus
from app.schemas.common import RefOut, clean

# ----- public: the operator's phone, no sign-in -----


class PublicCategory(BaseModel):
    id: int
    name: str
    incident_types: list[IncidentType]
    # Pre-fills "wyłączony z eksploatacji"; the operator may change it.
    default_out_of_service: bool


class PublicTruckOut(BaseModel):
    """What the phone shows after scanning a truck's sticker."""

    number: str
    truck_type: str
    make: str | None
    status: TruckStatus
    # The latest hour meter reported for it: the form warns below this.
    last_mth: float | None
    categories: list[PublicCategory]


class OperatorCheck(BaseModel):
    truck_token: str = Field(min_length=8, max_length=64)
    operator_token: str = Field(min_length=8, max_length=64)


class PublicOperatorOut(BaseModel):
    # "Jan K.": enough for the operator to see the right card was read.
    display_name: str


class IncidentSubmit(OperatorCheck):
    """The report itself; sent as the `data` field next to the photos."""

    # Made by the phone. Re-sending the same report returns the first one.
    client_uuid: UUID
    incident_type: IncidentType
    category_id: int
    description: str | None = Field(None, max_length=2000)
    mth: Decimal | None = Field(None, ge=0, le=Decimal("999999.9"), decimal_places=1)
    out_of_service: bool = False
    # When the operator pressed "send" (an offline phone sends it later).
    reported_at: datetime | None = None

    _text = field_validator("description")(clean)


class PublicIncidentOut(BaseModel):
    id: int
    # False when this was a repeat of a report already received.
    created: bool
    truck_out_of_service: bool


# ----- the administration panel -----


class StaffTruckOut(PublicTruckOut):
    """The truck picked (or scanned) for a report entered in the panel."""

    id: int


class StaffIncidentCreate(BaseModel):
    """A report entered by a signed-in user for someone else; the `data` field next to the photos.

    The driver is either a registered operator (`operator_id`) or, for a person
    outside the register, only a name (`operator_name`) — exactly one of them.
    """

    client_uuid: UUID
    truck_id: int
    operator_id: int | None = None
    operator_name: str | None = Field(None, max_length=128)
    incident_type: IncidentType
    category_id: int
    description: str | None = Field(None, max_length=2000)
    mth: Decimal | None = Field(None, ge=0, le=Decimal("999999.9"), decimal_places=1)
    out_of_service: bool = False
    # When it happened; entered later than it happened, so it may be days back.
    occurred_at: datetime | None = None

    _text = field_validator("description", "operator_name")(clean)

    @model_validator(mode="after")
    def _one_driver(self) -> "StaffIncidentCreate":
        if (self.operator_id is None) == (self.operator_name is None):
            raise ValueError("Give either operator_id or operator_name")
        return self


class TruckRef(BaseModel):
    id: int
    number: str
    status: TruckStatus

    model_config = ConfigDict(from_attributes=True)


class OperatorRef(BaseModel):
    id: int
    full_name: str

    model_config = ConfigDict(from_attributes=True)


class PhotoOut(BaseModel):
    id: int
    width: int
    height: int
    size: int

    model_config = ConfigDict(from_attributes=True)


class UserRef(BaseModel):
    id: int
    login: str
    full_name: str | None

    model_config = ConfigDict(from_attributes=True)


class IncidentEventOut(BaseModel):
    id: int
    created_at: datetime
    user: UserRef | None
    from_status: IncidentStatus | None
    to_status: IncidentStatus
    comment: str | None

    model_config = ConfigDict(from_attributes=True)


class IncidentBrief(BaseModel):
    id: int
    occurred_at: datetime
    created_at: datetime
    incident_type: IncidentType
    category: RefOut
    truck: TruckRef
    # Empty for a driver outside the register: `operator_name` then.
    operator: OperatorRef | None
    operator_name: str | None
    # Who entered it in the panel; empty for a report from an operator's phone.
    created_by: UserRef | None
    status: IncidentStatus
    flags: list[IncidentFlag]
    out_of_service: bool
    mth: float | None
    photos: list[PhotoOut]

    model_config = ConfigDict(from_attributes=True)


class IncidentOut(IncidentBrief):
    description: str | None
    events: list[IncidentEventOut]


class IncidentUpdate(BaseModel):
    """A status change, a comment, or both. Each one is a line in the history."""

    status: IncidentStatus | None = None
    comment: str | None = Field(None, max_length=1000)

    _comment = field_validator("comment")(clean)
