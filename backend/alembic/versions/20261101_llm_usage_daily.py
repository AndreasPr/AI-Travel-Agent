"""Persist daily LLM request reservations across server restarts."""
from alembic import op
import sqlalchemy as sa

revision = "20261101_llm_usage_daily"
down_revision = "20261031_synthetic_inventory"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("llm_usage_daily",
                    sa.Column("date", sa.Date(), primary_key=True),
                    sa.Column("provider", sa.String(64), primary_key=True),
                    sa.Column("model", sa.String(255), primary_key=True),
                    sa.Column("requests", sa.Integer(), nullable=False, server_default="0"),
                    sa.CheckConstraint("requests >= 0", name="ck_llm_usage_daily_nonnegative"))


def downgrade():
    op.drop_table("llm_usage_daily")
