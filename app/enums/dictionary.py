from app.enums.base import BaseStrEnum


class DictionaryKind(BaseStrEnum):
    """The lists administrators keep in the panel. The value is the URL segment."""

    SITES = "sites"
    PERMIT_CATEGORIES = "permit-categories"
    # One list for both permits ("may operate") and the fleet ("is a").
    TRUCK_TYPES = "truck-types"
    EMPLOYERS = "employers"
    INCIDENT_CATEGORIES = "incident-categories"
