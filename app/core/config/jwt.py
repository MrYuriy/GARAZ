from pydantic import Field

from app.core.config.base import BaseConfig

# Placeholders that must never sign a production token. Long enough (32+ bytes)
# that local runs and tests do not trip PyJWT's short-key warning.
DEV_ACCESS_SECRET = "dev-access-secret-change-me-0123456789"
DEV_REFRESH_SECRET = "dev-refresh-secret-change-me-0123456789"


class JwtConfig(BaseConfig):
    ACCESS_SECRET_KEY: str = Field(DEV_ACCESS_SECRET, alias="JWT_ACCESS_SECRET_KEY")
    REFRESH_SECRET_KEY: str = Field(DEV_REFRESH_SECRET, alias="JWT_REFRESH_SECRET_KEY")
    ALGORITHM: str = Field("HS256", alias="JWT_ALGORITHM")
    ACCESS_EXPIRE_MINUTES: int = Field(30, alias="JWT_ACCESS_EXPIRE_MINUTES")
    REFRESH_EXPIRE_DAYS: int = Field(30, alias="JWT_REFRESH_EXPIRE_DAYS")

    def weak_secrets(self) -> list[str]:
        """Names of secrets that are placeholders or too short to trust."""
        weak = []
        for name, value in (
            ("JWT_ACCESS_SECRET_KEY", self.ACCESS_SECRET_KEY),
            ("JWT_REFRESH_SECRET_KEY", self.REFRESH_SECRET_KEY),
        ):
            if value in (DEV_ACCESS_SECRET, DEV_REFRESH_SECRET) or "change-me" in value or len(value) < 32:
                weak.append(name)
        if self.ACCESS_SECRET_KEY == self.REFRESH_SECRET_KEY:
            weak.append("JWT_ACCESS_SECRET_KEY == JWT_REFRESH_SECRET_KEY")
        return weak
