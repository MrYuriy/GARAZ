from sqlalchemy import Column, Date, ForeignKey, Integer, String, Table
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin

# Which truck types a permit covers ("rodzaje wózków").
permit_truck_types = Table(
    "permit_truck_types",
    Base.metadata,
    Column("permit_id", Integer, ForeignKey("permits.id", ondelete="CASCADE"), primary_key=True),
    Column("truck_type_id", Integer, ForeignKey("truck_types.id"), primary_key=True),
)


class Permit(Base, TimestampMixin):
    """One permit ("uprawnienie") of an operator, as in the Excel register."""

    __tablename__ = "permits"

    id = Column(Integer, primary_key=True)
    operator_id = Column(Integer, ForeignKey("operators.id"), nullable=False, index=True)
    # "Nr pozwolenia". Typed by hand until the permit generator numbers them.
    number = Column(String(32), nullable=False, unique=True)
    category_id = Column(Integer, ForeignKey("permit_categories.id"), nullable=False, index=True)
    issued_on = Column(Date, nullable=False)
    # Valid through this whole day, local time.
    valid_until = Column(Date, nullable=False, index=True)
    status = Column(String(32), nullable=False, server_default="ACTIVE", index=True)  # PermitStatus

    # "Dokument-podstawa": what the permit was issued on (e.g. a UDT certificate).
    basis_name = Column(String(128), nullable=True)
    basis_number = Column(String(64), nullable=True)
    basis_date = Column(Date, nullable=True)
    # Its optional scan, in FileStorage under this key.
    document_key = Column(String(255), nullable=True)
    document_filename = Column(String(255), nullable=True)
    document_content_type = Column(String(64), nullable=True)
    document_size = Column(Integer, nullable=True)

    operator = relationship("Operator", back_populates="permits", lazy="joined")
    category = relationship("PermitCategory", lazy="joined")
    truck_types = relationship(
        "TruckType", secondary=permit_truck_types, lazy="selectin", order_by="[TruckType.sort_order, TruckType.name]"
    )
