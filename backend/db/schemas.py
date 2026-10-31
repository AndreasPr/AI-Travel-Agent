from datetime import date
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class AirportSchema(BaseModel):
    name: str = Field(alias="label")
    iata: str = Field(alias="value")

    class Config:
        populate_by_name = True
        from_attributes = True


# pydantic schema for sqlalchemy model
class FlightPriceSchema(BaseModel):
    id: int
    flightDate: date
    startingAirport: str
    destinationAirport: str
    # isBasicEconomy: bool
    # isRefundable: bool
    # isNonStop: bool
    segmentsAirlineName: str
    totalFare: int

    class Config:
        from_attributes = True


class FlightPriceDetailSchema(BaseModel):
    id: int
    flightDate: date
    startingAirport: str
    destinationAirport: str
    isBasicEconomy: bool
    isRefundable: bool
    isNonStop: bool
    segmentsAirlineName: str
    totalFare: int

    class Config:
        from_attributes = True


class FlightSchema(BaseModel):
    """Inventory response; source identifies synthetic records explicitly."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    flight_date: date
    starting_airport: str
    destination_airport: str
    origin_city: str | None
    destination_city: str | None
    airline: str
    duration_minutes: int | None
    is_nonstop: bool | None
    price: Decimal
    currency: str | None
    source: str | None


class HotelSchema(BaseModel):
    """Inventory response; source identifies synthetic records explicitly."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    city: str
    country: str
    district: str | None
    tier: str | None
    price_per_night: Decimal
    rating: float | None
    season: str | None
    currency: str | None
    source: str | None
