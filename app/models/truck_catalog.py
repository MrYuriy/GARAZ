"""Truck manufacturers and their models: the lists a truck's make is picked from.

Unlike the other dictionaries these are deleted, not switched off — but only
while no truck uses them, so the fleet never points at a name that is gone.
"""

from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class TruckManufacturer(Base, TimestampMixin):
    __tablename__ = "truck_manufacturers"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False, unique=True)

    models = relationship(
        "TruckModel",
        lazy="selectin",
        order_by="TruckModel.name",
        cascade="all, delete-orphan",
    )


class TruckModel(Base, TimestampMixin):
    __tablename__ = "truck_models"
    __table_args__ = (UniqueConstraint("manufacturer_id", "name", name="uq_truck_models_manufacturer_name"),)

    id = Column(Integer, primary_key=True)
    manufacturer_id = Column(
        Integer, ForeignKey("truck_manufacturers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(64), nullable=False)
