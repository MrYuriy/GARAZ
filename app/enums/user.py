from app.enums.base import BaseStrEnum


class RoleEnum(BaseStrEnum):
    # Manages user accounts of every role, including other administrators.
    SUPER_ADMIN = "SUPER_ADMIN"
    # Administrator: statuses, trucks, permits, incidents; manages MANAGER accounts.
    ADMIN = "ADMIN"
    # Kierownik/Lider: the administration panel, read-only.
    MANAGER = "MANAGER"


class UserStatus(BaseStrEnum):
    ACTIVE = "ACTIVE"
    # Cannot sign in. Accounts are disabled rather than deleted: the audit log
    # keeps pointing at who did what.
    DISABLED = "DISABLED"
