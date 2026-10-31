"""Persist conversations, preferences and immutable itinerary versions."""
from alembic import op
import sqlalchemy as sa

revision = '20261103_agent_state'
down_revision = '20261102_agent_tools'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('agent_conversations',
                    sa.Column('id', sa.String(36), primary_key=True),
                    sa.Column('revision', sa.Integer(), nullable=False),
                    sa.Column('preferences', sa.JSON(), nullable=False),
                    sa.Column('state', sa.JSON(), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table('agent_messages',
                    sa.Column('conversation_id', sa.String(36), sa.ForeignKey('agent_conversations.id', ondelete='CASCADE'), primary_key=True),
                    sa.Column('position', sa.Integer(), primary_key=True),
                    sa.Column('role', sa.String(16), nullable=False),
                    sa.Column('content', sa.Text(), nullable=False))
    op.create_table('agent_trips',
                    sa.Column('id', sa.String(36), sa.ForeignKey('agent_conversations.id', ondelete='CASCADE'), primary_key=True),
                    sa.Column('itinerary', sa.JSON(), nullable=True))
    op.create_table('agent_itinerary_versions',
                    sa.Column('trip_id', sa.String(36), sa.ForeignKey('agent_trips.id', ondelete='CASCADE'), primary_key=True),
                    sa.Column('number', sa.Integer(), primary_key=True),
                    sa.Column('parent_number', sa.Integer(), nullable=True),
                    sa.Column('itinerary', sa.JSON(), nullable=False),
                    sa.Column('budget', sa.String(64), nullable=True),
                    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade():
    for table in ['agent_itinerary_versions', 'agent_trips', 'agent_messages', 'agent_conversations']:
        op.drop_table(table)
