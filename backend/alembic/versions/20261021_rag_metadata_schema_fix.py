"""Add missing metadata columns for the RAG chunk table.

Revision ID: 20261021_rag_metadata_schema_fix
Revises: 20241020_initial_postgres_schema
Create Date: 2026-10-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20261021_rag_metadata_schema_fix"
down_revision = "20241020_initial_postgres_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_chunks", sa.Column("chunk_id", sa.String(length=64), nullable=True))
    op.add_column("document_chunks", sa.Column("city", sa.String(length=255), nullable=True, server_default="Unknown"))
    op.add_column("document_chunks", sa.Column("country", sa.String(length=255), nullable=True, server_default="Unknown"))
    op.add_column("document_chunks", sa.Column("season", sa.String(length=50), nullable=True))
    op.add_column("document_chunks", sa.Column("topic", sa.String(length=255), nullable=True))
    op.add_column("document_chunks", sa.Column("revision_id", sa.String(length=128), nullable=True))
    op.add_column("document_chunks", sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.add_column("document_chunks", sa.Column("source_url", sa.String(length=500), nullable=True))
    op.add_column("document_chunks", sa.Column("license", sa.String(length=128), nullable=True))

    op.execute(
        "UPDATE document_chunks SET chunk_id = COALESCE(chunk_id, md5(random()::text || id::text)) WHERE chunk_id IS NULL"
    )
    op.execute("UPDATE document_chunks SET city = COALESCE(city, 'Unknown') WHERE city IS NULL")
    op.execute("UPDATE document_chunks SET country = COALESCE(country, 'Unknown') WHERE country IS NULL")

    op.alter_column("document_chunks", "chunk_id", existing_type=sa.String(length=64), nullable=False)
    op.alter_column("document_chunks", "city", existing_type=sa.String(length=255), nullable=False, server_default="Unknown")
    op.alter_column("document_chunks", "country", existing_type=sa.String(length=255), nullable=False, server_default="Unknown")

    op.create_index(op.f("ix_document_chunks_chunk_id"), "document_chunks", ["chunk_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_document_chunks_chunk_id"), table_name="document_chunks")
    op.drop_column("document_chunks", "license")
    op.drop_column("document_chunks", "source_url")
    op.drop_column("document_chunks", "retrieved_at")
    op.drop_column("document_chunks", "revision_id")
    op.drop_column("document_chunks", "topic")
    op.drop_column("document_chunks", "season")
    op.drop_column("document_chunks", "country")
    op.drop_column("document_chunks", "city")
    op.drop_column("document_chunks", "chunk_id")
