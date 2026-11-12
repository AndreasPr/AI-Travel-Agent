"""Explicit request requirements and server-owned identifiers."""
import re
from datetime import date


def requested_hotels(message):
    return bool(re.search(r'\b(hotels?|accommodations?)\b', message, re.I)) and not bool(
        re.search(r"\b(no|without|exclude|skip)\s+(?:any\s+)?(?:hotels?|accommodations?)\b", message, re.I))


def requested_dates(message):
    values = re.findall(r'\b\d{4}-\d{2}-\d{2}\b', message)
    if len(values) != 2:
        return None
    try:
        start, end = (date.fromisoformat(value) for value in values)
    except ValueError:
        return None
    return (start.isoformat(), end.isoformat()) if start <= end else None


def assign_item_ids(candidate):
    # IDs are application identifiers, not generated travel facts or quote references.
    for day in candidate['days']:
        for index, item in enumerate(day['items'], start=1):
            item['id'] = f"{day['date']}:item:{index}"


def requirement_issues(candidate, message, hotel_results, citations=()):
    issues = []
    dates = requested_dates(message)
    if dates and (candidate['trip']['start_date'], candidate['trip']['end_date']) != dates:
        issues.append({'name': 'requested_dates_mismatch', 'severity': 'error', 'message': f'Use the requested trip dates {dates[0]} through {dates[1]}.'})
    if requested_hotels(message) and hotel_results:
        if not any(item['cost'] is not None and set(item['tool_result_ids']) & hotel_results
                   for day in candidate['days'] for item in day['items']):
            issues.append({'name': 'requested_hotel_quote_missing', 'severity': 'error',
                           'message': 'Include an accommodation item using a retrieved hotel quote, its exact total or nightly price, and its tool_result_id. Do not omit the requested hotel quote.'})
    if requested_retrieval(message) and citations and not any(item['chunk_ids'] for day in candidate['days'] for item in day['items']):
        issues.append({'name': 'requested_citations_missing', 'severity': 'error', 'message': 'Cite retrieved destination chunks for the requested activities using chunk_ids.'})
    return issues


def requested_retrieval(message):
    return bool(re.search(r'\b(museums?|food|restaurants?|history|art|sights?|attractions?|nature|beaches?)\b', message, re.I))


def requested_city(message):
    from pathlib import Path
    import yaml
    cities = yaml.safe_load((Path(__file__).resolve().parents[2] / 'config/cities.yaml').read_text())['cities']
    matches = [row['name'] for row in cities if re.search(r'\b' + re.escape(row['name']) + r'\b', message, re.I)]
    return matches[0] if len(matches) == 1 else None


def bind_tool_definitions(definitions, message):
    from copy import deepcopy
    result = deepcopy(definitions)
    dates, city = requested_dates(message), requested_city(message)
    for tool in result:
        props = tool['parameters'].get('properties', {})
        if city and tool['name'] in {'search_hotels', 'search_destinations'}:
            props['city'] = {'type': 'string', 'enum': [city]}
        if tool['name'] == 'search_hotels':
            # Do not ask the model to invent optional price, rating or tier filters.
            for field, pattern in (('max_price_per_night', r'per night|nightly'), ('min_rating', r'rating|stars?'), ('tier', r'budget hotel|mid|upscale')):
                if field in props and not re.search(pattern, message, re.I):
                    props[field] = {'type': 'null'}
        if dates and tool['name'] == 'search_hotels' and dates[0] != dates[1]:
            props['check_in'] = {'type': 'string', 'enum': [dates[0]]}
            props['check_out'] = {'type': 'string', 'enum': [dates[1]]}
    return result


