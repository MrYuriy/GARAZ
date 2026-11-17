from app.enums.base import BaseStrEnum


class IncidentType(BaseStrEnum):
    """What kind of event is reported; picked as its own field on the form."""

    AWARIA = "AWARIA"
    USZKODZENIE = "USZKODZENIE"
    KOLIZJA = "KOLIZJA"
