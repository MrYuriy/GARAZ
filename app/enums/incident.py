from app.enums.base import BaseStrEnum


class IncidentType(BaseStrEnum):
    """What kind of event is reported; picked as its own field on the form."""

    AWARIA = "AWARIA"
    USZKODZENIE = "USZKODZENIE"
    KOLIZJA = "KOLIZJA"


class IncidentStatus(BaseStrEnum):
    NEW = "NEW"  # Nowe
    IN_PROGRESS = "IN_PROGRESS"  # W trakcie
    CLOSED = "CLOSED"  # Zamknięte


class IncidentFlag(BaseStrEnum):
    """What the administrator should look at. A report is always accepted;
    these only mark it."""

    # The operator was switched off (left the company) when reporting.
    OPERATOR_INACTIVE = "OPERATOR_INACTIVE"
    # No active permit at all that day (all expired or suspended, or none).
    NO_ACTIVE_PERMIT = "NO_ACTIVE_PERMIT"
    # Active permits, but none covering this truck's type.
    TRUCK_TYPE_NOT_PERMITTED = "TRUCK_TYPE_NOT_PERMITTED"
    # Entered in the panel for a driver who is not in the register at all.
    UNREGISTERED_OPERATOR = "UNREGISTERED_OPERATOR"
    # The hour meter reads less than the last report for this truck.
    MTH_LOWER_THAN_LAST = "MTH_LOWER_THAN_LAST"
