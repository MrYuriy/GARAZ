"""incidents, their photos and status history

Revision ID: 00007
Revises: 00006
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "00007"
down_revision = "00006"
branch_labels = None
depends_on = None

_TS = sa.DateTime(timezone=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_uuid", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("truck_id", sa.Integer(), sa.ForeignKey("trucks.id"), nullable=False),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("operators.id"), nullable=False),
        sa.Column("incident_type", sa.String(16), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("incident_categories.id"), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("mth", sa.Numeric(10, 1), nullable=True),
        sa.Column("out_of_service", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("flags", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), server_default="NEW", nullable=False),
        sa.Column("occurred_at", _TS, nullable=False),
        sa.Column("reporter_ip", sa.String(64), nullable=True),
        sa.Column("reporter_agent", sa.String(512), nullable=True),
        *_timestamps(),
    )
    for column in ("truck_id", "operator_id", "incident_type", "category_id", "status", "occurred_at", "created_at"):
        op.create_index(f"ix_incidents_{column}", "incidents", [column])

    op.create_table(
        "incident_photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), sa.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("thumb_key", sa.String(255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_incident_photos_incident_id", "incident_photos", ["incident_id"])
    op.create_index("ix_incident_photos_created_at", "incident_photos", ["created_at"])

    op.create_table(
        "incident_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), sa.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("comment", sa.String(1000), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_incident_events_incident_id", "incident_events", ["incident_id"])
    op.create_index("ix_incident_events_created_at", "incident_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("incident_events")
    op.drop_table("incident_photos")
    op.drop_table("incidents")
