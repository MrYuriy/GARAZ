"""truck manufacturers and models as lists

Revision ID: 00006
Revises: 00005

The trucks' free-text manufacturer and model become entries of two lists, and
the trucks point at them. Existing text is carried over: names differing only
in case or spacing become one entry. A model typed without a manufacturer goes
under "Inny".
"""

import sqlalchemy as sa
from alembic import op

revision = "00006"
down_revision = "00005"
branch_labels = None
depends_on = None

_TS = sa.DateTime(timezone=True)
_OTHER = "Inny"


def _tidy(value: str | None) -> str | None:
    return " ".join(value.split())[:64] or None if value else None


def upgrade() -> None:
    op.create_table(
        "truck_manufacturers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_truck_manufacturers_created_at", "truck_manufacturers", ["created_at"])
    op.create_table(
        "truck_models",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "manufacturer_id",
            sa.Integer(),
            sa.ForeignKey("truck_manufacturers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("created_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("manufacturer_id", "name", name="uq_truck_models_manufacturer_name"),
    )
    op.create_index("ix_truck_models_manufacturer_id", "truck_models", ["manufacturer_id"])
    op.create_index("ix_truck_models_created_at", "truck_models", ["created_at"])

    op.add_column("trucks", sa.Column("manufacturer_id", sa.Integer(), nullable=True))
    op.add_column("trucks", sa.Column("model_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_trucks_manufacturer_id", "trucks", "truck_manufacturers", ["manufacturer_id"], ["id"])
    op.create_foreign_key("fk_trucks_model_id", "trucks", "truck_models", ["model_id"], ["id"])
    op.create_index("ix_trucks_manufacturer_id", "trucks", ["manufacturer_id"])
    op.create_index("ix_trucks_model_id", "trucks", ["model_id"])

    _carry_text_over()

    op.drop_column("trucks", "model")
    op.drop_column("trucks", "manufacturer")


def _carry_text_over() -> None:
    bind = op.get_bind()
    trucks = bind.execute(sa.text("SELECT id, manufacturer, model FROM trucks")).fetchall()
    makers: dict[str, int] = {}
    models: dict[tuple[int, str], int] = {}

    def maker_id(name: str) -> int:
        key = name.lower()
        if key not in makers:
            makers[key] = bind.execute(
                sa.text("INSERT INTO truck_manufacturers (name) VALUES (:n) RETURNING id"), {"n": name}
            ).scalar_one()
        return makers[key]

    def model_id(maker: int, name: str) -> int:
        key = (maker, name.lower())
        if key not in models:
            models[key] = bind.execute(
                sa.text("INSERT INTO truck_models (manufacturer_id, name) VALUES (:m, :n) RETURNING id"),
                {"m": maker, "n": name},
            ).scalar_one()
        return models[key]

    for truck_id, maker_text, model_text in trucks:
        maker_name, model_name = _tidy(maker_text), _tidy(model_text)
        if not maker_name and not model_name:
            continue
        maker = maker_id(maker_name or _OTHER)
        model = model_id(maker, model_name) if model_name else None
        bind.execute(
            sa.text("UPDATE trucks SET manufacturer_id = :m, model_id = :md WHERE id = :id"),
            {"m": maker, "md": model, "id": truck_id},
        )


def downgrade() -> None:
    op.add_column("trucks", sa.Column("manufacturer", sa.String(64), nullable=True))
    op.add_column("trucks", sa.Column("model", sa.String(64), nullable=True))
    op.execute(
        "UPDATE trucks SET manufacturer = (SELECT name FROM truck_manufacturers m WHERE m.id = trucks.manufacturer_id),"
        " model = (SELECT name FROM truck_models md WHERE md.id = trucks.model_id)"
    )
    op.drop_index("ix_trucks_model_id", table_name="trucks")
    op.drop_index("ix_trucks_manufacturer_id", table_name="trucks")
    op.drop_constraint("fk_trucks_model_id", "trucks", type_="foreignkey")
    op.drop_constraint("fk_trucks_manufacturer_id", "trucks", type_="foreignkey")
    op.drop_column("trucks", "model_id")
    op.drop_column("trucks", "manufacturer_id")
    op.drop_table("truck_models")
    op.drop_table("truck_manufacturers")
