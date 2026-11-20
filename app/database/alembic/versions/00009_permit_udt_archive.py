"""permits: UDT number, and the link from an archived permit to its renewal

Revision ID: 00009
Revises: 00008
"""

import sqlalchemy as sa
from alembic import op

revision = "00009"
down_revision = "00008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("permits", sa.Column("udt_number", sa.String(64), nullable=True))
    op.add_column("permits", sa.Column("replaced_by_id", sa.Integer(), sa.ForeignKey("permits.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("permits", "replaced_by_id")
    op.drop_column("permits", "udt_number")
    # The status is plain text; archived permits read as expired without the column.
    op.execute("UPDATE permits SET status = 'EXPIRED' WHERE status = 'ARCHIVED'")
