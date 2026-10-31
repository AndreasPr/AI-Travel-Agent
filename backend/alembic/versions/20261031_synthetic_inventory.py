"""Add synthetic inventory metadata and natural keys without relabeling legacy rows."""
from alembic import op
import sqlalchemy as sa

revision = "20261031_synthetic_inventory"
down_revision = "20261021_rag_metadata_schema_fix"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, type_ in [("origin_city", sa.String(255)), ("destination_city", sa.String(255)),
                        ("duration_minutes", sa.Integer()), ("is_nonstop", sa.Boolean()),
                        ("currency", sa.String(3)), ("source", sa.String(64))]:
        op.add_column("flights", sa.Column(name, type_, nullable=True))
    for name, type_ in [("district", sa.String(255)), ("tier", sa.String(32)),
                        ("currency", sa.String(3)), ("source", sa.String(64))]:
        op.add_column("hotels", sa.Column(name, type_, nullable=True))
    op.create_unique_constraint("uq_flights_inventory_key", "flights", ["source", "flight_date", "starting_airport", "destination_airport", "airline"])
    op.create_unique_constraint("uq_hotels_inventory_key", "hotels", ["source", "name", "city", "country"])


def downgrade() -> None:
    op.drop_constraint("uq_hotels_inventory_key", "hotels", type_="unique")
    op.drop_constraint("uq_flights_inventory_key", "flights", type_="unique")
    for name in ["district", "tier", "currency", "source"]:
        op.drop_column("hotels", name)
    for name in ["origin_city", "destination_city", "duration_minutes", "is_nonstop", "currency", "source"]:
        op.drop_column("flights", name)
