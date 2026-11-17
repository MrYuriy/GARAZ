"""users.must_change_password

Revision ID: 00002
Revises: 00001
"""

import sqlalchemy as sa
from alembic import op

revision = "00002"
down_revision = "00001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing accounts already chose their passwords: they start cleared.
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
