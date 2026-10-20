"""Initial PostgreSQL schema with pgvector support.

Revision ID: 20241020_initial_postgres_schema
Revises: 
Create Date: 2026-10-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import TSVECTOR

# revision identifiers, used by Alembic.
revision = "20241020_initial_postgres_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "airports",
        sa.Column("index", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String()),
        sa.Column("icao", sa.String()),
        sa.Column("iata", sa.String()),
        sa.Column("city", sa.String()),
        sa.Column("subd", sa.String()),
        sa.Column("country", sa.String()),
        sa.Column("elevation", sa.Float()),
        sa.Column("lat", sa.Float()),
        sa.Column("lon", sa.Float()),
        sa.Column("tz", sa.String()),
        sa.Column("lid", sa.String()),
    )

    op.create_table(
        "flight_prices",
        sa.Column("index", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("flightDate", sa.Date()),
        sa.Column("startingAirport", sa.String()),
        sa.Column("destinationAirport", sa.String()),
        sa.Column("isBasicEconomy", sa.Boolean()),
        sa.Column("isRefundable", sa.Boolean()),
        sa.Column("isNonStop", sa.Boolean()),
        sa.Column("segmentsAirlineName", sa.String()),
        sa.Column("totalFare", sa.Integer()),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    op.create_table(
        "trips",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("destination_city", sa.String(length=255), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="planned"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    op.create_table(
        "itineraries",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("trip_id", sa.Integer(), sa.ForeignKey("trips.id"), nullable=False),
        sa.Column("flight_id", sa.Integer(), nullable=True),
        sa.Column("hotel_id", sa.Integer(), nullable=True),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column("reservation_code", sa.String(length=128), nullable=True),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("trip_id", sa.Integer(), sa.ForeignKey("trips.id"), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    op.create_table(
        "flights",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("flight_date", sa.Date(), nullable=False),
        sa.Column("starting_airport", sa.String(length=16), nullable=False),
        sa.Column("destination_airport", sa.String(length=16), nullable=False),
        sa.Column("airline", sa.String(length=128), nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    op.create_table(
        "hotels",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=255), nullable=False),
        sa.Column("country", sa.String(length=255), nullable=False),
        sa.Column("price_per_night", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("season", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("license", sa.String(length=128), nullable=True),
        sa.Column("city", sa.String(length=255), nullable=True),
        sa.Column("country", sa.String(length=255), nullable=True),
        sa.Column("season", sa.String(length=50), nullable=True),
        sa.Column("topic", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("search_vector", TSVECTOR(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("search_vector", TSVECTOR(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    op.execute(
        "CREATE INDEX ix_documents_embedding_hnsw ON documents USING hnsw (embedding vector_cosine_ops);"
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw ON document_chunks USING hnsw (embedding vector_cosine_ops);"
    )
    op.execute("CREATE INDEX ix_documents_search_vector_gin ON documents USING gin (search_vector);")
    op.execute("CREATE INDEX ix_document_chunks_search_vector_gin ON document_chunks USING gin (search_vector);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_search_vector_gin;")
    op.execute("DROP INDEX IF EXISTS ix_documents_search_vector_gin;")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw;")
    op.execute("DROP INDEX IF EXISTS ix_documents_embedding_hnsw;")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("hotels")
    op.drop_table("flights")
    op.drop_table("messages")
    op.drop_table("itineraries")
    op.drop_table("trips")
    op.drop_table("users")
    op.drop_table("flight_prices")
    op.drop_table("airports")
