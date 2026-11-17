from sqlalchemy import Column, ForeignKey, Integer, String

from app.models.base import Base, TimestampMixin, UTCDateTime, UUIDMixin, UUIDType


class RefreshToken(Base, UUIDMixin, TimestampMixin):
    """One live (or retired) sign-in session.

    Only a hash of the token is stored. Refresh rotates: each token is good
    once, and the one that replaced it is recorded, so a replay can be told
    apart from two tabs refreshing at the same moment.
    """

    __tablename__ = "refresh_tokens"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False)
    expires_at = Column(UTCDateTime, nullable=False)
    revoked_at = Column(UTCDateTime, nullable=True)  # set on logout and on rotation
    replaced_by = Column(UUIDType, nullable=True)  # only rotation sets this
