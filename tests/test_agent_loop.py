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


def run(agent, message='Synthetic trip request under 1500 USD', trip_id=None):
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
    assert result.issues[0]['reason'] == 'schema_validation'
    assert result.issues[0]['validation_error_types'] == ['missing']


def test_step_limit_stops_loop():
    agent, runtime, plan = setup([calls('search_hotels')] * 8)
    result = run(agent)
    assert 'step limit' in result.message
    assert len(plan.calls) == len(runtime.calls) == 8


def test_parallel_tool_calls_run_concurrently():
    agent, runtime, _ = setup([calls('search_hotels', 'search_flights'), {}, itinerary()])
    runtime.barrier = threading.Barrier(2)
    result = run(agent, 'Synthetic flights from JFK under 1500 USD')
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
    result = run(agent, 'Synthetic trip request under 10 USD')
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
    result = run(agent, 'Make day 2 cheaper, budget 1 USD', state['id'])
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
            body, _ = provider._request(messages, None, None, False, {'tool_mode': 'auto'})
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


@pytest.mark.parametrize('text,valid', [
    ('{"intent":"new_trip","budget":1500}', True),
    ('{"intent":"unsupported"}', False),
    ('Synthetic non-JSON response', False),
])
def test_ollama_intent_fallback_requests_json_and_validates_schema(text, valid):
    import httpx
    import respx
    from backend.agent.models import Intent
    from backend.agent.providers import StructuredProvider
    from backend.llm.config import load_config, model_config
    from backend.llm.ollama import OllamaProvider
    from backend.llm.types import InvalidOutput

    config = load_config()
    entry = next(row for row in config['roles']['extract']['chain'] if row['provider'] == 'ollama')
    spec = {**model_config('ollama', entry['model'], config), 'supports': {'structured_output': False}}
    with httpx.Client() as client, respx.mock(assert_all_called=True) as mock:
        route = mock.post('http://localhost:11434/api/chat').mock(return_value=httpx.Response(200, json={
            'done': True, 'message': {'content': text}, 'prompt_eval_count': 10, 'eval_count': 5,
        }))
        adapter = OllamaProvider(entry['model'], spec, base_url='http://localhost:11434', client=client)
        provider = StructuredProvider(adapter, spec)
        messages = [{'role': 'user', 'content': 'Synthetic intent extraction example'}]
        if valid:
            response = provider.generate(messages, response_schema=Intent)
            assert Intent.model_validate_json(response.text).intent == 'new_trip'
        else:
            with pytest.raises(InvalidOutput):
                provider.generate(messages, response_schema=Intent)
        body = json.loads(route.calls[0].request.content)
        assert body['format'] == 'json'
        assert 'json_mode' not in body['options']
        assert 'Return only JSON matching this schema:' in body['messages'][-1]['content']
        assert messages == [{'role': 'user', 'content': 'Synthetic intent extraction example'}]


def test_generated_numeric_uuids_do_not_reject_agent_turn(monkeypatch):
    from uuid import UUID
    synthetic_id = UUID('12345678-1234-4234-8234-123456789012')
    monkeypatch.setattr('backend.agent.store.uuid4', lambda: synthetic_id)
    monkeypatch.setattr('test_agent_loop.uuid4', lambda: synthetic_id)
    agent, _, _ = setup([{}, itinerary()])
    result = run(agent)
    assert result.itinerary is not None
    assert result.trip_id == str(synthetic_id)
    assert agent.store.load(result.trip_id)['itinerary'] is not None


def test_configured_ollama_intent_uses_schema_constrained_output():
    import httpx
    import respx
    from backend.agent.models import Intent
    from backend.agent.providers import StructuredProvider
    from backend.llm.config import load_config, model_config
    from backend.llm.ollama import OllamaProvider
    from backend.llm.types import InvalidOutput

    config = load_config()
    entry = next(row for row in config['roles']['extract']['chain'] if row['provider'] == 'ollama')
    spec = model_config('ollama', entry['model'], config)
    assert spec['supports']['structured_output'] is True
    with httpx.Client() as client, respx.mock(assert_all_called=True) as mock:
        route = mock.post('http://localhost:11434/api/chat')
        provider = StructuredProvider(OllamaProvider(entry['model'], spec, base_url='http://localhost:11434', client=client), spec)
        for content in ['{"intent":"new_trip","budget":1500}', '{"intent":"new_trip","extra":"synthetic"}']:
            route.mock(return_value=httpx.Response(200, json={'done': True, 'message': {'content': content}}))
            if 'extra' in content:
                with pytest.raises(InvalidOutput, match='JSON schema'):
                    provider.generate([{'role': 'user', 'content': 'Synthetic trip request'}], response_schema=Intent)
            else:
                result = provider.generate([{'role': 'user', 'content': 'Synthetic trip request'}], response_schema=Intent)
                assert Intent.model_validate_json(result.text).intent == 'new_trip'
            body = json.loads(route.calls[-1].request.content)
            assert body['format'] == Intent.model_json_schema()
            assert body['format']['additionalProperties'] is False


