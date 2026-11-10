"""Persistent security admissions, keyed by pseudonymous subject and time window."""
from alembic import op
import sqlalchemy as sa

revision = '20261109_guardrails'
down_revision = '20261103_agent_state'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('security_usage', sa.Column('key', sa.String(80), primary_key=True),
                    sa.Column('window', sa.BigInteger(), primary_key=True),
                    sa.Column('requests', sa.BigInteger(), nullable=False),
                    sa.Column('tokens', sa.BigInteger(), nullable=False))


def downgrade():
    op.drop_table('security_usage')
