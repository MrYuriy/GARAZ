"""Lists administrators keep in the panel (a "słownik" each).

Every list has the same shape — a name, an order and an on/off switch — so the
code that serves them is shared. Entries are switched off, never deleted:
permits, trucks and reports will point at them, and an old report must keep
saying what it was filed under.
"""

from sqlalchemy import Boolean, Column, Integer, String, false, true

from app.models.base import Base, JSONType, TimestampMixin


class DictionaryMixin(TimestampMixin):
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False, unique=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=true())
    # Lists show in this order, then by name; lets the common ones come first.
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")


class Site(Base, DictionaryMixin):
    """A warehouse. There is one today; trucks and operators carry a site_id
    so a second one needs no migration of their data."""

    __tablename__ = "sites"


class PermitCategory(Base, DictionaryMixin):
    __tablename__ = "permit_categories"


class TruckType(Base, DictionaryMixin):
    __tablename__ = "truck_types"


class Employer(Base, DictionaryMixin):
    __tablename__ = "employers"


class IncidentCategory(Base, DictionaryMixin):
    __tablename__ = "incident_categories"

    # Which event types offer this category (IncidentType values): a collision
    # report lists only the collision categories.
    incident_types = Column(JSONType, nullable=False, default=list)
    # Pre-fills "wyłączony z eksploatacji" on the form; the operator may change it.
    default_out_of_service = Column(Boolean, nullable=False, default=False, server_default=false())