@pytest.mark.parametrize('error_message,expected', [
    ('Provider returned invalid JSON', 'invalid_json'),
    ('Output does not satisfy the JSON schema', 'schema_validation'),
    ('Synthetic secret should never be echoed', 'invalid_output'),
])
def test_intent_failure_reports_safe_diagnostic(error_message, expected):
    from backend.llm.types import InvalidOutput
    agent, runtime, _ = setup([])
    agent.providers = lambda role: Script([InvalidOutput(error_message)])
    result = run(agent)
    assert result.issues[0]['name'] == expected
    assert result.issues[0]['stage'] == 'intent'
    assert runtime.calls == []
    assert result.itinerary is None
    assert 'Synthetic secret' not in result.model_dump_json()
    assert 'Synthetic secret' not in json.dumps(agent.store.load(result.trip_id))


def test_repair_preserves_invalid_candidate_and_specific_datetime_rule():
    invalid = itinerary()
    invalid['days'][0]['items'][0]['start'] += 'Z'
    agent, _, script = setup([{}, invalid, itinerary()])
    result = run(agent)
    assert result.itinerary is not None
    repair = script.calls[-1][0][-1]['content']
    assert '2027-04-10T10:00:00Z' in repair
    assert 'Use local wall-clock datetimes without offsets' in repair
    assert '"path": ["days", 0, "items", 0]' in repair


def test_validation_details_do_not_echo_rejected_values():
    from pydantic import ValidationError
    from backend.agent.errors import validation_details
    from backend.tools.models import Itinerary
    invalid = itinerary()
    invalid['days'][0]['items'][0]['start'] = 'Synthetic private rejected value'
    with pytest.raises(ValidationError) as caught:
        Itinerary.model_validate(invalid)
    details = validation_details(caught.value)
    assert details[0]['path'] == ['days', 0, 'items', 0, 'start']
    assert 'Synthetic private' not in json.dumps(details)


@pytest.mark.parametrize('schema_name', ['Itinerary', 'DayPatch'])
def test_generation_schema_requires_local_datetimes_without_offsets(schema_name):
    from backend.agent.models import DayPatch
    from backend.agent.providers import generation_schema
    from backend.llm.validation import validate
    from backend.llm.types import InvalidOutput
    from backend.tools.models import Itinerary
    schema = Itinerary if schema_name == 'Itinerary' else DayPatch
    original = schema.model_json_schema()
    projected = generation_schema(schema)
    start = projected['$defs']['Item']['properties']['start']
    assert 'format' not in start
    assert r'\d' not in start['pattern']
    assert '[0-9]' in start['pattern']
    assert schema.model_json_schema() == original
    for value in ['2027-04-10T10:00:00', '2027-04-10T10:00:00.123456']:
        validate(value, start)
    for value in ['2027-04-10T10:00:00Z', '2027-04-10T10:00:00+01:00', '2027-04-10']:
        with pytest.raises(InvalidOutput):
            validate(value, start)


def test_ollama_itinerary_request_uses_local_time_schema():
    import httpx
    import respx
    from backend.agent.providers import StructuredProvider
    from backend.llm.config import load_config, model_config
    from backend.llm.ollama import OllamaProvider
    from backend.tools.models import Itinerary
    config = load_config()
    entry = next(row for row in config['roles']['plan']['chain'] if row['provider'] == 'ollama')
    spec = model_config('ollama', entry['model'], config)
    with httpx.Client() as client, respx.mock(assert_all_called=True) as mock:
        route = mock.post('http://localhost:11434/api/chat').mock(return_value=httpx.Response(200, json={
            'done': True, 'message': {'content': json.dumps(itinerary())},
        }))
        provider = StructuredProvider(OllamaProvider(entry['model'], spec, base_url='http://localhost:11434', client=client), spec)
        result = provider.generate([{'role': 'user', 'content': 'Synthetic trip request'}], response_schema=Itinerary)
        assert Itinerary.model_validate_json(result.text).days
        body = json.loads(route.calls[0].request.content)
        assert body['options']['num_ctx'] == spec['context_window']
        assert spec['context_window'] >= config['agent']['context']['token_budget'] + config['agent']['max_output_tokens']
        start = body['format']['$defs']['Item']['properties']['start']
        assert 'pattern' in start and 'format' not in start


