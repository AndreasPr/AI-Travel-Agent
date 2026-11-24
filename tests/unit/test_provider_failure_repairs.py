"""Synthetic provider failures; no live requests or quota consumption."""
import asyncio

import pytest

from backend.llm.types import ProviderUnavailable, RateLimited, QuotaExhausted
from test_agent_streaming import AsyncScript, agent_for, calls, collect, parse_frames


@pytest.mark.parametrize(('error', 'code'), [
    (ProviderUnavailable('Synthetic exhausted server retries'), 'provider_unavailable'),
    (RateLimited('Synthetic minute limit'), 'rate_limited'),
    (QuotaExhausted('Synthetic daily limit'), 'quota_exhausted'),
])
def test_synthetic_provider_failure_does_not_trigger_itinerary_repairs(error, code):
    plan = AsyncScript([calls('search_hotels'), {}, error])
    events = parse_frames(asyncio.run(collect(agent_for(plan=plan))))
    assert len(plan.calls) == 3
    assert events[-1]['type'] == 'error'
    assert events[-1]['code'] == code
    assert not any(event['type'] in {'itinerary_update', 'done'} for event in events)
    assert not any('Repair the candidate' in str(messages) for messages, _ in plan.calls)


def test_synthetic_outage_during_repair_is_reported_as_provider_failure():
    plan = AsyncScript([calls('search_hotels'), {}, {'invalid': 'synthetic'},
                        ProviderUnavailable('Synthetic outage')])
    events = parse_frames(asyncio.run(collect(agent_for(plan=plan))))
    assert len(plan.calls) == 4
    assert events[-1]['code'] == 'provider_unavailable'


def test_synthetic_http_400_is_not_repaired_or_retried():
    from backend.llm.retry import status_error
    from backend.llm.types import RequestRejected
    error = status_error(400)
    assert isinstance(error, RequestRejected)
    plan = AsyncScript([calls('search_hotels'), {}, error])
    events = parse_frames(asyncio.run(collect(agent_for(plan=plan))))
    assert len(plan.calls) == 3
    assert events[-1]['code'] == 'invalid_output'
    assert events[-1]['message'] == 'The provider rejected the request configuration.'


def test_synthetic_request_diagnostics_never_log_payload(caplog):
    from backend.llm.diagnostics import log_provider_failure
    error = Exception('response_json_schema synthetic-private-payload')
    error.code = 400
    log_provider_failure(error)
    assert 'category=response_schema' in caplog.text
    assert 'synthetic-private-payload' not in caplog.text


def test_synthetic_extraction_request_rejection_is_not_repaired():
    from backend.agent.attractions import extract_attractions
    from backend.llm.retry import status_error
    from backend.llm.types import RequestRejected
    attempts = []
    async def generate(*args, **kwargs):
        attempts.append(kwargs)
        raise status_error(400)
    with pytest.raises(RequestRejected):
        asyncio.run(extract_attractions([{'chunk_id': 'synthetic', 'excerpt': 'Synthetic Museum'}], generate))
    assert len(attempts) == 1
