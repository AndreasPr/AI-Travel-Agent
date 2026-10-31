"""Synthetic scripted conversations; no real model or external HTTP calls."""
import asyncio
from copy import deepcopy
import json
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.agent.api import get_agent, router
from backend.agent.loop import Agent
from backend.agent.models import ChatRequest
from backend.agent.store import MemoryTripStore
from backend.llm.types import Response, ToolCall
from backend.tools.models import ToolResult, ValidateInput
from backend.tools.storage import utcnow
from backend.tools.validator import validate_itinerary


@pytest.fixture(autouse=True)
def offline(monkeypatch, request):
    if request.node.get_closest_marker('integration'):
        return
    def denied(*args, **kwargs):
        raise AssertionError('Network forbidden in agent unit tests')
    monkeypatch.setattr('socket.socket.connect', denied)
    monkeypatch.setattr('socket.create_connection', denied)


def itinerary(cost=None):
    return {'trip': {'start_date': '2027-04-10', 'end_date': '2027-04-12', 'currency': 'USD'}, 'days': [
        {'date': f'2027-04-{10 + i}', 'items': [dict(id=f'item-{i}', start=f'2027-04-{10 + i}T10:00:00', end=f'2027-04-{10 + i}T11:00:00',
         place='Synthetic sample hotel', category='hotel', cost=cost, currency='USD', tool_result_ids=['quote'] if cost is not None else [], chunk_ids=[])]} for i in range(3)]}


class Script:
    def __init__(self, entries):
        self.entries = list(entries)
        self.calls = []

    def generate(self, messages, **kwargs):
        self.calls.append((deepcopy(messages), kwargs))
        value = self.entries.pop(0)
        if isinstance(value, Exception):
            raise value
        if isinstance(value, Response):
            return value
        return Response(text=json.dumps(value), provider='synthetic', model='synthetic-test')


class Runtime:
    def __init__(self):
        self.store = self
        self.results = {'quote': dict(status='ok', tool='search_hotels', data={'hotels': [{'price_per_night': '100', 'total_price': '300', 'currency': 'USD'}]})}
        self.calls = []
        self.barrier = None
        self.fail = False
        self.no_data = False

    def get_result(self, key):
        return self.results.get(key)

    def execute(self, name, arguments):
        self.calls.append(name)
        if name == 'validate_itinerary':
            value = validate_itinerary(ValidateInput(**arguments), SimpleNamespace(runtime=self, check=lambda: None))
            return ToolResult(tool_result_id=str(uuid4()), tool=name, status='ok', data=value, source='validator', fetched_at=utcnow(), cache_hit=False)
        if self.fail:
            raise RuntimeError('synthetic tool failure')
        if self.barrier:
            self.barrier.wait(timeout=2)
        return ToolResult(tool_result_id='quote', tool=name, status='no_data' if self.no_data else 'ok', data=None if self.no_data else {'synthetic': True}, source='synthetic-v1', fetched_at=utcnow(), cache_hit=False)


def calls(*names):
    return Response(provider='synthetic', model='synthetic-test', tool_calls=[ToolCall(name=name, arguments={}) for name in names])


def setup(entries, intent=None, store=None):
    extract = Script([intent or {'intent': 'new_trip', 'budget': 1500}])
    plan = Script(entries)
    runtime = Runtime()
    agent = Agent(store=store or MemoryTripStore(), runtime=runtime, providers=lambda role: extract if role == 'extract' else plan)
    return agent, runtime, plan


def run(agent, message='Synthetic trip request', trip_id=None):
    return asyncio.run(agent.chat(ChatRequest(message=message, trip_id=trip_id)))


def test_tool_error_becomes_observation():
    agent, runtime, plan = setup([calls('search_hotels'), {}, itinerary()])
    runtime.fail = True
    result = run(agent)
    assert result.itinerary is not None
    assert 'tool_failed' in json.dumps(plan.calls[1][0])


