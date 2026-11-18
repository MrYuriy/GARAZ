from pydantic import BaseModel, ConfigDict


def clean(value: str | None) -> str | None:
    """Tidy spaces; an empty field means "none"."""
    if value is None:
        return None
    return " ".join(value.split()) or None


def required(value: str) -> str:
    value = clean(value)
    if not value:
        raise ValueError("Must not be empty")
    return value


class RefOut(BaseModel):
    """A dictionary entry (or another record) as a record pointing at it shows it."""

    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)
