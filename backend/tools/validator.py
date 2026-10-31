"""Deterministic itinerary checks against the trusted server-side ToolResult ledger."""
import math
from datetime import time
from decimal import Decimal

from pydantic import ValidationError

from backend.tools.models import Issue, Itinerary, ValidateOutput


def haversine_km(a, b):
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    term = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(b.lon - a.lon) / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(max(0, term))))


def quoted_prices(result):
    data = result.get("data") or {}
    if result.get("tool") == "search_flights":
        return [(Decimal(str(row["price"])), row["currency"]) for row in data.get("outbound", []) + data.get("inbound", [])]
    if result.get("tool") == "search_hotels":
        return [(Decimal(str(row[key])), row["currency"]) for row in data.get("hotels", []) for key in ("price_per_night", "total_price")]
    return []


def validate_itinerary(request, ctx):
    issues = []

    def add(name, message, *items, severity="error"):
        issues.append(Issue(name=name, message=message, item_ids=[item.id for item in items], severity=severity))

    try:
        itinerary = Itinerary.model_validate(request.itinerary)
    except ValidationError:
        return ValidateOutput(valid=False, total_cost=None, currency=None,
                              issues=[Issue(name="schema_valid", severity="error", message="Itinerary does not match the schema or contains invalid time/date values")])
    items, results, verified_coords = [], {}, set()

    def lookup(result_id):
        if result_id not in results:
            ctx.check()
            results[result_id] = ctx.runtime.store.get_result(result_id)
        result = results[result_id]
        return result if result and result.get("status") == "ok" else None

    day_dates = set()
    for day in itinerary.days:
        if day.date in day_dates:
            add("duplicate_day", "A trip day is repeated")
        day_dates.add(day.date)
        if not itinerary.trip.start_date <= day.date <= itinerary.trip.end_date:
            add("day_outside_trip_dates", "Day is outside the trip dates")
        for item in day.items:
            items.append(item)
            if item.start.date() != day.date or not (itinerary.trip.start_date <= item.start.date() <= item.end.date() <= itinerary.trip.end_date):
                add("item_outside_day_or_trip", "Item dates do not match the trip/day", item)
            if not item.allow_outside_visiting_window and (item.start.time() < time(8) or item.end.time() > time(22) or item.end.date() != item.start.date()):
                add("outside_visiting_window", "Item is outside 08:00–22:00 without an exception", item)
            if item.cost is not None:
                if not item.tool_result_ids:
                    add("missing_tool_result_id", "Priced item must reference a ToolResult", item)
                else:
                    evidence = [lookup(result_id) for result_id in item.tool_result_ids]
                    if not any(evidence):
                        add("missing_tool_result_id", "No successful stored ToolResult exists for the supplied IDs", item)
                    elif not any(abs(amount - item.cost) <= Decimal("0.01") and currency == item.currency
                                 for result in evidence if result for amount, currency in quoted_prices(result)):
                        add("price_must_match_tool_result", "Cost/currency does not match a quoted value within 0.01", item)
                if item.currency != itinerary.trip.currency:
                    add("currency_mismatch", "Budget requires costs in the trip currency; conversion must be explicit", item)
            else:
                add("unpriced_item", "Item has no cost; total excludes it", item, severity="warning")
            if item.coords is not None:
                result = lookup(item.coord_tool_result_id) if item.coord_tool_result_id else None
                data = result.get("data", {}) if result else {}
                if (result and result.get("tool") == "geocode_place" and
                        abs(float(data["lat"]) - item.coords.lat) <= 0.000001 and abs(float(data["lon"]) - item.coords.lon) <= 0.000001):
                    verified_coords.add(item.id)
                else:
                    add("coordinates_must_match_geocode_result", "Coordinates need a matching geocode_place ToolResult", item)
    if len({item.id for item in items}) != len(items):
        add("duplicate_item_id", "Item IDs must be unique")
    compatible = all(item.currency == itinerary.trip.currency for item in items if item.cost is not None)
    total = sum((item.cost for item in items if item.cost is not None), Decimal("0")) if compatible else None
    if total is not None and total > request.budget:
        add("budget_exceeded", "Total quoted cost exceeds the budget")
    ordered = sorted(items, key=lambda item: (item.start, item.end, item.id))
    active = []
    for item in ordered:
        active = [prior for prior in active if prior.end > item.start]
        for prior in active:
            add("overlap", "Items overlap in time", prior, item)
        active.append(item)
    for prior, current in zip(ordered, ordered[1:], strict=False):
        if prior.id not in verified_coords or current.id not in verified_coords:
            add("travel_check_skipped_without_coords", "Travel-time check skipped: verified coordinates missing", prior, current, severity="warning")
            continue
        distance = haversine_km(prior.coords, current.coords)
        minutes = distance / (5 if current.travel_mode == "walking" else 25) * 60
        available = (current.start - prior.end).total_seconds() / 60
        if minutes > max(0, available) + 0.000001:
            add("travel_time_implausible", "Gap is too short at the configured walking/transit speed", prior, current)
    return ValidateOutput(valid=not any(issue.severity == "error" for issue in issues), total_cost=total, currency=itinerary.trip.currency, issues=issues)
