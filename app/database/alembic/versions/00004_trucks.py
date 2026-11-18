"""trucks

Revision ID: 00004
Revises: 00003
"""

import sqlalchemy as sa
from alembic import op

revision = "00004"
down_revision = "00003"
branch_labels = None
depends_on = None

_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "trucks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id"), nullable=False),
        sa.Column("number", sa.String(32), nullable=False, unique=True),
        sa.Column("manufacturer", sa.String(64), nullable=True),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("truck_type_id", sa.Integer(), sa.ForeignKey("truck_types.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("qr_token", sa.String(64), nullable=False, unique=True),
        sa.Column("qr_issued_at", _TS, nullable=False),
        sa.Column("created_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.func.now(), nullable=False),
    )
    for column in ("site_id", "truck_type_id", "status", "created_at"):
        op.create_index(f"ix_trucks_{column}", "trucks", [column])


def downgrade() -> None:
    for column in ("site_id", "truck_type_id", "status", "created_at"):
        op.drop_index(f"ix_trucks_{column}", table_name="trucks")
    op.drop_table("trucks")
