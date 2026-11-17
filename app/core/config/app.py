from pydantic import Field

from app.core.config.base import BaseConfig


class AppBaseConfig(BaseConfig):
    APP_NAME: str = Field("GARAZ", alias="APP_NAME")
    ENV: str = Field("local", alias="ENV")
    DEBUG: bool = Field(True, alias="DEBUG")
    HOST: str = Field("0.0.0.0", alias="HOST")
    PORT: int = Field(8000, alias="PORT")
    BASE_URL: str = Field("http://localhost:8000", alias="BASE_URL")
    ALLOWED_ORIGINS: list[str] = Field(default_factory=lambda: ["*"], alias="ALLOWED_ORIGINS")

    # Everything is stored in UTC; this is the zone dates are shown and
    # reported in (an event "reported at 14:05" means 14:05 on the warehouse
    # floor, not in UTC).
    TIMEZONE: str = Field("Europe/Warsaw", alias="TIMEZONE")

    # Identity of the Android build, for App Links. With these set the site
    # serves /.well-known/assetlinks.json, and Android opens our https URLs —
    # the truck QR codes — straight in the installed app instead of a browser.
    #
    # The fingerprint is the SHA-256 of the SIGNING certificate and differs
    # between a debug build and a release key. List every one, comma-separated,
    # or App Links silently stop verifying.
    ANDROID_PACKAGE_NAME: str = Field("pl.garaz.garaz_app", alias="ANDROID_PACKAGE_NAME")
    ANDROID_SHA256_FINGERPRINTS: str = Field("", alias="ANDROID_SHA256_FINGERPRINTS")

    @property
    def android_fingerprints(self) -> list[str]:
        return [f.strip().upper() for f in self.ANDROID_SHA256_FINGERPRINTS.split(",") if f.strip()]
