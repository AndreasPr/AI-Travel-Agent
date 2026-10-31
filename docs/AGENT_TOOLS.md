# Grounded agent tools

Use `backend.tools.ToolRuntime.execute(name, arguments)` to receive a typed ToolResult envelope. The registry in `backend/tools/registry.py` exposes input/output JSON Schemas and execution policies for all seven tools. `validate_itinerary` also exposes the Itinerary schema as a related contract. Schema snapshots in `tests/snapshots/tools/` are compared exactly by tests; intentional contract changes require explicit review and snapshot updates. Tests never regenerate snapshots.

Every envelope contains tool_result_id, tool, status (ok/no_data/error), data, source, fetched_at and cache_hit. Prices, quoted availability, coordinates and validation totals appear only inside data. Errors use data.error with a code, safe message and retryable flag. No stack traces, connection strings or credentials are included. no_data has null data. Successful/no_data results are persisted in tool_results; arbitrary caller-supplied evidence is never accepted by the validator.

## Tool behavior

| Tool | Behavior | Timeout | Attempts | HTTP TTL |
| --- | --- | ---: | ---: | ---: |
| search_destinations | Configured retrieval.default_mode, rerank enabled; citations and excerpts capped at 600 characters; explicit field allowlist excludes embeddings and coordinates | 120 s | 1 | none |
| get_weather | Open-Meteo forecast through UTC today + 15 days; later dates use the same dates of the previous year, labeled typical, based on YEAR | 30 s | 3 per HTTP fetch | 1 hour |
| convert_currency | Frankfurter v2 reference rates, Decimal conversion rounded to cents, requested and actual observation dates retained | 15 s | 3 | 1 day |
| geocode_place | Nominatim exact submitted place/city search, OSM attribution, no_data for an empty match | 15 s | 3 | 30 days |
| search_flights | Only synthetic-v1 rows; origin IATA, destination city, date and optional per-leg price cap | 15 s | 1 | none |
| search_hotels | Only synthetic-v1 rows; city, nightly cap, rating and tier; computes nights and total quote | 15 s | 1 | none |
| validate_itinerary | Deterministic structure, schedule, travel-time, budget and trusted result provenance checks | 10 s | 1 | none |

All outputs are limited to 64 KiB of serialized envelope JSON; oversized results return output_too_large instead of silently cutting evidence. HTTP bodies are bounded to one MiB while streaming. Inventory queries fetch at most 51 rows and return 50 with an explicit truncated flag. HTTP requests retry only transport failures, 429 and 5xx with exponential delays and Retry-After. Input/HTTP client errors are not retried. Read-only database/retrieval/validation tools have a single attempt.

The caller receives timeout on deadline expiry. In-flight Python threads cannot be forcibly killed: a non-cooperative retrieval/model call may continue until it returns. Workers check the deadline before saving successful results; HTTP read deadlines and Postgres statement_timeout provide additional bounds. The executor has eight workers. This is not a process-level hard-kill sandbox.

## Weather and currency semantics

Open-Meteo city geocoding is used internally to locate weather data; its coordinates are not returned to callers. Only geocode_place provides coordinates that the itinerary validator accepts. Explicit weather lat/lon inputs are not promoted to itinerary coordinate evidence. Weather dates use UTC. Requests crossing the forecast boundary split into forecast/archive groups. Each output day has both the requested date and basis_date. February 29 maps to February 28 in a non-leap baseline year. Past dates use actual archived dates and the historical label. Unavailable baseline dates (including dates still in the future), missing city matches and missing daily series yield no_data. A five-day archive freshness margin is used conservatively.

Typical means one previous year's observations, not a multi-year climate average or a prediction. Weather output includes Open-Meteo/GeoNames attribution. Use the public Open-Meteo service for this non-commercial demo under its free-use terms.

Frankfurter's current public base URL is https://api.frankfurter.dev; the implementation uses /v2/rates with base, quotes and optional date. Conversion happens locally using the returned reference rate; this is not a live trading price. Same-currency conversion is the identity operation without HTTP. Future rate dates are rejected. Latest/historical observations may precede the requested date (weekends/holidays), so rate_date is always included.

References: [Frankfurter documentation](https://frankfurter.dev/), [Open-Meteo forecast](https://open-meteo.com/en/docs), [archive](https://open-meteo.com/en/docs/historical-weather-api), [city geocoding](https://open-meteo.com/en/docs/geocoding-api).

## Nominatim usage policy and setup — M4

Read the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/) before live use. Public-service requests must be user-triggered, low-volume searches, with at most one request per second across the application, an identifying User-Agent and visible OSM attribution. Do not use this tool for autocomplete, systematic place harvesting or bulk geocoding.

