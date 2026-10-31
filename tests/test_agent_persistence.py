"""Synthetic state, context and replay tests; no provider requests."""
import asyncio
from copy import deepcopy
import json

import pytest
from sqlalchemy import create_engine

from backend.agent.context import ContextBuilder
from backend.agent.store import MemoryTripStore, PostgresTripStore, StoreConflict
from backend.db.models import AgentConversation, AgentMessage, AgentTrip, AgentItineraryVersion
from backend.llm.config import load_config
from backend.llm.replay import ReplayProvider, fixture_key
from backend.llm.types import Response
from test_agent_loop import Script, edit_state, run, setup, itinerary, offline  # noqa: F401


@pytest.fixture(params=['sqlite', pytest.param('postgres', marks=pytest.mark.integration)])
def store(tmp_path, request):
    if request.param == 'sqlite':
        engine = create_engine('sqlite:///' + str(tmp_path / 'synthetic-state.db'))
        for model in (AgentConversation, AgentMessage, AgentTrip, AgentItineraryVersion):
            model.__table__.create(engine)
        yield PostgresTripStore(engine)
        engine.dispose()
        return
    import importlib.util
    from pathlib import Path
    from uuid import uuid4
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    from backend.db.connect import engine
    schema = 'synthetic_agent_' + uuid4().hex
    scoped = engine.execution_options(schema_translate_map={None: schema})
    path = Path(__file__).resolve().parents[1] / 'backend/alembic/versions/20261103_agent_state.py'
    spec = importlib.util.spec_from_file_location('agent_state_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
        yield PostgresTripStore(scoped)
        with engine.begin() as connection:
            connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


def test_conversation_survives_new_session(store):
    agent, _, _ = setup([{}, itinerary()], store=store)
    result = run(agent)
    restored = PostgresTripStore(store.engine).load(result.trip_id)
    assert restored['itinerary'] == result.itinerary.model_dump(mode='json')
    assert restored['history'][0]['content'] == 'Synthetic trip request'
    assert len(restored['versions']) == 1


def test_each_edit_creates_version_and_undo_restores(store):
    state = edit_state(store)
    original = deepcopy(state['itinerary'])
    patch = {'day': 2, 'operations': [{'op': 'remove_item', 'item_id': 'item-1'}]}
    agent, _, _ = setup([{}, patch], {'intent': 'edit_trip', 'day': 2}, store)
    result = run(agent, 'Make day 2 cheaper', state['id'])
    assert result.diff is not None
    assert len(store.versions(state['id'])) == 2
    restored = PostgresTripStore(store.engine).undo(state['id'])
    assert restored['itinerary'] == original
    assert len(restored['versions']) == 3
    assert restored['versions'][1]['itinerary']['days'][1]['items'] == []
    with pytest.raises(ValueError, match='No earlier'):
        store.undo(state['id'])


def test_preference_proposal_requires_confirmation(store):
    agent, _, _ = setup([], {'intent': 'chitchat', 'preference_proposal': {'pace': 'relaxed', 'interests': ['museums']}}, store)
    result = run(agent, 'I prefer a relaxed pace and museums')
    assert store.load(result.trip_id)['preferences'] == {}
    assert result.preference_proposal.pace == 'relaxed'
    result = run(agent, 'confirm preferences', result.trip_id)
    assert store.load(result.trip_id)['preferences']['pace'] == 'relaxed'


def test_sensitive_data_not_stored(store):
    agent, _, _ = setup([], store=store)
    result = run(agent, 'My passport number is SYNTHETIC-123')
    state = store.load(result.trip_id)
    assert state['history'] == []
    assert 'SYNTHETIC-123' not in json.dumps(state)
    state['preferences'] = {'mobility': 'diagnosis: synthetic health detail'}
    with pytest.raises(ValueError):
        store.save(state, state['revision'])
    state['preferences'] = {}
    state['history'] = [{'role': 'user', 'content': 'My credit card is a synthetic example'}]
    with pytest.raises(ValueError, match='Sensitive'):
        store.save(state, state['revision'])


def context_settings():
    return {'token_budget': 2200, 'last_turns': 3, 'summary_input_chars': 2000, 'chars_per_token': {'default': 3, 'synthetic': 3}}


def test_summarization_triggers_over_budget():
    builder = ContextBuilder([], context_settings())
    state = MemoryTripStore().create()
    state['history'] = [{'role': 'user', 'content': 'Synthetic history ' * 100} for _ in range(10)]
    script = Script([{'summary': 'Synthetic summary: museums and food.'}] * 20)

    async def generate(role, messages, **kwargs):
        assert role == 'extract'
        return script.generate(messages, **kwargs)

    messages = asyncio.run(builder.build(state, 'Continue', 'synthetic', generate))
    assert len(script.calls) >= 1 and state['summarized_count'] > 0
    assert builder.estimate(messages, 'synthetic') <= 2200


def write_synthetic_fixture(folder, messages, tools=None, response_schema=None, response=None):
    response = response or Response(text=json.dumps({'summary': 'Synthetic summary: museums and food.'}), provider='synthetic', model='synthetic-test')
    key = fixture_key('synthetic', 'synthetic-test', messages, tools, response_schema)
    (folder / (key + '.json')).write_text(json.dumps({'provenance': 'synthetic scripted test, not a provider recording', 'response': response.model_dump()}))
    return response


def test_context_stays_under_budget_over_30_turns(tmp_path):
    builder = ContextBuilder([], context_settings())
    replay = ReplayProvider('synthetic', 'synthetic-test', tmp_path)
    counts = []

    async def turns(record_synthetic):
        state = MemoryTripStore().create()
        for index in range(30):
            async def generate(role, messages, **kwargs):
                if record_synthetic:
                    return write_synthetic_fixture(tmp_path, messages, response_schema=kwargs['response_schema'])
                return replay.generate(messages, **kwargs)
            messages = await builder.build(state, f'Synthetic turn {index}', 'synthetic', generate)
            counts.append(builder.estimate(messages, 'synthetic'))
            state['history'].extend([{'role': 'user', 'content': 'Synthetic museum preference ' * 40}, {'role': 'assistant', 'content': 'Synthetic acknowledgment ' * 40}])
        assert state['summarized_count'] > 0

    asyncio.run(turns(True))
    asyncio.run(turns(False))
    assert max(counts) <= 2200


def test_static_prefix_is_byte_identical_across_turns():
    builder = ContextBuilder([{'name': 'synthetic_lookup', 'parameters': {}}], context_settings())
    state = MemoryTripStore().create()

    async def no_summary(*args, **kwargs):
        raise AssertionError('No summarization needed')

    first = asyncio.run(builder.build(state, 'Synthetic first turn', 'synthetic', no_summary))
    state['preferences'] = {'pace': 'relaxed'}
    state['history'].append({'role': 'user', 'content': 'Synthetic first turn'})
    second = asyncio.run(builder.build(state, 'Synthetic second turn', 'synthetic', no_summary))
    assert first[0]['content'].encode() == second[0]['content'].encode()


def test_concurrent_state_write_is_rejected(store):
    state = store.create()
    stale = deepcopy(state)
    store.save(state, 0)
    with pytest.raises(StoreConflict):
        store.save(stale, 0)


def test_agent_loop_with_synthetic_replay(tmp_path):
    from backend.agent.loop import Agent
    from test_agent_loop import Runtime

    class SyntheticFixtures:
        def __init__(self, entries):
            self.script = Script(entries)

        def generate(self, messages, tools=None, response_schema=None, **kwargs):
            result = self.script.generate(messages)
            return write_synthetic_fixture(tmp_path, messages, tools, response_schema, result)

    fake_extract = SyntheticFixtures([{'intent': 'new_trip', 'budget': 1500}])
    fake_plan = SyntheticFixtures([{}, itinerary()])
    config = load_config()
    # Both runs use exactly the same synthetic request payload; IDs are not prompt inputs.
    first = Agent(store=MemoryTripStore(), runtime=Runtime(), config=config, providers=lambda role: fake_extract if role == 'extract' else fake_plan)
    expected = run(first)
    replay = ReplayProvider('synthetic', 'synthetic-test', tmp_path)
    second = Agent(store=MemoryTripStore(), runtime=Runtime(), config=config, providers=lambda role: replay)
    actual = run(second)
    assert actual.itinerary == expected.itinerary
    assert actual.itinerary is not None


def test_versions_and_undo_endpoints(store):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.agent.api import get_agent, router
    state = edit_state(store)
    patch = {'day': 2, 'operations': [{'op': 'remove_item', 'item_id': 'item-1'}]}
    agent, _, _ = setup([{}, patch], {'intent': 'edit_trip', 'day': 2}, store)
    run(agent, 'Make day 2 cheaper', state['id'])
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_agent] = lambda: agent
    client = TestClient(app)
    listed = client.get('/api/trips/' + state['id'] + '/versions')
    assert listed.status_code == 200 and len(listed.json()['versions']) == 2
    restored = client.post('/api/trips/' + state['id'] + '/undo')
    assert restored.status_code == 200
    assert restored.json()['itinerary'] == state['itinerary']
    assert restored.json()['version'] == 3
