from pydantic import BaseModel, Field, field_validator

from app.core.security.login import normalize_login


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=64)
    password: str = Field(max_length=128)

    # Normalized, not validated: a malformed login is just one that does not
    # exist, and must get the same answer as a wrong password.
    _normalize = field_validator("login")(normalize_login)


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    # Not needed while the account owes a password change: the user has just
    # signed in with the starting password, and the screen asks only for a new one.
    current_password: str | None = Field(None, max_length=128)
    # No strength rules — any non-empty password.
    new_password: str = Field(min_length=1, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
