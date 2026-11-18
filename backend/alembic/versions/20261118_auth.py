"""Local accounts, revocable sessions, ownership and persistent user quotas."""
from alembic import op
import sqlalchemy as sa

revision = '20261118_auth'
down_revision = '20261109_guardrails'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('auth_users', sa.Column('id', sa.String(36), primary_key=True),
                    sa.Column('email', sa.String(254), nullable=False, unique=True),
                    sa.Column('password_hash', sa.Text(), nullable=False), sa.Column('created_at', sa.BigInteger(), nullable=False))
    op.create_table('auth_sessions', sa.Column('id', sa.String(36), primary_key=True),
                    sa.Column('user_id', sa.String(36), sa.ForeignKey('auth_users.id', ondelete='CASCADE'), nullable=False),
                    sa.Column('expires_at', sa.BigInteger(), nullable=False), sa.Column('revoked', sa.Boolean(), nullable=False))
    op.create_index('ix_auth_sessions_user_id', 'auth_sessions', ['user_id'])
    op.create_table('auth_refresh_tokens', sa.Column('token_hash', sa.String(64), primary_key=True),
                    sa.Column('session_id', sa.String(36), sa.ForeignKey('auth_sessions.id', ondelete='CASCADE'), nullable=False),
                    sa.Column('expires_at', sa.BigInteger(), nullable=False), sa.Column('used', sa.Boolean(), nullable=False))
    op.create_index('ix_auth_refresh_tokens_session_id', 'auth_refresh_tokens', ['session_id'])
    op.create_table('auth_usage_daily', sa.Column('user_id', sa.String(36), sa.ForeignKey('auth_users.id', ondelete='CASCADE'), primary_key=True),
                    sa.Column('day', sa.BigInteger(), primary_key=True), sa.Column('messages', sa.BigInteger(), nullable=False),
                    sa.Column('tokens', sa.BigInteger(), nullable=False))
    op.create_table('auth_login_attempts', sa.Column('key', sa.String(64), primary_key=True),
                    sa.Column('window', sa.BigInteger(), primary_key=True), sa.Column('attempts', sa.Integer(), nullable=False),
                    sa.Column('failures', sa.Integer(), nullable=False), sa.Column('next_allowed', sa.BigInteger(), nullable=False))
    op.add_column('agent_conversations', sa.Column('owner_id', sa.String(36), nullable=True))
    op.create_foreign_key('fk_agent_conversation_owner', 'agent_conversations', 'auth_users', ['owner_id'], ['id'])
    op.create_index('ix_agent_conversations_owner_id', 'agent_conversations', ['owner_id'])


def downgrade():
    op.drop_index('ix_agent_conversations_owner_id', table_name='agent_conversations')
    op.drop_constraint('fk_agent_conversation_owner', 'agent_conversations', type_='foreignkey')
    op.drop_column('agent_conversations', 'owner_id')
    for name in ('auth_login_attempts', 'auth_usage_daily', 'auth_refresh_tokens', 'auth_sessions', 'auth_users'):
        op.drop_table(name)
