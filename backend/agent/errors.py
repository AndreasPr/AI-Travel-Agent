"""Safe diagnostic categories without provider payloads or exception text."""
from pydantic import ValidationError

from backend.llm.types import InvalidOutput, ProviderUnavailable, QuotaExhausted, RateLimited


def failure_issue(exc, stage):
    if isinstance(exc, TimeoutError):
        name, message = 'provider_timeout', 'The provider exceeded the response deadline.'
    elif isinstance(exc, InvalidOutput):
        # These adapter messages are fixed literals; never echo arbitrary exception text.
        known = {
            'Provider returned invalid JSON': ('invalid_json', 'The provider returned invalid JSON.'),
            'Output does not satisfy the JSON schema': ('schema_validation', 'The provider response did not match the required schema.'),
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
