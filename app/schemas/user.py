from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security.login import validate_login
from app.enums.user import RoleEnum, UserStatus


class UserOut(BaseModel):
    id: int
    login: str
    email: str | None
    full_name: str | None
    role: RoleEnum
    status: UserStatus
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


def _blank_to_none(value: str | None) -> str | None:
    # A form sends "" for an untouched field; that means "no email".
    return (value.strip() or None) if isinstance(value, str) else value


class UserCreate(BaseModel):
    login: str = Field(max_length=64)
    # A starting password from the administrator; no strength rules.
    password: str = Field(min_length=1, max_length=128)
    full_name: str | None = Field(None, max_length=255)
    email: EmailStr | None = None
    role: RoleEnum
    # The usual case: the user replaces the starting password on first sign-in.
    must_change_password: bool = True

    _check_login = field_validator("login")(validate_login)
    _email = field_validator("email", mode="before")(_blank_to_none)


class UserUpdate(BaseModel):
    """Every field optional: only what is sent changes.

    For `email`, sending it at all counts — `null` or "" removes it — because
    an empty email is a real value here, not "leave it alone".
    """

    login: str | None = Field(None, max_length=64)
    full_name: str | None = Field(None, max_length=255)
    email: EmailStr | None = None
    role: RoleEnum | None = None
    status: UserStatus | None = None
    # Set by an administrator for someone who forgot theirs; no strength rules.
    password: str | None = Field(None, min_length=1, max_length=128)
    # True: the user must pick a new password on their next sign-in.
    must_change_password: bool | None = None

    @field_validator("login")
    @classmethod
    def _check_login(cls, value: str | None) -> str | None:
        return validate_login(value) if value is not None else None

    _email = field_validator("email", mode="before")(_blank_to_none)
