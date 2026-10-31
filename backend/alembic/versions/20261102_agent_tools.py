"""Cache HTTP tool data and persist trusted result provenance."""
from alembic import op
import sqlalchemy as sa

revision = "20261102_agent_tools"
down_revision = "20261101_llm_usage_daily"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("tool_http_cache",
                    sa.Column("cache_key", sa.String(64), primary_key=True),
                    sa.Column("tool", sa.String(64), nullable=False),
                    sa.Column("payload", sa.JSON(), nullable=False),
                    sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_tool_http_cache_expires_at", "tool_http_cache", ["expires_at"])
    op.create_table("tool_results",
                    sa.Column("tool_result_id", sa.String(36), primary_key=True),
                    sa.Column("payload", sa.JSON(), nullable=False),
                    sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("tool_results")
    op.drop_index("ix_tool_http_cache_expires_at", table_name="tool_http_cache")
    op.drop_table("tool_http_cache")
