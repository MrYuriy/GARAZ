from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, String, Text, false
from sqlalchemy.orm import relationship

from app.models.base import Base, JSONType, TimestampMixin, UTCDateTime, UUIDType


class Incident(Base, TimestampMixin):
    """An event reported from a truck's QR code: awaria, uszkodzenie or kolizja.

    Usually sent by an operator without an account (identified by their QR
    card). A signed-in user may also file one for someone: then `created_by_id`
    says who, and the driver may be a person outside the register, kept only
    by name in `operator_name`. `client_uuid` is made by the client: a report
    re-sent after a dropped connection is recognised, not filed twice.
    """

    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True)
    client_uuid = Column(UUIDType, nullable=False, unique=True)
    truck_id = Column(Integer, ForeignKey("trucks.id"), nullable=False, index=True)
    # Empty only for a driver outside the register; `operator_name` then says who.
    operator_id = Column(Integer, ForeignKey("operators.id"), nullable=True, index=True)
    operator_name = Column(String(128), nullable=True)
    incident_type = Column(String(16), nullable=False, index=True)  # IncidentType
    category_id = Column(Integer, ForeignKey("incident_categories.id"), nullable=False, index=True)
    description = Column(Text, nullable=True)
    # Motogodziny as read from the truck; entered by hand, may be missing.
    mth = Column(Numeric(10, 1), nullable=True)
    # The operator's answer to "wyłączony z eksploatacji?"; TAK stopped the truck.
    out_of_service = Column(Boolean, nullable=False, default=False, server_default=false())
    # IncidentFlag values worked out when the report arrived.
    flags = Column(JSONType, nullable=False, default=list)
    status = Column(String(16), nullable=False, server_default="NEW", index=True)  # IncidentStatus
    # When it was reported on the phone (an offline phone sends it later).
    occurred_at = Column(UTCDateTime, nullable=False, index=True)
    reporter_ip = Column(String(64), nullable=True)
    reporter_agent = Column(String(512), nullable=True)
    # The panel user who entered it; empty for a report from an operator's phone.
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    truck = relationship("Truck", lazy="joined")
    operator = relationship("Operator", lazy="joined")
    category = relationship("IncidentCategory", lazy="joined")
    created_by = relationship("User", lazy="joined")
    photos = relationship(
        "IncidentPhoto", lazy="selectin", order_by="IncidentPhoto.position", cascade="all, delete-orphan"
    )
    events = relationship("IncidentEvent", lazy="selectin", order_by="IncidentEvent.id", cascade="all, delete-orphan")


class IncidentPhoto(Base, TimestampMixin):
    """A photo of the report, stored re-encoded (no EXIF) with a thumbnail."""

    __tablename__ = "incident_photos"

    id = Column(Integer, primary_key=True)
    incident_id = Column(Integer, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    position = Column(Integer, nullable=False, default=0)
    key = Column(String(255), nullable=False)
    thumb_key = Column(String(255), nullable=False)
    size = Column(Integer, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)


class IncidentEvent(Base, TimestampMixin):
    """A step in the report's history: who moved it to which status, and why."""

    __tablename__ = "incident_events"

    id = Column(Integer, primary_key=True)
    incident_id = Column(Integer, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    # Empty for a report sent from an operator's phone.
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    from_status = Column(String(16), nullable=True)
    to_status = Column(String(16), nullable=False)
    comment = Column(String(1000), nullable=True)

    user = relationship("User", lazy="joined")