def test_no_data_answer_says_cannot_find():
    agent, runtime, _ = setup([calls('search_hotels'), {}, itinerary()])
    runtime.no_data = True
    assert 'cannot find' in run(agent).message


def test_repair_loop_fixes_invalid_itinerary():
    agent, _, plan = setup([{}, {'bad': 'schema'}, itinerary()])
    result = run(agent)
    assert result.itinerary is not None
    assert 'schema_valid' in json.dumps(plan.calls[-1][0])


def test_repair_loop_gives_up_after_two():
    agent, _, plan = setup([{}, {}, {}, {}])
    result = run(agent)
    assert result.itinerary is None
    assert 'two repairs' in result.message
    assert len(plan.calls) == 4
    assert result.issues[0]['name'] == 'schema_valid'


def test_step_limit_stops_loop():
    agent, runtime, plan = setup([calls('search_hotels')] * 8)
    result = run(agent)
    assert 'step limit' in result.message
    assert len(plan.calls) == len(runtime.calls) == 8


def test_parallel_tool_calls_run_concurrently():
    agent, runtime, _ = setup([calls('search_hotels', 'search_flights'), {}, itinerary()])
    runtime.barrier = threading.Barrier(2)
    result = run(agent)
    assert all(row['status'] == 'ok' for row in result.tool_trace[:2])


def test_price_without_tool_result_fails():
    bad = itinerary('100')
    for day in bad['days']:
        day['items'][0]['tool_result_ids'] = []
    agent, _, _ = setup([{}, bad, bad, bad])
    result = run(agent)
    assert result.itinerary is None
    assert any(issue['name'] == 'missing_tool_result_id' for issue in result.issues)


def test_impossible_budget_sets_budget_met_false():
    agent, _, _ = setup([calls('search_hotels'), {}, itinerary('100'), itinerary('100'), itinerary('100')], {'intent': 'new_trip', 'budget': 10})
    result = run(agent)
    assert result.itinerary is not None and result.budget_met is False
    assert 'exceeds your budget' in result.message


def test_intent_routes_to_allowed_tools():
    agent, runtime, plan = setup([calls('search_hotels'), {}], {'intent': 'question_about_trip'})
    result = run(agent)
    assert 'search_hotels' not in runtime.calls
    assert result.tool_trace[0]['data']['error']['code'] == 'not_allowed'
    assert 'search_hotels' not in [t['name'] for t in plan.calls[0][1]['tools']]


def edit_state(store):
    from backend.tools.models import Itinerary
    state = store.create()
    state['itinerary'] = Itinerary.model_validate(itinerary('100')).model_dump(mode='json')
    state['budget'], state['evidence'] = '1000', ['quote']
    store.save(state, 0)
    return state


def test_edit_changes_only_day_2_and_other_days_identical():
    store = MemoryTripStore()
    state = edit_state(store)
    agent, _, _ = setup([{}, {'day': 2, 'operations': [{'op': 'remove_item', 'item_id': 'item-1'}]}], {'intent': 'edit_trip', 'day': 2}, store)
    result = run(agent, 'Make day 2 cheaper', state['id'])
    actual = result.itinerary.model_dump(mode='json')
    for i in [0, 2]:
        assert json.dumps(actual['days'][i]) == json.dumps(state['itinerary']['days'][i])
    assert actual['days'][1]['items'] == []
    assert result.diff['day'] == 2


def test_edit_revalidates_budget():
    store = MemoryTripStore()
    state = edit_state(store)
    patch = {'day': 2, 'operations': [{'op': 'remove_item', 'item_id': 'item-1'}]}
    agent, runtime, _ = setup([{}, patch, patch, patch], {'intent': 'edit_trip', 'day': 2, 'budget': 1}, store)
    result = run(agent, 'Make day 2 cheaper', state['id'])
    assert result.budget_met is False
    assert runtime.calls.count('validate_itinerary') == 3


