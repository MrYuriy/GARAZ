from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.enums.incident import IncidentType


def _clean_name(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    if not value:
        raise ValueError("Name must not be empty")
    return value


class DictionaryEntryOut(BaseModel):
    id: int
    name: str
    is_active: bool
    sort_order: int
    # Only incident categories have these; null for every other list.
    incident_types: list[IncidentType] | None = None
    default_out_of_service: bool | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DictionaryEntryCreate(BaseModel):
    name: str = Field(max_length=128)
    sort_order: int = Field(0, ge=0, le=100_000)
    # Incident categories only: required there, refused elsewhere.
    incident_types: list[IncidentType] | None = None
    default_out_of_service: bool | None = None

    _name = field_validator("name")(_clean_name)


class DictionaryEntryUpdate(BaseModel):
    """Only what is sent changes. Entries are switched off (`is_active`), never deleted."""

    name: str | None = Field(None, max_length=128)
    sort_order: int | None = Field(None, ge=0, le=100_000)
    is_active: bool | None = None
    incident_types: list[IncidentType] | None = None
    default_out_of_service: bool | None = None

    _name = field_validator("name")(_clean_name)
