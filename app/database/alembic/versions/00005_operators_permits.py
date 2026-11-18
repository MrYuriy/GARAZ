"""operators and permits

Revision ID: 00005
Revises: 00004
"""

import sqlalchemy as sa
from alembic import op

revision = "00005"
down_revision = "00004"
branch_labels = None
depends_on = None

_TS = sa.DateTime(timezone=True)

_OPERATOR_INDEXES = ("site_id", "full_name", "employer_id", "hyster_card_number", "created_at")
_PERMIT_INDEXES = ("operator_id", "category_id", "valid_until", "status", "created_at")


def upgrade() -> None:
    op.create_table(
        "operators",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id"), nullable=False),
        sa.Column("full_name", sa.String(128), nullable=False),
        sa.Column("employer_id", sa.Integer(), sa.ForeignKey("employers.id"), nullable=True),
        sa.Column("hyster_card_number", sa.String(32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("qr_token", sa.String(64), nullable=False, unique=True),
        sa.Column("qr_issued_at", _TS, nullable=False),
        sa.Column("created_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.func.now(), nullable=False),
    )
    for column in _OPERATOR_INDEXES:
        op.create_index(f"ix_operators_{column}", "operators", [column])

    op.create_table(
        "permits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("operators.id"), nullable=False),
        sa.Column("number", sa.String(32), nullable=False, unique=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("permit_categories.id"), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("basis_name", sa.String(128), nullable=True),
        sa.Column("basis_number", sa.String(64), nullable=True),
        sa.Column("basis_date", sa.Date(), nullable=True),
        sa.Column("document_key", sa.String(255), nullable=True),
        sa.Column("document_filename", sa.String(255), nullable=True),
        sa.Column("document_content_type", sa.String(64), nullable=True),
        sa.Column("document_size", sa.Integer(), nullable=True),
        sa.Column("created_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.func.now(), nullable=False),
    )
    for column in _PERMIT_INDEXES:
        op.create_index(f"ix_permits_{column}", "permits", [column])

    op.create_table(
        "permit_truck_types",
        sa.Column("permit_id", sa.Integer(), sa.ForeignKey("permits.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("truck_type_id", sa.Integer(), sa.ForeignKey("truck_types.id"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("permit_truck_types")
    for column in _PERMIT_INDEXES:
        op.drop_index(f"ix_permits_{column}", table_name="permits")
    op.drop_table("permits")
    for column in _OPERATOR_INDEXES:
        op.drop_index(f"ix_operators_{column}", table_name="operators")
    op.drop_table("operators")