def bind_itinerary_schema(schema, message, results, citations, original=None, edit_day=None, activity_places=()):
    from backend.agent.providers import generation_schema
    from backend.tools.validator import quoted_prices
    from datetime import timedelta
    result = generation_schema(schema)
    item = result['$defs']['Item']['properties']
    if activity_places:
        item['place'] = {'type': 'string', 'enum': list(activity_places)}
    quote_ids = [row['tool_result_id'] for row in results if quoted_prices(row)]
    prices = [None]
    for row in results:
        for price, _ in quoted_prices(row):
            prices.extend([str(price), float(price)])
    item['cost']['enum'] = list(dict.fromkeys(prices))
    item['tool_result_ids'] = {'type': 'array', 'items': {'type': 'string', 'enum': quote_ids}} if quote_ids else {'type': 'array', 'maxItems': 0, 'items': {'type': 'string'}}
    chunk_ids = sorted({row['chunk_id'] for row in citations})
    item['chunk_ids'] = {'type': 'array', 'items': {'type': 'string', 'enum': chunk_ids}} if chunk_ids else {'type': 'array', 'maxItems': 0, 'items': {'type': 'string'}}
    coordinates = [row['tool_result_id'] for row in results if row.get('tool') == 'geocode_place']
    if not coordinates:
        item['coords'] = {'type': 'null'}
        item['coord_tool_result_id'] = {'type': 'null'}
    else:
        item['coord_tool_result_id'] = {'enum': [None, *coordinates]}
    dates = requested_dates(message)
    if dates and 'Trip' in result['$defs']:
        props = result['$defs']['Trip']['properties']
        props['start_date'], props['end_date'] = ({'type': 'string', 'enum': [value]} for value in dates)
        count = (date.fromisoformat(dates[1]) - date.fromisoformat(dates[0])).days + 1
        date_choices = '|'.join((date.fromisoformat(dates[0]) + timedelta(days=i)).isoformat() for i in range(count))
        for field in ('start', 'end'):
            item[field]['pattern'] = '^(' + date_choices + r')T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]$'
        result['properties']['days'].update(minItems=count, maxItems=count)
        result['$defs']['Day']['properties']['date'] = {'type': 'string', 'enum': [(date.fromisoformat(dates[0]) + timedelta(days=i)).isoformat() for i in range(count)]}
    if original and edit_day and 1 <= edit_day <= len(original['days']):
        result['properties']['day'] = {'type': 'integer', 'enum': [edit_day]}
        ids = [row['id'] for row in original['days'][edit_day - 1]['items']]
        result['$defs']['PatchOperation']['properties']['item_id'] = {'enum': [None, *ids]}
        target_items = original['days'][edit_day - 1]['items']
        if target_items and all(row['cost'] is None for row in target_items) and re.search(r'\bcheaper\b', message, re.I):
            operation = result['$defs']['PatchOperation']
            operation['properties']['op'] = {'const': 'remove_item'}
            operation['properties']['item_id'] = {'type': 'string', 'enum': ids}
            operation['properties']['item'] = {'type': 'null'}
            operation['required'] = ['op', 'item_id']
            result['properties']['operations'].update(minItems=1, maxItems=1)
    # Bind hotel identity and price together; unrelated activities remain unpriced.
    hotel_rows = [(row['tool_result_id'], hotel) for row in results
                  if row.get('tool') == 'search_hotels' and row.get('status') == 'ok'
                  for hotel in row['data'].get('hotels', []) if 'name' in hotel]
    if hotel_rows and all(row.get('tool') == 'search_hotels' for row in results if quoted_prices(row)):
        from copy import deepcopy
        base = result['$defs']['Item']
        unpriced = deepcopy(base)
        unpriced['properties']['cost'] = {'type': 'null'}
        if activity_places:
            unpriced['properties']['place'] = {'type': 'string', 'enum': list(activity_places)}
        if activity_places or (chunk_ids and requested_retrieval(message)):
            unpriced['properties']['chunk_ids']['minItems'] = 1
            unpriced['required'] = list(dict.fromkeys([*unpriced['required'], 'chunk_ids']))
        unpriced['required'] = list(dict.fromkeys([*unpriced['required'], 'cost']))
        variants = [unpriced]
        for key, hotel in hotel_rows:
            variant = deepcopy(base)
            props = variant['properties']
            props['place'] = {'type': 'string', 'enum': [hotel['name']]}
            props['category'] = {'const': 'hotel'}
            props['currency'] = {'type': 'string', 'enum': [hotel['currency']]}
            props['cost'] = {'type': 'string', 'enum': [str(hotel['total_price'])] if dates and 'days' in result['properties'] else [str(hotel['price_per_night']), str(hotel['total_price'])]}
            props['tool_result_ids'] = {'type': 'array', 'items': {'type': 'string', 'enum': [key]}, 'minItems': 1, 'maxItems': 1}
            variant['required'] = list(dict.fromkeys([*variant['required'], 'cost', 'tool_result_ids']))
            variants.append(variant)
        if activity_places:
            grounded_variants = []
            for place in activity_places:
                grounded = deepcopy(unpriced)
                grounded['properties']['place'] = {'const': place}
                grounded['properties']['chunk_ids']['items']['enum'] = [
                    row['chunk_id'] for row in citations
                    if place.casefold() in row.get('excerpt', '').casefold()]
                grounded_variants.append(grounded)
            # Each union branch is a complete object schema. Partial properties
            # alongside anyOf can yield incomplete objects in local grammars.
            unpriced = {'anyOf': grounded_variants}
        result['$defs']['UnpricedItem'] = unpriced
        result['$defs']['QuotedHotelItem'] = {'anyOf': variants[1:]}
        result['$defs']['Item'] = {'anyOf': [{'$ref': '#/$defs/UnpricedItem'}, {'$ref': '#/$defs/QuotedHotelItem'}]}
        if dates and requested_hotels(message) and 'days' in result['properties']:
            day_schemas = []
            for index in range(count):
                day_schema = deepcopy(result['$defs']['Day'])
                day_schema['properties']['date'] = {'const': (date.fromisoformat(dates[0]) + timedelta(days=index)).isoformat()}
                if index == 0:
                    day_schema['properties']['items'].pop('items', None)
                    day_schema['properties']['items']['prefixItems'] = [{'$ref': '#/$defs/QuotedHotelItem'}, {'$ref': '#/$defs/UnpricedItem'}]
                    day_schema['properties']['items']['minItems'] = 2
                    day_schema['properties']['items']['maxItems'] = 2
                else:
                    day_schema['properties']['items']['items'] = {'$ref': '#/$defs/UnpricedItem'}
                day_schemas.append(day_schema)
            result['properties']['days'].pop('items', None)
            result['properties']['days']['prefixItems'] = day_schemas
    return result