def test_adapter_rejected_tool_arguments_become_runtime_observation():
    from backend.llm.validation import validate_response
    from backend.tools.runtime import ToolRuntime

    class ValidatingScript(Script):
        def generate(self, messages, **kwargs):
            result = super().generate(messages, **kwargs)
            return validate_response(result, kwargs.get('tools'), kwargs.get('response_schema'))

    agent, store, _ = setup([])
    extract = Script([{'intent': 'new_trip', 'budget': 1500}])
    plan = ValidatingScript([calls('search_hotels'), {}, itinerary()])
    agent.providers = lambda role: extract if role == 'extract' else plan
    store.save_result = lambda result: store.results.update({result.tool_result_id: result.model_dump(mode='json')})
    def no_database():
        raise AssertionError('Invalid arguments must not reach a database')
    runtime = ToolRuntime(store=store, session_factory=no_database)
    agent.runtime = runtime
    try:
        result = run(agent)
    finally:
        runtime.close()
    assert result.itinerary is not None
    assert result.tool_trace[0]['status'] == 'error'
    assert result.tool_trace[0]['data']['error']['code'] == 'invalid_input'
    assert 'invalid_input' in json.dumps(plan.calls[1][0])
    assert 'argument_issues' in json.dumps(plan.calls[1][0])
    assert 'check_in' in json.dumps(plan.calls[1][0])


def test_tool_call_envelope_enforces_nullable_arguments_and_definitions():
    from backend.llm.ollama import tool_envelope
    from backend.llm.validation import validate
    from backend.llm.types import InvalidOutput
    from backend.tools.models import HotelsInput
    tools = [{'name': 'search_hotels', 'parameters': HotelsInput.model_json_schema()}]
    schema = tool_envelope(tools)
    args = {'city': 'Synthetic City', 'check_in': '2027-04-10', 'check_out': '2027-04-14', 'min_rating': None}
    value = {'text': '', 'tool_calls': [{'name': 'search_hotels', 'arguments': args}]}
    validate(value, schema)
    args['min_rating'] = 'null'
    with pytest.raises(InvalidOutput):
        validate(value, schema)
    tools = [{'name': 'synthetic_lookup', 'parameters': {'type': 'object', 'properties': {'value': {'$ref': '#/$defs/Value'}}, 'required': ['value'], '$defs': {'Value': {'type': 'integer'}}}}]
    schema = tool_envelope(tools)
    validate({'text': '', 'tool_calls': [{'name': 'synthetic_lookup', 'arguments': {'value': 1}}]}, schema)
    with pytest.raises(InvalidOutput):
        validate({'text': '', 'tool_calls': [{'name': 'synthetic_lookup', 'arguments': {'value': 'invalid'}}]}, schema)


def test_requested_hotel_lookup_cannot_be_skipped():
    agent, runtime, _ = setup([{}, calls('search_hotels'), itinerary('100')])
    result = run(agent, 'Plan a trip with synthetic hotel quotes under 1500 USD')
    assert result.itinerary is not None
    assert 'search_hotels' in runtime.calls


def test_requested_hotel_quote_cannot_be_omitted_from_itinerary():
    agent, _, script = setup([calls('search_hotels'), itinerary(), itinerary('100')])
    result = run(agent, 'Plan a trip with synthetic hotel quotes under 1500 USD')
    assert result.itinerary is not None
    assert any(item.cost is not None for day in result.itinerary.days for item in day.items)
    assert 'requested_hotel_quote_missing' in json.dumps(script.calls[-1][0])


def test_server_assigns_unique_stable_item_ids_without_changing_prices():
    raw = itinerary('100')
    for day in raw['days']:
        day['items'][0]['id'] = 'synthetic-repeated-id'
    agent, _, _ = setup([calls('search_hotels'), {}, raw])
    result = run(agent)
    ids = [item.id for day in result.itinerary.days for item in day.items]
    assert len(set(ids)) == 3
    assert ids[1] == '2027-04-11:item:1'
    assert all(str(item.cost) == '100' and item.tool_result_ids == ['quote'] for day in result.itinerary.days for item in day.items)