def test_chat_endpoint_returns_expected_shape():
    agent, _, _ = setup([{}, itinerary()])
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_agent] = lambda: agent
    response = TestClient(app).post('/api/chat', json={'message': 'Synthetic sample trip'})
    assert response.status_code == 200
    assert {'trip_id', 'message', 'itinerary', 'diff', 'citations', 'tool_trace', 'budget_met', 'usage'} <= response.json().keys()


def test_tool_turn_messages_match_provider_protocols():
    from backend.llm.config import load_config, model_config
    from backend.llm.gemini import GeminiProvider
    from backend.llm.ollama import OllamaProvider
    agent, _, script = setup([calls('search_hotels'), {}, itinerary()])
    run(agent)
    messages = script.calls[1][0]
    config = load_config()
    for entry in config['roles']['plan']['chain']:
        spec = model_config(entry['provider'], entry['model'], config)
        if entry['provider'] == 'ollama':
            provider = OllamaProvider(entry['model'], spec)
            body, _ = provider._request(messages, None, None, False, {})
            assistant = next(row for row in body['messages'] if row.get('tool_calls'))
            assert assistant['tool_calls'][0]['function']['name'] == 'search_hotels'
            assert next(row for row in body['messages'] if row['role'] == 'tool')['tool_name'] == 'search_hotels'
        elif entry['provider'] == 'gemini':
            provider = GeminiProvider(entry['model'], spec)
            body = provider._request(messages, None, None, {})
            assert any('function_call' in part for row in body['contents'] for part in row['parts'])
            assert any('function_response' in part for row in body['contents'] for part in row['parts'])


def test_unknown_citation_and_foreign_result_are_rejected():
    bad = itinerary('100')
    bad['days'][0]['items'][0]['chunk_ids'] = ['invented-chunk']
    agent, _, _ = setup([{}, bad, bad, bad])
    result = run(agent)
    assert result.itinerary is None
    assert {'untrusted_citation', 'untrusted_tool_result'} <= {issue['name'] for issue in result.issues}


def test_structured_fallback_validates_and_usage_tracks_cache():
    from backend.agent.providers import StructuredProvider
    from backend.agent.models import Intent
    from backend.llm.types import InvalidOutput
    inner = Script([{'intent': 'chitchat'}, {'invalid': True}])
    inner.provider, inner.model = 'synthetic', 'synthetic-test'
    provider = StructuredProvider(inner, {'supports': {'structured_output': False}})
    provider.generate([{'role': 'user', 'content': 'Synthetic hello'}], response_schema=Intent)
    assert inner.calls[0][1]['response_schema'] is None
    assert 'Return only JSON' in inner.calls[0][0][-1]['content']
    with pytest.raises(InvalidOutput):
        provider.generate([], response_schema=Intent)
    agent, _, _ = setup([])
    response = Response(text='{"intent":"chitchat"}', provider='synthetic', model='synthetic-test', tokens_in=20, tokens_out=4, cached_tokens=12)
    agent.providers = lambda role: Script([response])
    result = run(agent)
    assert (result.usage.tokens_in, result.usage.cached_tokens, result.usage.uncached_tokens) == (20, 12, 8)


def test_tool_deadline_becomes_structured_observation(monkeypatch):
    import time
    from dataclasses import replace
    from backend.tools.registry import REGISTRY
    agent, runtime, script = setup([calls('search_hotels'), {}, itinerary()])
    original = runtime.execute

    def slow(name, arguments):
        if name == 'search_hotels':
            time.sleep(0.2)
        return original(name, arguments)

    runtime.execute = slow
    entry = REGISTRY['search_hotels']
    monkeypatch.setitem(REGISTRY, 'search_hotels', replace(entry, policy=replace(entry.policy, timeout_seconds=0.001)))
    result = run(agent)
    assert result.tool_trace[0]['status'] == 'error'
    assert 'tool_failed' in json.dumps(script.calls[1][0])