Export NOMINATIM_USER_AGENT with your application's identity and a real contact method. No default contact is invented; missing configuration returns a configuration error before HTTP. NOMINATIM_URL can change the endpoint without code changes. Use a single application host: a disk flock and timestamp under the OS temporary directory serialize all processes on that host, including retries, to at most one request start per second. This does not coordinate separate hosts; multi-host deployment requires a shared limiter or a self-hosted service. Attribution is returned in data and must be displayed by any consuming UI.

The HTTP cache is persisted in Postgres and includes empty results. Cache hits bypass HTTP and geocoding throttling. cache_hit is true only when every HTTP dependency was cached. fetched_at retains the oldest contributing fetch time on cache hits, rather than claiming fresh observations. Expired entries are ignored and overwritten when reused; no scheduled purge job is installed.

## Synthetic inventory limitations

Flight/hotel data and availability descriptions are explicitly labeled synthetic-v1. They are not offers, reservations or real room/seat availability. Flight max_price applies separately to each leg. A round trip requires a matching inbound row; the current generator only supplies US-to-destination flights, so return-date queries normally yield no_data rather than an invented return leg.

Hotels are seasonal quotes, not date-specific inventory. Requested dates determine the number of nights and total quoted amount, not stock availability or newly modeled seasonal prices. Both nightly and full-stay quote values are available as price evidence; the caller must select the appropriate unit when assembling items.

## Itinerary validation

The Itinerary schema defines trip dates/currency, dated days and items with local wall-clock start/end datetimes, place, category, optional cost, currency, chunk_ids, tool_result_ids and optional coords/coord_tool_result_id. Offset-aware timestamps are rejected to avoid mixed timezone comparisons. Visiting hours default to 08:00–22:00; allow_outside_visiting_window is an explicit per-item exception.

Schema errors return a named schema_valid error issue. Other named issues include budget_exceeded, overlap, outside_visiting_window, day_outside_trip_dates, item_outside_day_or_trip, missing_tool_result_id, price_must_match_tool_result, currency_mismatch, coordinates_must_match_geocode_result and travel_time_implausible. Missing verified coordinates yield the warning travel_check_skipped_without_coords. Unpriced items yield unpriced_item warnings and are excluded from the total. valid means no error issues; warnings remain visible. Duplicate days and item IDs are rejected.

Budget is expressed in trip.currency; mixed-currency priced items are errors and total_cost is null rather than an invalid cross-currency sum. Each non-null cost, including zero, must match a price in a successful stored flight/hotel ToolResult within 0.01 and with the same currency. Currency conversion results alone cannot establish a quoted price. Coordinates must match a successful geocode_place ToolResult within 0.000001 degrees. The ledger is trusted server-side data, not input supplied alongside the itinerary.

Consecutive items use haversine distance and the next item's travel_mode: walking at 5 km/h or transit at 25 km/h. This is a plausibility heuristic, not a route planner or transit timetable. It skips the check with a warning when either coordinate reference is missing or invalid. Overlap detection includes nested intervals and items across day entries. This validator establishes value provenance, not a booking, freshness guarantee or semantic match between a quote and an attraction name.

## Run locally

```bash
source venv/bin/activate
export PYTHONPATH=.
python -m pip install -r requirements-dev.txt
alembic -c backend/alembic.ini upgrade head
make test-tools
pytest -q -m integration tests/test_agent_tools_integration.py
python -m backend.tools.cli schemas
python -m backend.tools.cli search_hotels --city Lisbon --check_in 2027-04-10 --check_out 2027-04-15 --max_price_per_night 120
```

Inventory queries need migrated/seeded local Postgres. Destination retrieval also needs the populated RAG corpus and cached embedding/reranker models. HTTP tools need network access at runtime; all unit tests use synthetic fixtures, respx and a live-socket guard. Nominatim additionally needs M4 configuration. validate_itinerary accepts --json with an input object or --itinerary with JSON and --budget; evidence must already exist in the server ledger.

The cache/result migration is 20261102_agent_tools. The integration test creates an isolated temporary schema, tests cache expiry and result persistence, and removes that schema afterward. It does not migrate or seed the application's normal schema.