def test_explicit_trip_dates_cannot_be_replaced_by_model():
    agent, _, _ = setup([{}, itinerary(), itinerary(), itinerary()])
    result = run(agent, 'Plan 2027-04-20 through 2027-04-22 under 1500 USD')
    assert result.itinerary is None
    assert any(row['name'] == 'requested_dates_mismatch' for row in result.issues)


def test_trip_interests_do_not_implicitly_propose_saved_preferences():
    agent, _, _ = setup([], {'intent': 'chitchat', 'preference_proposal': {'interests': ['museums']}})
    result = run(agent, 'Tell me about museums')
    assert result.preference_proposal is None
    assert agent.store.load(result.trip_id)['proposal'] is None


def test_json_tool_mode_preserves_observations_without_native_message_fields():
    from backend.llm.config import load_config, model_config
    from backend.llm.ollama import OllamaProvider
    config = load_config()
    entry = next(row for row in config['roles']['plan']['chain'] if row['provider'] == 'ollama')
    adapter = OllamaProvider(entry['model'], model_config('ollama', entry['model'], config))
    messages = [{'role': 'assistant', 'content': '', 'tool_calls': [{'function': {'name': 'synthetic_lookup', 'arguments': {'city': 'Synthetic City'}}}]},
                {'role': 'tool', 'name': 'synthetic_lookup', 'content': '<DATA>synthetic observation</DATA>'}]
    body, _ = adapter._request(messages, None, None, False, {})
    assert json.loads(body['messages'][0]['content'])['tool_calls'][0]['name'] == 'synthetic_lookup'
    assert 'tool_calls' not in body['messages'][0]
    assert body['messages'][1]['role'] == 'user'
    assert '<DATA>synthetic observation</DATA>' in body['messages'][1]['content']
    assert messages[1]['role'] == 'tool'


def test_explicit_hotel_activity_trip_excludes_unrequested_flights_and_weather():
    from backend.agent.requirements import scoped_tools
    from backend.agent.policy import ALLOWLISTS
    selected = scoped_tools(ALLOWLISTS['new_trip'], 'Plan Lisbon 2027-04-10 through 2027-04-14 with hotels and museums')
    assert selected == {'search_hotels', 'search_destinations'}


def test_hotel_quote_cannot_price_an_unrelated_activity():
    from backend.agent.requirements import quoted_item_issues
    candidate = itinerary('100')
    result = {'tool': 'search_hotels', 'tool_result_id': 'quote', 'data': {'hotels': [
        {'name': 'Synthetic sample hotel', 'price_per_night': '100', 'total_price': '300', 'currency': 'USD'}]}}
    assert quoted_item_issues(candidate, [result]) == []
    candidate['days'][1]['items'][0]['place'] = 'Synthetic museum'
    issues = quoted_item_issues(candidate, [result])
    assert len(issues) == 1 and issues[0]['name'] == 'hotel_quote_item_mismatch'


def test_ollama_transport_keeps_static_prefix_before_dynamic_schemas():
    from backend.llm.ollama import OllamaProvider
    from backend.llm.config import load_config, model_config
    config = load_config()
    entry = next(row for row in config['roles']['plan']['chain'] if row['provider'] == 'ollama')
    provider = OllamaProvider(entry['model'], model_config('ollama', entry['model'], config))
    messages = [{'role': 'system', 'content': 'Synthetic static system and tool definitions'}, {'role': 'user', 'content': 'Synthetic turn'}]
    first, _ = provider._request(messages, [{'name': 'synthetic_lookup', 'parameters': {'type': 'object'}}], None, False, {})
    second, _ = provider._request(messages, None, {'type': 'object', 'properties': {'changed': {'type': 'string'}}}, False, {})
    assert first['messages'][0] == second['messages'][0] == messages[0]
    assert first['messages'][-1]['role'] == second['messages'][-1]['role'] == 'user'


def test_ollama_request_timeout_comes_from_config():
    import httpx
    import respx
    from backend.llm.ollama import OllamaProvider
    from backend.llm.config import load_config, model_config
    config = load_config()
    entry = next(row for row in config['roles']['plan']['chain'] if row['provider'] == 'ollama')
    spec = model_config('ollama', entry['model'], config)
    with respx.mock as mock:
        route = mock.post('http://localhost:11434/api/chat').mock(return_value=httpx.Response(
            200, json={'done': True, 'message': {'content': 'hello'}}))
        result = OllamaProvider(entry['model'], spec).generate([{'role': 'user', 'content': 'hello'}])
        assert result.text == 'hello'
        assert route.calls[0].request.extensions['timeout']['read'] == spec['request_timeout_seconds']
        assert config['agent']['model_timeout_seconds'] > spec['request_timeout_seconds']


