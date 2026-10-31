"""Public tool contracts and execution policy."""
from backend.tools import handlers, models
from backend.tools.runtime import Policy, ToolDefinition
from backend.tools.validator import validate_itinerary

REGISTRY = {definition.name: definition for definition in [
    ToolDefinition("search_destinations", "Retrieve cited destination excerpts; no embeddings or coordinates.", models.DestinationInput, models.DestinationOutput, handlers.search_destinations, "local-rag", Policy(timeout_seconds=120, attempts=1, cache_ttl_seconds=0)),
    ToolDefinition("get_weather", "Forecast or explicitly labeled previous-year weather; never returns coordinates.", models.WeatherInput, models.WeatherOutput, handlers.get_weather, "Open-Meteo", Policy(timeout_seconds=30, cache_ttl_seconds=3600)),
    ToolDefinition("convert_currency", "Convert using Frankfurter reference rates; returns the actual rate date.", models.CurrencyInput, models.CurrencyOutput, handlers.convert_currency, "Frankfurter", Policy(cache_ttl_seconds=86400)),
    ToolDefinition("geocode_place", "User-triggered OSM place lookup with attribution, caching and a shared-host one-request-per-second limit.", models.GeocodeInput, models.GeocodeOutput, handlers.geocode_place, "OpenStreetMap/Nominatim", Policy(cache_ttl_seconds=2592000)),
    ToolDefinition("search_flights", "Search synthetic-v1 flights; max_price is a per-leg USD cap. Round trips require both legs to exist.", models.FlightsInput, models.FlightsOutput, handlers.search_flights, "synthetic-v1", Policy(attempts=1, cache_ttl_seconds=0)),
    ToolDefinition("search_hotels", "Search synthetic-v1 seasonal quotes, not live room availability; returns nightly and total stay amounts.", models.HotelsInput, models.HotelsOutput, handlers.search_hotels, "synthetic-v1", Policy(attempts=1, cache_ttl_seconds=0)),
    ToolDefinition("validate_itinerary", "Validate local-time itinerary structure, schedule, budget and stored ToolResult price/coordinate evidence.", models.ValidateInput, models.ValidateOutput, validate_itinerary, "deterministic-validator", Policy(timeout_seconds=10, attempts=1, cache_ttl_seconds=0)),
]}


def tool_schemas():
    return [REGISTRY[name].schema() for name in sorted(REGISTRY)]
