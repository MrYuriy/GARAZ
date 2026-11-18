from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, true
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UTCDateTime


class Operator(Base, TimestampMixin):
    """A person who drives trucks. Has no account: they are identified by the
    QR code on their card, scanned in the app after the truck's.

    The permits ("uprawnienia") are separate rows, so a renewal or a second
    category never changes who the operator is, nor their card.
    """

    __tablename__ = "operators"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False, index=True)
    full_name = Column(String(128), nullable=False, index=True)
    employer_id = Column(Integer, ForeignKey("employers.id"), nullable=True, index=True)
    # "Nr karty Hyster Tracker": the card that starts the truck.
    hyster_card_number = Column(String(32), nullable=True, index=True)
    # Off when the person has left. Kept, because their reports and permits stay.
    is_active = Column(Boolean, nullable=False, default=True, server_default=true())
    # A raw random token (not a URL): only the app's own scanner reads it, and
    # only after a truck code. Nothing about the person can be read from it.
    qr_token = Column(String(64), nullable=False, unique=True)
    qr_issued_at = Column(UTCDateTime, nullable=False)

    site = relationship("Site", lazy="joined")
    employer = relationship("Employer", lazy="joined")
    permits = relationship("Permit", back_populates="operator", lazy="selectin", order_by="Permit.valid_until.desc()")