def test_generation_schema_binds_hotel_price_to_quoted_place():
    from backend.agent.requirements import bind_itinerary_schema
    from backend.tools.models import Itinerary
    from backend.llm.validation import validate
    from backend.llm.types import InvalidOutput
    evidence = {'status': 'ok', 'tool': 'search_hotels', 'tool_result_id': 'quote', 'data': {'hotels': [
        {'name': 'Synthetic sample hotel', 'price_per_night': '100', 'total_price': '300', 'currency': 'USD'}]}}
    schema = bind_itinerary_schema(Itinerary, '', [evidence], [])
    candidate = itinerary('100')
    validate(candidate, schema)
    candidate['days'][0]['items'][0]['place'] = 'Synthetic museum'
    with pytest.raises(InvalidOutput):
        validate(candidate, schema)
    candidate['days'][0]['items'][0]['cost'] = None
    validate(candidate, schema)


def test_requested_accommodation_is_required_by_generation_schema():
    from backend.agent.requirements import bind_itinerary_schema
    from backend.tools.models import Itinerary
    from backend.llm.validation import validate
    from backend.llm.types import InvalidOutput
    evidence = {'status': 'ok', 'tool': 'search_hotels', 'tool_result_id': 'quote', 'data': {'hotels': [
        {'name': 'Synthetic sample hotel', 'price_per_night': '100', 'total_price': '300', 'currency': 'USD'}]}}
    schema = bind_itinerary_schema(Itinerary, 'Hotels 2027-04-10 through 2027-04-12', [evidence], [])
    candidate = itinerary('300')
    activity = dict(candidate['days'][0]['items'][0], id='activity', place='Synthetic museum', cost=None)
    candidate['days'][0]['items'].append(activity)
    for day in candidate['days'][1:]:
        day['items'][0]['cost'] = None
    validate(candidate, schema)
    candidate['days'][0]['items'][0]['cost'] = None
    with pytest.raises(InvalidOutput):
        validate(candidate, schema)
    candidate = itinerary('300')
    activity = dict(candidate['days'][0]['items'][0], id='activity', place='Synthetic museum', cost=None)
    candidate['days'][0]['items'].append(activity)
    for day in candidate['days'][1:]:
        day['items'][0]['cost'] = None
    candidate['days'][0]['items'][0]['start'] = '0800-09-00T09:00:00'
    with pytest.raises(InvalidOutput):
        validate(candidate, schema)


def test_activity_extraction_only_admits_names_present_in_cited_excerpt():
    class DestinationRuntime(Runtime):
        def execute(self, name, arguments):
            if name == 'search_destinations':
                return ToolResult(tool_result_id='destinations', tool=name, status='ok', source='synthetic-test',
                    fetched_at=utcnow(), cache_hit=False, data={'chunks': [{'chunk_id': 'synthetic-chunk',
                    'excerpt': 'Visit the Synthetic Museum.', 'title': 'Synthetic guide'}]})
            return super().execute(name, arguments)
    extract = Script([{'intent': 'new_trip', 'budget': 1500}, {'places': [
        {'name': 'Synthetic Museum', 'chunk_id': 'synthetic-chunk'},
        {'name': 'Invented Place', 'chunk_id': 'synthetic-chunk'},
        {'name': 'Visit', 'chunk_id': 'missing-chunk'}]}])
    candidate = itinerary()
    for day in candidate['days']:
        day['items'][0].update(place='Synthetic Museum', chunk_ids=['synthetic-chunk'])
    plan = Script([calls('search_destinations'), candidate])
    agent = Agent(store=MemoryTripStore(), runtime=DestinationRuntime(), providers=lambda role: extract if role == 'extract' else plan)
    response = run(agent, 'Lisbon museums 2027-04-10 through 2027-04-12 under 1500 USD')
    assert response.itinerary is not None
    assert plan.calls[-1][1]['response_schema']['$defs']['Item']['properties']['place']['enum'] == ['Synthetic Museum']
    assert len(extract.calls) == 2


