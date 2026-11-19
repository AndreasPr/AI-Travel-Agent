"""Committed chat and SSE response contracts; regeneration is deliberate."""
import json
from pathlib import Path
from backend.agent.models import ChatResponse
from backend.agent.events import EVENT_ADAPTER


def test_api_response_schema_snapshots():
    root = Path(__file__).parents[1] / 'snapshots/api'
    actual = {'chat': ChatResponse.model_json_schema(), 'stream': EVENT_ADAPTER.json_schema()}
    assert {p.stem for p in root.glob('*.json')} == set(actual)
    for name, schema in actual.items():
        assert json.loads((root / f'{name}.json').read_text()) == schema
