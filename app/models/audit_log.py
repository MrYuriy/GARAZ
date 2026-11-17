from sqlalchemy import Column, ForeignKey, Index, Integer, String

from app.models.base import Base, JSONType, TimestampMixin, UUIDMixin


class AuditLog(Base, UUIDMixin, TimestampMixin):
    """Append-only record of who changed what, and when.

    Written in the same transaction as the change it describes, so a change
    without its entry cannot exist. `user_id` is empty for actions nobody
    signed in for — an operator's report, the nightly expiry job.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_resource", "resource_type", "resource_id"),)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    action = Column(String(64), nullable=False, index=True)  # AuditAction
    resource_type = Column(String(64), nullable=True)
    resource_id = Column(String(64), nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)
    payload = Column(JSONType, nullable=True)  # what changed; never secrets
