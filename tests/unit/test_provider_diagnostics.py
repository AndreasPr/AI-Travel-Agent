"""Synthetic failure metadata tests; no provider or network calls."""
import logging

import httpx
import pytest

from backend.agent.errors import failure_issue, public_failure_detail
from backend.llm.diagnostics import log_provider_failure
from backend.llm.types import ProviderUnavailable


@pytest.mark.parametrize('cause,reason,status', [
    (httpx.ConnectError('synthetic-secret https://example.invalid?key=synthetic-secret'), 'connection', None),
    (httpx.ReadTimeout('synthetic-secret'), 'timeout', None),
    (TypeError('synthetic-secret'), 'sdk_interface', None),
    (ImportError('synthetic-secret'), 'sdk_import', None),
    (ProviderUnavailable('M3: export GEMINI_API_KEY for the free-tier project'), 'missing_api_key', None),
    (httpx.HTTPStatusError('synthetic-secret', request=httpx.Request('GET', 'https://example.invalid'),
                           response=httpx.Response(503)), 'http_error', 503),
])
def test_synthetic_provider_diagnostic_is_safe(cause, reason, status, caplog):
    outer = ProviderUnavailable('synthetic-secret')
    outer.__cause__ = cause
    with caplog.at_level(logging.WARNING):
        result = log_provider_failure(outer)
    assert result == {'reason': reason, 'http_status': status}
    assert reason in caplog.text
    assert 'synthetic-secret' not in caplog.text
    assert 'example.invalid' not in caplog.text


def test_synthetic_provider_failure_is_not_reported_as_validation(caplog):
    exc = ProviderUnavailable('synthetic-secret')
    exc.__cause__ = httpx.ConnectError('synthetic-secret')
    with caplog.at_level(logging.WARNING):
        issue = failure_issue(exc, 'intent')
    assert issue['name'] == 'provider_unavailable'
    assert 'connection' in caplog.text
    assert 'validation' not in public_failure_detail([issue])
    assert 'synthetic-secret' not in caplog.text


def test_synthetic_quota_database_error_is_classified_without_secrets(caplog):
    from psycopg import OperationalError
    error = ProviderUnavailable('Daily quota store unavailable; run database migrations')
    error.__cause__ = OperationalError('unsupported startup parameter; synthetic-secret')
    with caplog.at_level(logging.WARNING):
        result = log_provider_failure(error)
    assert result['reason'] == 'quota_database'
    assert 'synthetic-secret' not in caplog.text
