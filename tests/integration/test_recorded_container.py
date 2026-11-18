"""Real recorded full turns are distinct from synthetic pipeline exercises."""
import asyncio
import json
from pathlib import Path
import secrets

import pytest


@pytest.fixture
def recorded_chat():
    manifest = Path('tests/fixtures/llm/full_chat/manifest.json')
    if not manifest.exists():
        pytest.skip('no recording; run make eval-record')
    value = json.loads(manifest.read_text())
    assert value['provenance'] == 'recorded'
    return manifest.parent, value


def test_full_chat_turn_with_postgres_container(recorded_chat, request):
    # Resolve Docker only after a real transcript is available. No fake recordings.
    directory, recorded = recorded_chat
    engine = request.getfixturevalue('postgres_container_engine')
    from backend.agent.loop import Agent
    from backend.agent.models import ChatRequest
    from backend.agent.store import PostgresTripStore
    from backend.auth.service import AuthService, Settings
    from backend.llm.replay import ReplayProvider
    from backend.tools.models import ToolResult, ValidateInput
    from backend.tools.storage import PostgresStore, utcnow
    from backend.tools.validator import validate_itinerary
    from types import SimpleNamespace

    class RecordedTools:
        def __init__(self):
            self.store = PostgresStore(engine)
            self.pending = list(recorded['tools'])

        def execute(self, name, arguments):
            if name == 'validate_itinerary':
                data = validate_itinerary(ValidateInput(**arguments), SimpleNamespace(runtime=self, check=lambda: None))
                return ToolResult(tool_result_id='recorded-validation', tool=name, status='ok', data=data,
                                  source='validator', fetched_at=utcnow(), cache_hit=False)
            entry = self.pending.pop(0)
            assert entry['tool'] == name and entry['arguments'] == arguments
            result = ToolResult.model_validate(entry['result'])
            self.store.save_result(result)
            return result

    auth = AuthService(engine, Settings(secrets.token_urlsafe(48), False, ('http://recorded.test',)))
    user = auth.register('recorded-test@example.invalid', secrets.token_urlsafe(24))
    store = PostgresTripStore(engine).for_owner(user['id'])
    runtime = RecordedTools()
    def provider(role):
        entry = recorded['roles'][role]
        assert entry['provider'] != 'synthetic'
        return ReplayProvider(entry['provider'], entry['model'], directory)
    agent = Agent(store=store, runtime=runtime, providers=provider)
    reservation = auth.reserve_turn(user['id'], agent.config['guardrails']['turn_tokens'])
    result = asyncio.run(agent.chat(ChatRequest(message=recorded['request']), user_id=user['id']))
    assert result.itinerary is not None, result.issues
    assert result.itinerary.model_dump(mode='json') == recorded['itinerary']
    assert not runtime.pending
    auth.settle_turn(reservation, result.usage.tokens_in + result.usage.tokens_out)
    assert store.load(result.trip_id)['itinerary'] == recorded['itinerary']
