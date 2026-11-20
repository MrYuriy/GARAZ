from app.enums.base import BaseStrEnum


class PermitStatus(BaseStrEnum):
    # "Aktywne": valid and in force.
    ACTIVE = "ACTIVE"
    # "Zawieszone": withdrawn by an administrator for now. Only they lift it,
    # and the daily expiry leaves it alone — a manual decision outranks the date.
    SUSPENDED = "SUSPENDED"
    # "Wygasłe": past its valid-until date. Set by the system, never by hand;
    # moving the date forward makes the permit active again.
    EXPIRED = "EXPIRED"
    # "Zarchiwizowane": replaced by a renewal (a new permit with a new number).
    # Kept as it was, read-only; `replaced_by_id` points at its successor.
    ARCHIVED = "ARCHIVED"
