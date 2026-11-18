"""incidents entered in the panel: who entered them, drivers outside the register

Revision ID: 00008
Revises: 00007
"""

import sqlalchemy as sa
from alembic import op

revision = "00008"
down_revision = "00007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("incidents", "operator_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("incidents", sa.Column("operator_name", sa.String(128), nullable=True))
    op.add_column(
        "incidents",
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("incidents", "created_by_id")
    op.drop_column("incidents", "operator_name")
    # Reports without a registered operator cannot stay once the column is required again.
    op.execute("DELETE FROM incidents WHERE operator_id IS NULL")
    op.alter_column("incidents", "operator_id", existing_type=sa.Integer(), nullable=False)
