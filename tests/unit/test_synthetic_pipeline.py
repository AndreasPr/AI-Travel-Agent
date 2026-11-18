"""Synthetic scripted tests of the pipeline, not model behavior."""
import asyncio
import json
from pathlib import Path

import pytest

from backend.agent.models import ChatRequest
from backend.agent.store import MemoryTripStore
from backend.testing.synthetic import FIXTURE, enabled, synthetic_agent
from backend.tools.runtime import ToolRuntime
from test_agent_tools import MemoryStore


def test_synthetic_pipeline_validates_itinerary_and_emits_tools():
    fixture = json.loads(FIXTURE.read_text())
    runtime = ToolRuntime(store=MemoryStore(), search=lambda *a, **k: [fixture['chunk']])
    try:
        agent = synthetic_agent(MemoryTripStore(), runtime)
        result = asyncio.run(agent.chat(ChatRequest(message=fixture['request'])))
        assert result.itinerary is not None, result.issues
        assert result.citations[0]['title'].startswith('Synthetic')
        assert {r['tool'] for r in result.tool_trace} == {'search_destinations', 'validate_itinerary'}
        assert all(call['provider'] == 'synthetic' for call in result.usage.calls)
    finally:
        runtime.close()


def test_synthetic_mode_rejected_in_production(monkeypatch):
    monkeypatch.setenv('LLM_STUB', '1')
    monkeypatch.setenv('TEST_SUITE_MODE', '1')
    monkeypatch.setenv('APP_ENV', 'production')
    with pytest.raises(RuntimeError, match='forbidden in production'):
        enabled()


def test_synthetic_fixture_never_attributed_to_real_model():
    for folder in ('tests/fixtures/llm', 'tests/fixtures/synthetic', 'eval/fixtures/recorded'):
        for path in Path(folder).rglob('*.json'):
            row = json.loads(path.read_text())
            provenance = str(row.get('provenance', row.get('source', ''))).lower()
            response = row.get('response', row)
            synthetic = ('synthetic' in path.parts or 'synthetic' in provenance
                         or response.get('provider') == 'synthetic'
                         or str(response.get('model', '')).startswith('synthetic'))
            if not synthetic:
                continue
            assert 'synthetic' in provenance, path
            assert 'recorded' not in path.parts and 'recordings' not in path.parts, path
            response = row.get('response', row)
            assert response.get('provider', 'synthetic') == 'synthetic', path
            assert response.get('model', 'synthetic').startswith('synthetic'), path
            assert 'synthetic' in path.parts, path
