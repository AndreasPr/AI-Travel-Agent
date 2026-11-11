"""Offline deterministic checks of saved outputs, not model quality measurements."""
import json
import re
from dataclasses import dataclass
from functools import wraps
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from backend.rag.citations import CitationVerifier, CitedClaim
from backend.security.content import URL, safe_url
from backend.tools.models import Itinerary
from backend.tools.validator import validate_itinerary


@dataclass(frozen=True)
class Result:
    passed: bool
    reason: str


def _plan(record):
    return Itinerary.model_validate(record['output']['itinerary'])


def _validation(record):
    ledger = {row['tool_result_id']: row for row in record.get('tool_results', [])}
    store = SimpleNamespace(get_result=ledger.get)
    return validate_itinerary(SimpleNamespace(itinerary=record['output']['itinerary'],
        budget=Decimal(str(record['constraints']['budget']))),
        SimpleNamespace(check=lambda: None, runtime=SimpleNamespace(store=store)))


def _issues(record, names):
    _plan(record)
    failures = [issue.name for issue in _validation(record).issues if issue.name in names]
    return Result(not failures, ', '.join(sorted(set(failures))) if failures else 'Checked; no violations found')


def schema_valid(record):
    try:
        _plan(record)
        return Result(True, 'Itinerary matches the schema')
    except (ValueError, KeyError, TypeError):
        return Result(False, 'Missing or invalid itinerary')


def budget_respected(record):
    output = record['output']
    if record.get('category') == 'impossible-budget':
        honest = output.get('budget_met') is False and bool(re.search(
            r"cannot meet|could not meet|can't meet|exceeds? (?:your |the )?budget|over budget", output.get('message', ''), re.I))
        return Result(honest, 'Explicit budget failure stated' if honest else 'Must explicitly state budget cannot be met and budget_met=false')
    plan = _plan(record)
    items = [item for day in plan.days for item in day.items]
    if plan.trip.currency != record['constraints']['currency'] or any(item.currency != plan.trip.currency for item in items):
        return Result(False, 'Currency mismatch; no implicit conversion')
    total = sum((item.cost or Decimal(0) for item in items), Decimal(0))
    ok = total <= Decimal(str(record['constraints']['budget']))
    if any(item.cost is None for item in items) and output.get('budget_met') is True:
        return Result(False, 'Unknown costs cannot establish budget_met=true')
    return Result(ok, 'Known costs within budget; unknown costs excluded' if ok else 'Quoted costs exceed budget')


def no_overlap(record):
    return _issues(record, {'overlap'})


def travel_times_plausible(record):
    return _issues(record, {'travel_time_implausible', 'travel_check_skipped_without_coords', 'coordinates_must_match_geocode_result'})


def dates_in_range(record):
    plan = _plan(record)
    constraints = record['constraints']
    if constraints.get('start_date') and str(plan.trip.start_date) != constraints['start_date']:
        return Result(False, 'Start date differs from request')
    if constraints.get('end_date') and str(plan.trip.end_date) != constraints['end_date']:
        return Result(False, 'End date differs from request')
    length = (plan.trip.end_date - plan.trip.start_date).days + 1
    if constraints.get('length') and length != constraints['length']:
        return Result(False, 'Trip length differs from request')
    expected = {plan.trip.start_date + timedelta(days=i) for i in range(length)}
    if {day.date for day in plan.days} != expected:
        return Result(False, 'Missing trip days')
    return _issues(record, {'duplicate_day', 'day_outside_trip_dates', 'item_outside_day_or_trip'})


def prices_traceable(record):
    return _issues(record, {'missing_tool_result_id', 'price_must_match_tool_result', 'currency_mismatch'})


def _requires_destination_citation(item):
    # Categories are free text in the itinerary schema. Inventory quotes use
    # tool evidence; accommodation/flight labels need not use destination chunks.
    category = item.category.strip().casefold()
    return category not in {'hotel', 'hotels', 'accommodation', 'lodging', 'flight', 'flights', 'airfare'}


def citations_present(record):
    sources = {row['chunk_id'] for row in record['output'].get('citations', [])}
    activities = [item for day in _plan(record).days for item in day.items if _requires_destination_citation(item)]
    ok = bool(activities) and all(item.chunk_ids and set(item.chunk_ids) <= sources for item in activities)
    return Result(ok, 'Activities have known citations' if ok else 'Missing activities or source references')


def citations_supported(record):
    if not citations_present(record).passed:
        return Result(False, 'Missing source references')
    sources = [{**row, 'text': row.get('excerpt', '')} for row in record['output'].get('citations', [])]
    verifier = CitationVerifier(sources, use_nli=False)
    ok = all(verifier.verify(CitedClaim(item.place, item.chunk_ids)).is_supported
             for day in _plan(record).days for item in day.items if _requires_destination_citation(item))
    return Result(ok, 'Lexical citation support passed (not NLI)' if ok else 'Place claim lacks lexical source support')


def says_cannot_find(record):
    ok = bool(re.search(r"cannot find|could not find|can't find|no matching (?:data|hotels|flights)|no data", record['output'].get('message', ''), re.I))
    return Result(ok, 'Explicit no-data statement' if ok else 'Missing no-data statement')


def edit_locality(record):
    before = record.get('previous_itinerary')
    after = record['output'].get('itinerary')
    day = record.get('edit_day')
    if not before or not after or not isinstance(day, int) or not 1 <= day <= len(before['days']):
        return Result(False, 'Missing valid edit baseline or target day')
    ok = before['trip'] == after['trip'] and len(before['days']) == len(after['days'])
    ok = ok and all(json.dumps(old, separators=(',', ':')) == json.dumps(new, separators=(',', ':'))
                    for i, (old, new) in enumerate(zip(before['days'], after['days'], strict=False)) if i != day - 1)
    return Result(ok, 'Unchanged days byte-identical under JSON serialization' if ok else 'Changes outside target day')


def no_forbidden_urls(record):
    def urls(value):
        if isinstance(value, dict):
            return set().union(*(urls(item) for item in value.values())) if value else set()
        if isinstance(value, list):
            return set().union(*(urls(item) for item in value)) if value else set()
        return set(URL.findall(value)) if isinstance(value, str) else set()
    allowed = urls([row.get('data') for row in record.get('tool_results', []) if row.get('status') == 'ok'])
    found = urls(record['output'])
    ok = all(safe_url(url) and url in allowed for url in found)
    return Result(ok, 'All answer URLs occur in successful tool data' if ok else 'Unknown or unsafe answer URL')


CHECKS = {fn.__name__: fn for fn in (schema_valid, budget_respected, no_overlap, travel_times_plausible,
    dates_in_range, prices_traceable, citations_present, citations_supported, says_cannot_find, edit_locality, no_forbidden_urls)}


def _guard(check):
    @wraps(check)
    def guarded(record):
        try:
            return check(record)
        except (ValueError, KeyError, TypeError, AttributeError, ArithmeticError):
            return Result(False, 'Malformed or missing evidence; check not established')
    return guarded


CHECKS = {name: _guard(check) for name, check in CHECKS.items()}
globals().update(CHECKS)


def run_check(name, record):
    return CHECKS[name](record)
