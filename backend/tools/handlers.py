"""Read-only retrieval, free HTTP services and explicitly synthetic inventory queries."""
import calendar
import os
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select, text

from backend.db.models import Flight, Hotel
from backend.tools.models import CurrencyOutput, DestinationOutput, FlightQuote, FlightsOutput, GeocodeOutput, HotelQuote, HotelsOutput, WeatherDay, WeatherOutput
from backend.tools.runtime import ToolFault


def search_destinations(request, ctx):
    search = ctx.runtime.search
    if search is None:
        from backend.rag.search import search
    rows = search(request.query, limit=request.k, rerank=True, city=request.city, country=request.country, season=request.season, topic=request.topic)
    chunks = [{"chunk_id": str(row["chunk_id"]), "title": row.get("title"), "url": row.get("source_url"),
               "license": row.get("license"), "attribution": row.get("attribution"), "excerpt": str(row.get("text", ""))[:600]}
              for row in rows[:request.k]]
    return DestinationOutput(chunks=chunks) if chunks else None


def get_weather(request, ctx):
    today = ctx.runtime.today()
    targets = [request.start_date + timedelta(days=index) for index in range((request.end_date - request.start_date).days + 1)]
    groups = defaultdict(list)
    for target in targets:
        if today <= target <= today + timedelta(days=15):
            groups[("https://api.open-meteo.com/v1/forecast", "forecast")].append((target, target))
        else:
            if target > today:
                year = target.year - 1
                basis = target.replace(year=year, day=min(target.day, calendar.monthrange(year, target.month)[1]))
                label = f"typical, based on {year}"
            else:
                basis, label = target, "historical"
            # Archive observations for future or very recent baseline dates are not invented.
            if basis > today - timedelta(days=5):
                return None
            groups[("https://archive-api.open-meteo.com/v1/archive", label)].append((target, basis))
    lat, lon = request.lat, request.lon
    if request.city:
        lookup = ctx.http("https://geocoding-api.open-meteo.com/v1/search", {"name": request.city, "count": 1, "language": "en", "format": "json"})
        matches = lookup.get("results", [])
        if not matches:
            return None
        lat, lon = float(matches[0]["latitude"]), float(matches[0]["longitude"])
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ToolFault("upstream_error", "Invalid weather location")
    days = []
    for (url, label), pairs in groups.items():
        params = {"latitude": lat, "longitude": lon, "start_date": min(basis for _, basis in pairs).isoformat(),
                  "end_date": max(basis for _, basis in pairs).isoformat(), "timezone": "UTC",
                  "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum"}
        if label == "forecast":
            params["forecast_days"] = 16
        raw = ctx.http(url, params)
        daily = raw.get("daily", {})
        times = daily.get("time", [])
        if not times:
            return None
        for target, basis in pairs:
            if basis.isoformat() not in times:
                return None
            index = times.index(basis.isoformat())
            values = {}
            for output, key in [("temperature_max_c", "temperature_2m_max"), ("temperature_min_c", "temperature_2m_min"), ("precipitation_mm", "precipitation_sum")]:
                array = daily.get(key, [])
                values[output] = array[index] if index < len(array) else None
            days.append(WeatherDay(date=target, basis_date=basis, label=label, **values))
    return WeatherOutput(days=sorted(days, key=lambda day: day.date))


def convert_currency(request, ctx):
    if request.date and request.date > ctx.runtime.today():
        raise ToolFault("invalid_input", "Future exchange rates are unavailable")
    if request.from_currency == request.to_currency:
        return CurrencyOutput(amount=request.amount, from_currency=request.from_currency, to_currency=request.to_currency,
                              converted_amount=request.amount, rate=Decimal("1"), rate_date=request.date or ctx.runtime.today(), requested_date=request.date)
    params = {"base": request.from_currency, "quotes": request.to_currency}
    if request.date:
        params["date"] = request.date.isoformat()
    rows = ctx.http("https://api.frankfurter.dev/v2/rates", params)
    matches = [row for row in rows if row.get("base", "").upper() == request.from_currency and row.get("quote", "").upper() == request.to_currency]
    if not matches:
        return None
    row = matches[-1]
    rate = Decimal(str(row["rate"]))
    if not rate.is_finite() or rate <= 0:
        raise ToolFault("upstream_error", "Invalid exchange rate")
    return CurrencyOutput(amount=request.amount, from_currency=request.from_currency, to_currency=request.to_currency,
                          converted_amount=(request.amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), rate=rate,
                          rate_date=row["date"], requested_date=request.date)