def test_identical_edit_is_repaired_before_acceptance():
    store = MemoryTripStore()
    state = edit_state(store)
    unchanged = {'day': 2, 'operations': [{'op': 'replace_item', 'item_id': 'item-1', 'item': state['itinerary']['days'][1]['items'][0]}]}
    changed = {'day': 2, 'operations': [{'op': 'remove_item', 'item_id': 'item-1'}]}
    agent, _, plan = setup([{}, unchanged, changed], {'intent': 'edit_trip', 'day': 2}, store)
    result = run(agent, 'Make day 2 cheaper', state['id'])
    assert result.itinerary is not None
    assert result.itinerary.days[1].items == []
    assert 'edit_no_change' in json.dumps(plan.calls[-1][0])


def test_preference_only_edit_classification_does_not_ask_for_trip_day():
    agent, _, _ = setup([], {'intent': 'edit_trip', 'preference_proposal': {'pace': 'relaxed'}})
    result = run(agent, 'Remember my preference for a relaxed pace')
    assert result.preference_proposal.pace == 'relaxed'
    assert 'day to edit' not in result.message
    assert 'confirm preferences' in result.message
    assert agent.store.load(result.trip_id)['preferences'] == {}


def test_citation_only_edit_is_not_a_substantive_change():
    from backend.agent.requirements import substantive_itinerary
    before = itinerary()
    after = deepcopy(before)
    after['days'][1]['items'][0]['chunk_ids'] = ['synthetic-new-citation']
    assert substantive_itinerary(before) == substantive_itinerary(after)
    after['days'][1]['items'] = []
    assert substantive_itinerary(before) != substantive_itinerary(after)


def test_cheaper_unpriced_day_requests_removal_without_inventing_price():
    from backend.agent.requirements import bind_itinerary_schema
    from backend.agent.models import DayPatch
    from backend.llm.validation import validate
    from backend.llm.types import InvalidOutput
    schema = bind_itinerary_schema(DayPatch, 'Make day 2 cheaper', [], [], itinerary(), 2)
    validate({'day': 2, 'operations': [{'op': 'remove_item', 'item_id': 'item-1'}]}, schema)
    with pytest.raises(InvalidOutput):
        validate({'day': 2, 'operations': [{'op': 'replace_item', 'item_id': 'item-1', 'item': itinerary()['days'][1]['items'][0]}]}, schema)


@pytest.mark.parametrize('message, classified_day', [('Add more museums.', 1), ('Add more museums to day 99', 99)])
def test_edit_requires_explicit_existing_day_without_creating_version(message, classified_day):
    store = MemoryTripStore()
    state = store.create()
    state['itinerary'], state['budget'] = itinerary(), '1500'
    store.save(state, state['revision'])
    original = store.load(state['id'])
    agent, _, plan = setup([], {'intent': 'edit_trip', 'day': classified_day}, store)
    result = run(agent, message, state['id'])
    assert 'Which day should I change?' in result.message
    assert not result.issues and not plan.calls
    saved = store.load(state['id'])
    assert saved['itinerary'] == original['itinerary']
    assert saved['versions'] == original['versions']
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_agent] = lambda: agent
    response = TestClient(app).post(f"/api/trips/{state['id']}/undo")
    assert response.status_code == 409
    assert response.json()['detail'] == 'No earlier itinerary version'


@pytest.mark.parametrize('keep_safe', [True, False])
def test_sensitive_retrieval_is_withheld_before_planning_and_save(keep_safe):
    agent, runtime, plan = setup([calls('search_destinations'), {}, itinerary()])
    original_execute = runtime.execute
    safe = dict(chunk_id='synthetic-source', title='Synthetic museum', url=None,
                license='synthetic fixture', attribution='synthetic', excerpt='Visit the museum.')
    rejected = {**safe, 'chunk_id': 'rejected', 'excerpt': 'Synthetic passport details'}
    def execute(name, arguments):
        if name == 'search_destinations':
            return ToolResult(tool_result_id='retrieval', tool=name, status='ok',
                              data={'chunks': [rejected] + ([safe] if keep_safe else [])},
                              source='synthetic', fetched_at=utcnow(), cache_hit=False)
        return original_execute(name, arguments)
    runtime.execute = execute
    result = run(agent)
    assert result.itinerary is not None
    assert 'Synthetic passport details' not in json.dumps(plan.calls)
    assert agent.store.load(result.trip_id)['citations'] == ([safe] if keep_safe else [])
    assert result.tool_trace[0]['status'] == ('ok' if keep_safe else 'no_data')
    if not keep_safe:
        assert 'cannot find' in result.message


