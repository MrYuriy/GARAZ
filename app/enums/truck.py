from app.enums.base import BaseStrEnum


class TruckStatus(BaseStrEnum):
    # In the fleet and working.
    ACTIVE = "ACTIVE"
    # "Wyłączony z eksploatacji": stopped after an incident (or by hand), and
    # only an administrator puts it back to work.
    OUT_OF_SERVICE = "OUT_OF_SERVICE"
    # "Nieaktywny": no longer in the fleet (returned, scrapped). Kept for history.
    INACTIVE = "INACTIVE"
