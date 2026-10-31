from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import DeclarativeBase

from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    pass


class Airport(Base):
    __tablename__ = "airports"
    __table_args__ = {"extend_existing": True}
    id = Column("index", BigInteger, primary_key=True, autoincrement=True)
    name = Column(String)
    icao = Column(String)
    iata = Column(String)
    city = Column(String)
    subd = Column(String)
    country = Column(String)
    elevation = Column(Float)
    lat = Column(Float)
    lon = Column(Float)
    tz = Column(String)
    lid = Column(String)


class FlightPrice(Base):
    __tablename__ = "flight_prices"
    __table_args__ = {"extend_existing": True}
    id = Column("index", BigInteger, primary_key=True, autoincrement=True)
    flightDate = Column(Date)
    startingAirport = Column(String)
    destinationAirport = Column(String)
    isBasicEconomy = Column(Boolean)
    isRefundable = Column(Boolean)
    isNonStop = Column(Boolean)
    segmentsAirlineName = Column(String)
    totalFare = Column(Integer)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True)
    full_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Trip(Base):
    __tablename__ = "trips"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    destination_city = Column(String(255), nullable=False)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    status = Column(String(50), nullable=False, server_default="planned")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Itinerary(Base):
    __tablename__ = "itineraries"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    flight_id = Column(Integer, nullable=True)
    hotel_id = Column(Integer, nullable=True)
    day_index = Column(Integer, nullable=False)
    reservation_code = Column(String(128), nullable=True)


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Flight(Base):
    __tablename__ = "flights"
    __table_args__ = (UniqueConstraint("source", "flight_date", "starting_airport", "destination_airport", "airline", name="uq_flights_inventory_key"),)
    origin_city = Column(String(255), nullable=True)
    destination_city = Column(String(255), nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    is_nonstop = Column(Boolean, nullable=True)
    currency = Column(String(3), nullable=True)
    source = Column(String(64), nullable=True)
    id = Column(Integer, primary_key=True, autoincrement=True)
    flight_date = Column(Date, nullable=False)
    starting_airport = Column(String(16), nullable=False)
    destination_airport = Column(String(16), nullable=False)
    airline = Column(String(128), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Hotel(Base):
    __tablename__ = "hotels"
    __table_args__ = (UniqueConstraint("source", "name", "city", "country", name="uq_hotels_inventory_key"),)
    district = Column(String(255), nullable=True)
    tier = Column(String(32), nullable=True)
    currency = Column(String(3), nullable=True)
    source = Column(String(64), nullable=True)
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    city = Column(String(255), nullable=False)
    country = Column(String(255), nullable=False)
    price_per_night = Column(Numeric(10, 2), nullable=False)
    rating = Column(Float, nullable=True)
    season = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_url = Column(String(500), nullable=True)
    title = Column(String(255), nullable=False)
    license = Column(String(128), nullable=True)
    city = Column(String(255), nullable=True)
    country = Column(String(255), nullable=True)
    season = Column(String(50), nullable=True)
    topic = Column(String(255), nullable=True)
    text = Column(Text, nullable=False)
    embedding = Column(Vector(384), nullable=True)
    search_vector = Column(TSVECTOR, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    chunk_id = Column(String(64), unique=True, nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    city = Column(String(255), nullable=False, default="Unknown")
    country = Column(String(255), nullable=False, default="Unknown")
    season = Column(String(50), nullable=True)
    topic = Column(String(255), nullable=True)
    revision_id = Column(String(128), nullable=True)
    retrieved_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    source_url = Column(String(500), nullable=True)
    license = Column(String(128), nullable=True)
    text = Column(Text, nullable=False)
    embedding = Column(Vector(384), nullable=True)
    search_vector = Column(TSVECTOR, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LLMUsageDaily(Base):
    __tablename__ = "llm_usage_daily"
    __table_args__ = (CheckConstraint("requests >= 0", name="ck_llm_usage_daily_nonnegative"),)
    date = Column(Date, primary_key=True)
    provider = Column(String(64), primary_key=True)
    model = Column(String(255), primary_key=True)
    requests = Column(Integer, nullable=False, server_default="0")


class ToolHTTPCache(Base):
    __tablename__ = "tool_http_cache"
    cache_key = Column(String(64), primary_key=True)
    tool = Column(String(64), nullable=False)
    payload = Column(JSON, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)


class StoredToolResult(Base):
    __tablename__ = "tool_results"
    tool_result_id = Column(String(36), primary_key=True)
    payload = Column(JSON, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)
