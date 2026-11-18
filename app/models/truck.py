from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UTCDateTime


class Truck(Base, TimestampMixin):
    """A forklift in the fleet ("Rejestr wózków").

    The QR sticker on it carries only `qr_token`. Re-issuing the code replaces
    the token, so a lost or copied sticker stops working at once.
    """

    __tablename__ = "trucks"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False, index=True)
    # The fleet number painted on the truck; what people call it by.
    number = Column(String(32), nullable=False, unique=True)
    # Picked from the manufacturers list; the model, when set, is one of that manufacturer's.
    manufacturer_id = Column(Integer, ForeignKey("truck_manufacturers.id"), nullable=True, index=True)
    model_id = Column(Integer, ForeignKey("truck_models.id"), nullable=True, index=True)
    truck_type_id = Column(Integer, ForeignKey("truck_types.id"), nullable=False, index=True)
    status = Column(String(32), nullable=False, server_default="ACTIVE", index=True)  # TruckStatus
    # Kept in clear: the sticker must be reprintable at any time, and the token
    # is on the truck for anyone to see anyway. It only identifies, never authorises.
    qr_token = Column(String(64), nullable=False, unique=True)
    qr_issued_at = Column(UTCDateTime, nullable=False)

    site = relationship("Site", lazy="joined")
    truck_type = relationship("TruckType", lazy="joined")
    manufacturer = relationship("TruckManufacturer", lazy="joined", innerjoin=False)
    model = relationship("TruckModel", lazy="joined", innerjoin=False)
