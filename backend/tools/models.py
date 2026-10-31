"""Typed tool contracts; price, availability and coordinates stay inside result data."""
from __future__ import annotations

from datetime import date as Date, datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, allow_inf_nan=False)


class ToolError(Contract):
    code: Literal["invalid_input", "timeout", "upstream_error", "output_too_large", "configuration", "internal_error"]
    message: str
    retryable: bool = False


class Failure(Contract):
    error: ToolError


Data = TypeVar("Data")


class ToolResult(Contract, Generic[Data]):
    tool_result_id: str
    tool: str
    status: Literal["ok", "no_data", "error"]
    data: Data | Failure | None
    source: str
    fetched_at: datetime
    cache_hit: bool


class DestinationInput(Contract):
    query: str = Field(min_length=1, max_length=1000)
    city: str | None = None
    country: str | None = None
    season: str | None = None
    topic: str | None = None
    k: int = Field(default=5, ge=1, le=20)


class Chunk(Contract):
    chunk_id: str
    title: str | None
    url: str | None
    license: str | None
    attribution: str | None
    excerpt: str = Field(max_length=600)


class DestinationOutput(Contract):
    chunks: list[Chunk]


class WeatherInput(Contract):
    city: str | None = Field(default=None, min_length=1, max_length=200)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    start_date: Date
    end_date: Date

    @model_validator(mode="after")
    def dates_and_location(self):
        if self.city is not None:
            if self.lat is not None or self.lon is not None:
                raise ValueError("Supply city or lat/lon, not both")
        elif self.lat is None or self.lon is None:
            raise ValueError("Supply city or both lat and lon")
        if not 0 <= (self.end_date - self.start_date).days <= 31:
            raise ValueError("Weather date range must be ordered and at most 32 days")
        return self


class WeatherDay(Contract):
    date: Date
    basis_date: Date
    label: str
    temperature_max_c: float | None
    temperature_min_c: float | None
    precipitation_mm: float | None


class WeatherOutput(Contract):
    days: list[WeatherDay]
    attribution: str = "Weather data by Open-Meteo (CC BY 4.0); city lookup by GeoNames."
    note: str = "Typical values describe one previous year, not a climate average or forecast."


class CurrencyInput(Contract):
    amount: Decimal = Field(ge=0, max_digits=16, decimal_places=4)
    from_currency: str = Field(alias="from", pattern="^[A-Z]{3}$")
    to_currency: str = Field(alias="to", pattern="^[A-Z]{3}$")
    date: Date | None = None


class CurrencyOutput(Contract):
    amount: Decimal
    from_currency: str
    to_currency: str
    converted_amount: Decimal
    rate: Decimal
    rate_date: Date
    requested_date: Date | None


class GeocodeInput(Contract):
    name: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=200)


class Coordinates(Contract):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class GeocodeOutput(Coordinates):
    display_name: str
    osm_type: str | None = None
    osm_id: int | None = None
    attribution: str = "© OpenStreetMap contributors, ODbL 1.0. https://www.openstreetmap.org/copyright"


class FlightsInput(Contract):
    origin: str = Field(pattern="^[A-Z]{3}$")
    destination_city: str = Field(min_length=1, max_length=255)
    depart_date: Date
    return_date: Date | None = None
    max_price: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def dates(self):
        if self.return_date and self.return_date < self.depart_date:
            raise ValueError("Return date precedes departure")
        return self


class FlightQuote(Contract):
    id: int
    flight_date: Date
    origin: str
    destination: str
    origin_city: str | None
    destination_city: str | None
    airline: str
    duration_minutes: int | None
    is_nonstop: bool | None
    price: Decimal
    currency: str
    source: Literal["synthetic-v1"]


class FlightsOutput(Contract):
    outbound: list[FlightQuote]
    inbound: list[FlightQuote]
    availability: str = "Synthetic inventory only; not live availability or a booking offer."
    truncated: bool = False


class HotelsInput(Contract):
    city: str = Field(min_length=1, max_length=255)
    check_in: Date
    check_out: Date
    max_price_per_night: Decimal | None = Field(default=None, ge=0)
    min_rating: float | None = Field(default=None, ge=0, le=5)
    tier: Literal["budget", "mid", "upscale"] | None = None

    @model_validator(mode="after")
    def dates(self):
        if not 1 <= (self.check_out - self.check_in).days <= 365:
            raise ValueError("Stay must be between 1 and 365 nights")
        return self


class HotelQuote(Contract):
    id: int
    name: str
    city: str
    district: str | None
    tier: str | None
    price_per_night: Decimal
    total_price: Decimal
    nights: int
    rating: float | None
    currency: str
    source: Literal["synthetic-v1"]


class HotelsOutput(Contract):
    hotels: list[HotelQuote]
    check_in: Date
    check_out: Date
    availability: str = "Synthetic seasonal quotes only; no room-stock or booking availability is tracked."
    truncated: bool = False


class Trip(Contract):
    start_date: Date
    end_date: Date
    currency: str = Field(pattern="^[A-Z]{3}$")

    @model_validator(mode="after")
    def dates(self):
        if self.end_date < self.start_date:
            raise ValueError("Trip end precedes start")
        return self


class Item(Contract):
    id: str
    start: datetime
    end: datetime
    place: str
    category: str
    cost: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(pattern="^[A-Z]{3}$")
    chunk_ids: list[str] = Field(default_factory=list)
    tool_result_ids: list[str] = Field(default_factory=list)
    coords: Coordinates | None = None
    coord_tool_result_id: str | None = None
    allow_outside_visiting_window: bool = False
    travel_mode: Literal["walking", "transit"] = "walking"

    @model_validator(mode="after")
    def local_times(self):
        # Local wall-clock times avoid mixing offset-aware and offset-naive day schedules.
        if self.start.tzinfo is not None or self.end.tzinfo is not None:
            raise ValueError("Use local wall-clock datetimes without offsets")
        if self.end <= self.start:
            raise ValueError("Item end must follow start")
        return self


class Day(Contract):
    date: Date
    items: list[Item]


class Itinerary(Contract):
    trip: Trip
    days: list[Day]


class ValidateInput(Contract):
    # Keep invalid itineraries parseable so the tool can return a named schema issue.
    itinerary: dict
    budget: Decimal = Field(ge=0)


class Issue(Contract):
    name: str
    severity: Literal["error", "warning"]
    message: str
    item_ids: list[str] = Field(default_factory=list)


class ValidateOutput(Contract):
    valid: bool
    total_cost: Decimal | None
    currency: str | None
    issues: list[Issue]
