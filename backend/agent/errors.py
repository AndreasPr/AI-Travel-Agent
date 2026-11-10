"""Safe diagnostic categories without provider payloads or exception text."""
from pydantic import ValidationError

from backend.llm.types import InvalidOutput, ProviderUnavailable, QuotaExhausted, RateLimited


def failure_issue(exc, stage):
    from backend.security.limits import LimitExceeded
    if isinstance(exc, LimitExceeded):
        name, message = 'usage_limit', 'The session, user or turn token limit has been reached.'
    elif isinstance(exc, TimeoutError):
        name, message = 'provider_timeout', 'The provider exceeded the response deadline.'
    elif isinstance(exc, InvalidOutput):
        # These adapter messages are fixed literals; never echo arbitrary exception text.
        known = {
            'Provider returned invalid JSON': ('invalid_json', 'The provider returned invalid JSON.'),
            'Output does not satisfy the JSON schema': ('schema_validation', 'The provider response did not match the required schema.'),
            'No grounded activity places were extracted': ('activity_extraction', 'No named attractions could be verified against the retrieved excerpts.'),
        }
        name, message = known.get(str(exc), ('invalid_output', 'The provider output was rejected.'))
    elif isinstance(exc, ValidationError):
        name, message = 'schema_validation', 'The response did not match the required schema.'
    elif isinstance(exc, QuotaExhausted):
        name, message = 'quota_exhausted', 'The configured provider quota is exhausted.'
    elif isinstance(exc, RateLimited):
        name, message = 'rate_limited', 'The provider is rate limited.'
    elif isinstance(exc, ProviderUnavailable):
        name, message = 'provider_unavailable', 'The provider could not be reached or was unavailable.'
    else:
        name, message = 'configuration_or_context', 'The provider configuration or context could not be accepted.'
    return {'name': name, 'severity': 'error', 'stage': stage, 'message': message}


def public_failure_detail(issues):
    """Select only fixed explanations; never expose provider or tool payloads."""
    explanations = {
        'activity_extraction': 'No named attractions could be verified against the retrieved excerpts.',
        'invalid_json': 'The model returned invalid JSON.',
        'schema_validation': 'The model output did not match the itinerary schema.',
        'incomplete_itinerary': 'The generated itinerary did not cover every requested day.',
        'requested_citations_missing': 'The generated activities lacked the required source citations.',
        'untrusted_citation': 'The generated itinerary referenced sources that were not retrieved.',
        'untrusted_tool_result': 'The generated itinerary referenced unknown tool results.',
        'validation_unavailable': 'The itinerary validation tool could not complete.',
        'invalid_output': 'The provider output was rejected.',
    }
    for issue in issues:
        if issue.get('severity') != 'error':
            continue
        for key in ('reason', 'name'):
            code = issue.get(key)
            if isinstance(code, str) and code in explanations:
                return explanations[code]
    return 'The itinerary failed validation; no validated plan was returned.'


def validation_details(exc, allowed_fields=()):
    """Report schema locations and known validator rules without rejected values."""
    known_rules = {
        'Use local wall-clock datetimes without offsets',
        'Item end must follow start',
        'Trip end precedes start',
        'Stay must be between 1 and 365 nights',
        'Return date precedes departure',
        'Supply city or lat/lon, not both',
        'Supply city or both lat and lon',
        'Weather date range must be ordered and at most 32 days',
    }
    fields = {'trip', 'days', 'items', 'start_date', 'end_date', 'start', 'end', 'place', 'category',
              'cost', 'currency', 'id', 'chunk_ids', 'tool_result_ids', 'coords', 'lat', 'lon',
              'coord_tool_result_id', 'allow_outside_visiting_window', 'travel_mode', 'day', 'operations', 'op', 'item', 'item_id'}
    fields.update(allowed_fields)
    details = []
    for error in exc.errors(include_input=False, include_url=False):
        path = [part if isinstance(part, int) or part in fields else '[field]' for part in error['loc']]
        rule = str(error.get('ctx', {}).get('error', ''))
        details.append({'path': path, 'type': error['type'],
                        'message': rule if rule in known_rules else 'Correct this field to match the schema.'})
    return details