def geocode_place(request, ctx):
    user_agent = os.getenv("NOMINATIM_USER_AGENT", "").strip()
    if not user_agent:
        raise ToolFault("configuration", "Set NOMINATIM_USER_AGENT to identify your application and contact before live geocoding")
    endpoint = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
    rows = ctx.http(endpoint, {"q": f"{request.name}, {request.city}", "format": "jsonv2", "limit": 1},
                    headers={"User-Agent": user_agent}, rate_limited=True)
    if not rows:
        return None
    row = rows[0]
    return GeocodeOutput(lat=row["lat"], lon=row["lon"], display_name=row["display_name"], osm_type=row.get("osm_type"), osm_id=row.get("osm_id"))


def _db_timeout(session, ctx):
    ctx.check()
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT set_config('statement_timeout', :timeout, true)"), {"timeout": str(max(1, int(ctx.remaining() * 1000)))})


def _flight(row):
    return FlightQuote(id=row.id, flight_date=row.flight_date, origin=row.starting_airport, destination=row.destination_airport,
                       origin_city=row.origin_city, destination_city=row.destination_city, airline=row.airline,
                       duration_minutes=row.duration_minutes, is_nonstop=row.is_nonstop, price=row.price, currency=row.currency, source=row.source)


def search_flights(request, ctx):
    with ctx.runtime.session_factory() as session:
        _db_timeout(session, ctx)
        statement = select(Flight).where(Flight.source == "synthetic-v1", Flight.starting_airport == request.origin,
                                         Flight.destination_city == request.destination_city, Flight.flight_date == request.depart_date)
        if request.max_price is not None:
            statement = statement.where(Flight.price <= request.max_price)
        outbound = session.scalars(statement.order_by(Flight.price, Flight.id).limit(51)).all()
        if not outbound:
            return None
        inbound = []
        if request.return_date:
            statement = select(Flight).where(Flight.source == "synthetic-v1", Flight.origin_city == request.destination_city,
                                             Flight.destination_airport == request.origin, Flight.flight_date == request.return_date)
            if request.max_price is not None:
                statement = statement.where(Flight.price <= request.max_price)
            inbound = session.scalars(statement.order_by(Flight.price, Flight.id).limit(51)).all()
            if not inbound:
                return None
        return FlightsOutput(outbound=[_flight(row) for row in outbound[:50]], inbound=[_flight(row) for row in inbound[:50]], truncated=len(outbound) > 50 or len(inbound) > 50)


def search_hotels(request, ctx):
    with ctx.runtime.session_factory() as session:
        _db_timeout(session, ctx)
        statement = select(Hotel).where(Hotel.source == "synthetic-v1", Hotel.city == request.city)
        if request.max_price_per_night is not None:
            statement = statement.where(Hotel.price_per_night <= request.max_price_per_night)
        if request.min_rating is not None:
            statement = statement.where(Hotel.rating >= request.min_rating)
        if request.tier is not None:
            statement = statement.where(Hotel.tier == request.tier)
        rows = session.scalars(statement.order_by(Hotel.price_per_night, Hotel.id).limit(51)).all()
        if not rows:
            return None
        nights = (request.check_out - request.check_in).days
        hotels = [HotelQuote(id=row.id, name=row.name, city=row.city, district=row.district, tier=row.tier, price_per_night=row.price_per_night,
                             total_price=row.price_per_night * nights, nights=nights, rating=row.rating, currency=row.currency, source=row.source) for row in rows[:50]]
        return HotelsOutput(hotels=hotels, check_in=request.check_in, check_out=request.check_out, truncated=len(rows) > 50)
