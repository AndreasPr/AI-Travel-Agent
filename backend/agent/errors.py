"""Safe diagnostic categories without provider payloads or exception text."""
from pydantic import ValidationError

from backend.llm.types import InvalidOutput, ProviderUnavailable, QuotaExhausted, RateLimited, RequestRejected


def failure_issue(exc, stage):
    from backend.security.limits import LimitExceeded
    if isinstance(exc, LimitExceeded):
        name, message = 'usage_limit', 'The session, user or turn token limit has been reached.'
    elif isinstance(exc, TimeoutError):
        name, message = 'provider_timeout', 'The provider exceeded the response deadline.'
    elif isinstance(exc, RequestRejected):
        from backend.llm.diagnostics import log_provider_failure
        log_provider_failure(exc)
        name, message = "request_rejected", "The provider rejected the request configuration."
    elif isinstance(exc, InvalidOutput):
        from backend.llm.diagnostics import log_provider_failure
        log_provider_failure(exc)
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
        from backend.llm.diagnostics import log_provider_failure
        log_provider_failure(exc)
        name, message = 'provider_unavailable', 'The provider could not be reached or was unavailable.'
    else:
        name, message = 'configuration_or_context', 'The provider configuration or context could not be accepted.'
    issue = {'name': name, 'severity': 'error', 'stage': stage, 'message': message}
    if name == 'schema_validation':
        import logging
        details = safe_schema_details(exc)
        safe_stage = stage if stage in {'intent', 'summary', 'itinerary', 'edit', 'extract', 'plan', 'attractions'} else 'unknown'
        logging.getLogger(__name__).warning('Schema failure: stage=%s details=%s', safe_stage, details)
    return issue


def public_failure_detail(issues):
    """Select only fixed explanations; never expose provider or tool payloads."""
    failed_days = [issue.get('day') for issue in issues if issue.get('name') == 'day_failed']
    if failed_days:
        from datetime import date
        try:
            dates = [date.fromisoformat(day).isoformat() for day in failed_days]
            return 'Deep planning failed after two attempts for: ' + ', '.join(dates) + '. No partial itinerary was saved.'
        except (TypeError, ValueError):
            pass
    explanations = {
        'request_rejected': 'The provider rejected the request configuration.',
        'provider_unavailable': 'The configured provider could not be reached or was unavailable.',
        'rate_limited': 'The configured provider is rate limited.',
        'quota_exhausted': 'The configured provider quota is exhausted.',
        'provider_timeout': 'The provider exceeded the response deadline.',
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


def safe_schema_details(exc):
    """Expose only contract field names and validator rules, never rejected content."""
    from jsonschema import ValidationError as JSONValidationError
    fields = {'trip', 'days', 'items', 'start_date', 'end_date', 'currency', 'id',
              'start', 'end', 'place', 'category', 'cost', 'chunk_ids', 'tool_result_ids',
              'coords', 'coord_tool_result_id', 'lat', 'lon', 'travel_mode',
              'allow_outside_visiting_window', 'day', 'operations', 'op', 'item', 'item_id',
              'places', 'name', 'chunk_id'}
    rules = {'required', 'type', 'enum', 'const', 'pattern', 'format', 'minItems', 'maxItems',
             'additionalProperties', 'anyOf', 'oneOf', 'minimum', 'maximum'}
    current, seen = exc, set()
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        if isinstance(current, ValidationError):
            return validation_details(current, fields)
        if isinstance(current, JSONValidationError):
            errors = list(current.context)[:8] or [current]
            return [{'path': [p if type(p) is int or isinstance(p, str) and p in fields else '[field]' for p in e.absolute_path],
                     'rule': e.validator if e.validator in rules else 'schema',
                     'message': 'Correct this field using the requested schema.',
                     'required_fields': [p for p in e.validator_value if p in fields] if e.validator == 'required' else []}
                    for e in errors]
        current = current.__cause__ or current.__context__
    return []