@pytest.mark.parametrize('first', [
    {'places': [{'name': 'Synthetic Museum', 'chunk_id': 'invented-id'}]},
    {'places': [{'name': 'Invented Museum', 'chunk_id': 'synthetic-chunk'}]},
    {'places': []},
])
def test_attraction_extraction_repairs_ungrounded_output(first):
    from backend.agent.attractions import extract_attractions
    script = Script([first, {'places': [{'name': 'Synthetic Museum', 'chunk_id': 'synthetic-chunk'}]}])
    async def generate(role, messages, **kwargs):
        return script.generate(messages, **kwargs)
    result = asyncio.run(extract_attractions([
        {'chunk_id': 'synthetic-chunk', 'excerpt': 'Visit Synthetic Museum.'},
    ], generate))
    assert result == ['Synthetic Museum']
    assert len(script.calls) == 2
    schema = script.calls[0][1]['response_schema']
    assert schema['$defs']['ActivityPlace']['properties']['chunk_id']['enum'] == ['synthetic-chunk']


def test_attraction_extraction_stops_after_two_repairs_without_inventing_places():
    from backend.agent.attractions import extract_attractions
    from backend.llm.types import InvalidOutput
    script = Script([{'places': [{'name': 'Invented Museum', 'chunk_id': 'synthetic-chunk'}]}] * 3)
    async def generate(role, messages, **kwargs):
        return script.generate(messages, **kwargs)
    with pytest.raises(InvalidOutput, match='No grounded activity'):
        asyncio.run(extract_attractions([
            {'chunk_id': 'synthetic-chunk', 'excerpt': 'Synthetic city transport overview.'},
        ], generate))
    assert len(script.calls) == 3


def test_cheaper_unpriced_day_skips_search_and_validates_patch():
    store = MemoryTripStore()
    state = edit_state(store)
    state['itinerary']['days'][1]['items'][0].update(cost=None, category='museum', place='Synthetic museum', tool_result_ids=[])
    state['trip_request'] = 'Lisbon museums and synthetic hotels 2027-04-10 through 2027-04-12 under 1500 USD'
    store.save(state, state['revision'])
    state = store.load(state['id'])
    patch = {'day': 2, 'operations': [{'op': 'remove_item', 'item_id': 'item-1'}]}
    agent, runtime, plan = setup([patch], intent={'intent': 'edit_trip', 'day': 2}, store=store)
    result = run(agent, 'Make day 2 cheaper', state['id'])
    assert result.itinerary is not None
    assert runtime.calls == ['validate_itinerary']
    assert len(plan.calls) == 1
    assert plan.calls[0][1]['response_schema']['title'] == 'DayPatch'
    updated = result.itinerary.model_dump(mode='json')
    assert updated['days'][1]['items'] == []
    for index in (0, 2):
        assert json.dumps(updated['days'][index]) == json.dumps(state['itinerary']['days'][index])


def test_missing_hotel_dates_clarifies_without_tools():
    agent, runtime, plan = setup([], intent={'intent':'new_trip','budget':600})
    result = run(agent, 'Plan Lisbon with hotels under 600 USD. I have not chosen dates yet.')
    assert 'arrival and departure dates' in result.message
    assert result.itinerary is None
    assert runtime.calls == [] and plan.calls == []


def test_hotel_schema_does_not_invent_optional_filters():
    from backend.agent.requirements import bind_tool_definitions
    agent, _, _ = setup([])
    tools = bind_tool_definitions(agent.definitions, 'Lisbon hotel 2027-04-10 through 2027-04-11 under 600 USD')
    hotel = next(tool for tool in tools if tool['name']=='search_hotels')['parameters']['properties']
    assert hotel['city']['enum'] == ['Lisbon']
    for key in ('max_price_per_night','min_rating','tier'):
        assert hotel[key] == {'type':'null'}


def test_generated_overlap_is_separated_but_explicit_times_are_preserved():
    from backend.agent.requirements import separate_generated_visits
    plan = itinerary()
    first = plan['days'][0]['items'][0]
    first['category'] = 'museum'
    second = {**first, 'id':'second'}
    plan['days'][0]['items'].append(second)
    original = deepcopy(plan)
    separate_generated_visits(plan, 'Plan a trip')
    assert second['start'] == first['end']
    assert second['end'] == '2027-04-10T12:00:00'
    separate_generated_visits(original, 'Visit at 10:00')
    assert original['days'][0]['items'][1]['start'] == first['start']


