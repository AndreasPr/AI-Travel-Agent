"""Argument provenance: retrieved prose never grants a tool permission."""
import json
import re

from backend.security.content import sanitize_text

# Only typed result fields can contribute facts. Never use excerpts, titles or URLs.
FACT_FIELDS = {'city', 'country', 'origin', 'destination', 'destination_city', 'origin_city', 'name',
               'display_name', 'date', 'flight_date', 'check_in', 'check_out', 'lat', 'lon',
               'currency', 'from_currency', 'to_currency', 'amount', 'tier', 'rating'}
DEFAULTS = {'k': 5}


def facts_from(results):
    values = []
    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in FACT_FIELDS and isinstance(item, (str, int, float)):
                    values.append(str(item))
                elif isinstance(item, (dict, list)):
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    for row in results:
        if row.get('status') == 'ok' and row.get('tool') != 'search_destinations':
            walk(row.get('data'))
    return values


def contains(text, value):
    return bool(re.search(r'(?<!\w)' + re.escape(str(value).casefold()) + r'(?!\w)', text.casefold()))


def step_tools(allowed, request, results):
    request = request_facts(request)
    allowed = set(allowed)
    # Flights always need an explicitly supplied origin; retrieved text cannot add one.
    if not re.search(r'\b(?:flight|flights|fly|airfare)\b', request, re.I) or not re.search(r'\b(?:from|origin)\s+([A-Z]{3})\b', request):
        allowed.discard('search_flights')
    for name, pattern in (
        ('geocode_place', r'\b(?:coordinates?|geocod\w*|map|walking|travel time|transit)\b'),
        ('get_weather', r'\b(?:weather|forecast|rain|temperature)\b'),
        ('convert_currency', r'\b(?:convert|exchange|currency conversion)\b'),
    ):
        if not re.search(pattern, request, re.I):
            allowed.discard(name)
    # Per-step permissions are recomputed from the snapshot before parallel execution.
    if not request.strip() and not facts_from(results):
        return set()
    return allowed


def authorize_arguments(name, arguments, request, results):
    if not isinstance(arguments, dict):
        raise ValueError('Tool arguments must be an object')
    request = request_facts(request)
    result = dict(arguments)
    if name == 'search_flights' and 'origin' in result:
        origin = re.search(r'\b(?:from|origin)\s+([A-Z]{3})\b', request)
        if not origin or result['origin'] != origin.group(1):
            raise ValueError('Flight origin must be explicitly requested')
    facts = facts_from(results)
    for key, value in result.items():
        if key == 'query' and name == 'search_destinations':
            # Queries are generated from trusted request context, never copied from a chunk.
            result[key] = sanitize_text(request, 1000)
            continue
        if value is None or (key in DEFAULTS and value == DEFAULTS[key]):
            continue
        if isinstance(value, (dict, list)) or not (contains(request, value) or str(value) in facts):
            raise ValueError('Argument lacks trusted provenance')
        # Boolean defaults and numeric coercion remain the tool's Pydantic responsibility.
    # ToolRuntime performs complete schema validation, including required fields.
    return result


def explicit_budget(value, request):
    from decimal import Decimal
    request = request_facts(request)
    match = re.search(r'(?i)\b(?:budget(?: of| is|:)?|under|up to|maximum)\s*[$€£]?\s*(\d[\d,]*(?:\.\d{1,2})?)', request)
    if match is None:
        match = re.search(r'\b(\d[\d,]*(?:\.\d{1,2})?)\s*(?:USD|EUR|GBP)\b', request, re.I)
    return Decimal(match.group(1).replace(',', '')) if match else None


def request_facts(request):
    # Quoted notes and role-like markup do not authorize executable parameters.
    return re.split(r'(?i)\bnotes\s*:|```|<\s*(?:system|data|tool|assistant)\b', request, maxsplit=1)[0]


def trusted_urls(citations):
    return {row['url'] for row in citations if row.get('url')}


def candidate_has_unknown_url(candidate, allowed):
    from backend.security.content import allow_urls
    encoded = json.dumps(candidate, ensure_ascii=False)
    return allow_urls(encoded, allowed) != encoded
