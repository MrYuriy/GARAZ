from pydantic import Field

from app.core.config.base import BaseConfig


class AuthConfig(BaseConfig):
    # The first administrator of an instance that has none.
    #
    # Accounts are created only by administrators — there is no sign-up — so a
    # fresh or emptied database has nobody who could create the first one.
    # These two give a way in. Checked on every container start rather than in
    # a migration: a migration runs once, and the case that needs this is the
    # second time a database is emptied.
    ADMIN_BOOTSTRAP_LOGIN: str = Field("", alias="ADMIN_BOOTSTRAP_LOGIN")
    ADMIN_BOOTSTRAP_PASSWORD: str = Field("", alias="ADMIN_BOOTSTRAP_PASSWORD")

    # How long after a refresh token is rotated its replay still counts as two
    # of the user's own tabs refreshing at once rather than as theft.
    REFRESH_REUSE_GRACE_SECONDS: int = 15
