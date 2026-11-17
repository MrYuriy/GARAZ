from sqlalchemy import Boolean, Column, Integer, String, false

from app.models.base import Base, TimestampMixin, UTCDateTime


class User(Base, TimestampMixin):
    """Someone who signs in to the panel: an administrator or a manager.

    Signs in with a login — the same one they have in the WMS, so there is one
    name to remember. The email is only where notifications go, and is optional.

    Operators are not users — they never sign in, and are identified by the QR
    code on their badge. They live in their own register.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    login = Column(String(64), unique=True, index=True, nullable=False)  # stored lowercased
    email = Column(String(255), nullable=True)  # notifications only, not an identity
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(String(32), nullable=False, index=True)  # RoleEnum
    status = Column(String(32), nullable=False, server_default="ACTIVE")  # UserStatus
    # Set by an administrator (by default on a new account); cleared when the
    # user sets their own password. Until then only /auth/me, change-password
    # and logout answer.
    must_change_password = Column(Boolean, nullable=False, default=False, server_default=false())
    last_login_at = Column(UTCDateTime, nullable=True)