def scoped_tools(allowed, message, original_request=''):
    context = original_request + ' ' + message
    if not requested_city(context) or not requested_dates(original_request or message):
        return allowed
    selected = set()
    if requested_hotels(context) or re.search(r'\bcheaper\b', message, re.I):
        selected.add('search_hotels')
    if requested_retrieval(context):
        selected.add('search_destinations')
    for name, pattern in [('search_flights', r'\b(flights?|fly|airfare)\b'),
                          ('get_weather', r'\b(weather|forecast|rain|temperature)\b'),
                          ('convert_currency', r'\b(convert|exchange|currency conversion)\b'),
                          ('geocode_place', r'\b(coordinates?|geocod\w*|walking|travel time|transit)\b')]:
        if re.search(pattern, context, re.I):
            selected.add(name)
    return allowed & selected if selected else allowed


def quoted_item_issues(candidate, results):
    """A hotel quote cannot be relabeled as an unrelated priced activity."""
    from decimal import Decimal
    hotels = {row['tool_result_id']: row['data'].get('hotels', []) for row in results if row.get('tool') == 'search_hotels'}
    issues = []
    for day in candidate['days']:
        for item in day['items']:
            if item['cost'] is None:
                continue
            rows = [row for key in item['tool_result_ids'] for row in hotels.get(key, []) if 'name' in row]
            if rows and not any(item['place'] == row['name'] and item['currency'] == row['currency'] and
                                any(abs(Decimal(str(item['cost'])) - Decimal(str(row[field]))) <= Decimal('0.01') for field in ('price_per_night', 'total_price')) for row in rows):
                issues.append({'name': 'hotel_quote_item_mismatch', 'severity': 'error', 'item_ids': [item['id']],
                               'message': 'Use the quoted hotel exact name, currency and price. A hotel quote cannot price a museum, meal or other place.'})
    return issues


def substantive_itinerary(candidate):
    from copy import deepcopy
    result = deepcopy(candidate)
    for day in result['days']:
        for item in day['items']:
            for key in ('id', 'chunk_ids', 'tool_result_ids', 'coord_tool_result_id'):
                item.pop(key, None)
    return result


def grounded_activity_issues(candidate, citations):
    """Require each cited place name in at least one of its actual excerpts."""
    chunks = {row['chunk_id']: row.get('excerpt', '') for row in citations}
    issues = []
    for day in candidate['days']:
        for item in day['items']:
            if item['cost'] is not None or not item['chunk_ids']:
                continue
            if citations and not any(item['place'].strip().casefold() in chunks.get(key, '').casefold()
                                     for key in item['chunk_ids']):
                issues.append(dict(name='unsupported_activity', severity='error', item_ids=[item['id']],
                                   message='Copy the place name from its cited excerpt and use that excerpt ID.'))
    return issues


def separate_generated_visits(candidate, message):
    """Pack generated visits; represent hotel accommodation as a short check-in.

    Explicit user times are never moved; impossible schedules remain validator errors.
    This does not establish travel-time feasibility.
    """
    from datetime import datetime, time, timedelta
    if re.search(r'\b\d{1,2}:\d{2}\b|\b\d{1,2}\s*(?:am|pm)\b', message, re.I):
        return
    for day in candidate['days']:
        end = None
        for item in sorted(day['items'], key=lambda item: item['start']):
            start, finish = datetime.fromisoformat(item['start']), datetime.fromisoformat(item['end'])
            # Accommodation appears as a check-in visit, not a multi-day activity
            # blocking every subsequent visit; the quote still covers its stay.
            overlaps = any(other is not item and start < datetime.fromisoformat(other['end'])
                           and finish > datetime.fromisoformat(other['start']) for other in day['items'])
            if item['category'].casefold() == 'hotel' and (finish.date() != start.date() or overlaps):
                finish = start + timedelta(minutes=30)
                item['end'] = finish.isoformat()
            if end is not None and start < end and start.date() == end.date():
                shifted = end + (finish-start)
                if shifted.date() == start.date() and shifted.time() <= time(22):
                    start, finish = end, shifted
                    item['start'], item['end'] = start.isoformat(), finish.isoformat()
            end = max(end, finish) if end is not None else finish
