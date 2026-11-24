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