def test_activity_requires_its_own_supporting_excerpt():
    from backend.agent.requirements import grounded_activity_issues
    plan = itinerary()
    item = plan['days'][0]['items'][0]
    item.update(place='Synthetic Museum',chunk_ids=['wrong'])
    sources = [{'chunk_id':'right','excerpt':'Synthetic Museum displays paintings.'},
               {'chunk_id':'wrong','excerpt':'Synthetic Park has trees.'}]
    assert grounded_activity_issues(plan,sources)[0]['name']=='unsupported_activity'
    item['chunk_ids']=['right']
    assert not grounded_activity_issues(plan,sources)


def test_reference_link_sanitization_preserves_following_prose():
    from backend.security.content import sanitize_text
    assert 'Synthetic Museum' in sanitize_text('[x]: javascript:alert(1) Synthetic Museum')
    assert 'javascript:' not in sanitize_text('[x]: javascript:alert(1) Synthetic Museum')


def test_grounded_schema_couples_activity_name_to_its_source():
    from backend.agent.requirements import bind_itinerary_schema
    from backend.tools.models import Itinerary
    from jsonschema import validate, ValidationError
    citations=[{'chunk_id':'museum','excerpt':'Synthetic Museum'}, {'chunk_id':'park','excerpt':'Synthetic Park'}]
    evidence=[{'tool_result_id':'q','tool':'search_hotels','status':'ok','data':{'hotels':[
        {'name':'Synthetic Stay','currency':'USD','total_price':'10','price_per_night':'10'}]}}]
    schema=bind_itinerary_schema(Itinerary,'Lisbon museums 2027-04-10 through 2027-04-12',evidence,citations,activity_places=['Synthetic Museum'])
    item=itinerary()['days'][0]['items'][0]
    item.update(place='Synthetic Museum',chunk_ids=['museum'])
    for variant in schema['$defs']['UnpricedItem']['anyOf']:
        assert {'id','start','end','place','category','currency','cost'} <= set(variant['required'])
        assert variant['type'] == 'object'
    contract={'$defs':schema['$defs'],'$ref':'#/$defs/UnpricedItem'}
    validate(item,contract)
    item['chunk_ids']=['park']
    with pytest.raises(ValidationError):
        validate(item,contract)


def test_hotel_stay_is_a_checkin_visit_not_a_multiday_overlap():
    from backend.agent.requirements import separate_generated_visits
    plan=itinerary('100')
    item=plan['days'][0]['items'][0]
    item['end']='2027-04-12T10:00:00'
    separate_generated_visits(plan,'Plan a hotel stay')
    assert item['end']=='2027-04-10T10:30:00'
    assert item['cost']=='100' and item['tool_result_ids']==['quote']


def test_schema_repair_receives_rejected_candidate_as_data():
    from backend.llm.validation import validate_response
    from backend.llm.types import InvalidOutput
    candidate=itinerary()
    candidate['days'][0]['items'][0]['cost']='invented'
    try:
        validate_response(Response(text=json.dumps(candidate),provider='synthetic',model='synthetic'),
                          response_schema=__import__('backend.tools.models',fromlist=['Itinerary']).Itinerary)
    except InvalidOutput as exc:
        rejected=exc
    agent, _, plan=setup([{},rejected,itinerary()])
    result=run(agent)
    assert result.itinerary is not None
    assert 'invented' in plan.calls[-1][0][-1]['content']
    assert '<DATA>' in plan.calls[-1][0][-1]['content']


def test_attraction_extraction_rejects_destination_name_alone():
    from backend.agent.attractions import extract_attractions
    script=Script([{'places':[{'name':'Lisbon','chunk_id':'c'}]},
                   {'places':[{'name':'Synthetic Museum','chunk_id':'c'}]}])
    async def generate(role,messages,**kwargs):
        return script.generate(messages,**kwargs)
    result=asyncio.run(extract_attractions([{'chunk_id':'c','excerpt':'Lisbon has Synthetic Museum.'}],generate,['Lisbon']))
    assert result==['Synthetic Museum']
    assert len(script.calls)==2


def test_nonretryable_database_failure_stops_tool_loop():
    agent,runtime,plan=setup([calls('search_hotels')])
    def execute(name,arguments):
        return ToolResult(tool_result_id='failed',tool=name,status='error',
            data={'error':{'code':'internal_error','message':'Database unavailable','retryable':False}},
            source='synthetic',fetched_at=utcnow(),cache_hit=False)
    runtime.execute=execute
    result=run(agent)
    assert result.itinerary is None
    assert result.issues[0]['name']=='tool_unavailable'
    assert len(plan.calls)==1
    assert len(result.tool_trace)==1
