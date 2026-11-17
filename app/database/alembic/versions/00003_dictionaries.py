"""dictionaries: sites, permit_categories, truck_types, employers, incident_categories

Revision ID: 00003
Revises: 00002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "00003"
down_revision = "00002"
branch_labels = None
depends_on = None

_TS = sa.DateTime(timezone=True)

_TABLES = ("sites", "permit_categories", "truck_types", "employers", "incident_categories")

# From the requirements, section 11. "wyłączony" defaults start at NIE: which
# ones stop the truck is still an open question, and admins can change it.
_BREAKDOWN = (
    "Bateria",
    "Elektryka",
    "Hydraulika",
    "Maszt",
    "Widły",
    "Napęd",
    "Opony",
    "Karoseria",
    "Osłony",
    "Oświetlenie",
)
_COLLISION = ("Kolizja z regałem", "Kolizja z infrastrukturą", "Kolizja z innym wózkiem")


def _dictionary_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    for table in _TABLES:
        extra = []
        if table == "incident_categories":
            extra = [
                sa.Column("incident_types", postgresql.JSONB(), nullable=False),
                sa.Column("default_out_of_service", sa.Boolean(), nullable=False, server_default=sa.false()),
            ]
        op.create_table(table, *_dictionary_columns(), *extra)
        op.create_index(f"ix_{table}_created_at", table, ["created_at"])

    sites = sa.table("sites", sa.column("name", sa.String), sa.column("sort_order", sa.Integer))
    op.bulk_insert(sites, [{"name": "Magazyn główny", "sort_order": 0}])

    categories = sa.table(
        "incident_categories",
        sa.column("name", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("incident_types", postgresql.JSONB),
    )
    rows = [{"name": name, "incident_types": ["AWARIA", "USZKODZENIE"]} for name in _BREAKDOWN]
    rows += [{"name": name, "incident_types": ["KOLIZJA"]} for name in _COLLISION]
    rows.append({"name": "Inne", "incident_types": ["AWARIA", "USZKODZENIE", "KOLIZJA"]})
    op.bulk_insert(categories, [{**row, "sort_order": (i + 1) * 10} for i, row in enumerate(rows)])


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_index(f"ix_{table}_created_at", table_name=table)
        op.drop_table(table)
