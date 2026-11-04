"""Synthetic conversations and mocked transports; no live network or models."""
import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import respx

from backend.agent.api import get_agent, router
from backend.agent.events import EVENT_ADAPTER
from backend.agent.loop import Agent
from backend.agent.models import ChatRequest
from backend.agent.store import MemoryTripStore
from backend.agent.streaming import stream_events
from backend.llm.limits import TokenBucket
from backend.llm.ollama import OllamaProvider
from backend.llm.replay import ReplayProvider, fixture_key
from backend.llm.router import ManagedProvider
from backend.llm.types import InvalidOutput, QuotaExhausted, RateLimited, Response
from test_agent_loop import Runtime, Script, calls, itinerary, offline  # noqa: F401


class AsyncScript(Script):
    async def agenerate(self, messages, **kwargs):
        return self.generate(messages, **kwargs)


class AsyncRuntime(Runtime):
    async def aexecute(self, name, arguments):
        return self.execute(name, arguments)


def agent_for(plan=None, extract=None, runtime=None):
    plan = plan or AsyncScript([calls('search_hotels'), {}, itinerary()])
    extract = extract or AsyncScript([{'intent': 'new_trip', 'budget': 1500}])
    return Agent(store=MemoryTripStore(), runtime=runtime or AsyncRuntime(),
                 providers=lambda role: extract if role == 'extract' else plan)


def app_for(agent):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_agent] = lambda: agent
    return app


def parse_frames(frames):
    return [EVENT_ADAPTER.validate_json(frame.decode().split('data: ', 1)[1].strip()).model_dump(mode='json')
            for frame in frames if not frame.startswith(b':')]


async def collect(agent, **kwargs):
    return [frame async for frame in stream_events(agent, ChatRequest(message='Synthetic trip request'), uuid4(), **kwargs)]


def test_event_order_for_scripted_conversation(tmp_path):
    class SyntheticFixtureScript(AsyncScript):
        async def agenerate(self, messages, tools=None, response_schema=None, **opts):
            response = await super().agenerate(messages, tools=tools, response_schema=response_schema, **opts)
            key = fixture_key('synthetic', 'synthetic-test', messages, tools, response_schema)
            (tmp_path / f'{key}.json').write_text(json.dumps({'provenance': 'synthetic', 'response': response.model_dump(mode='json')}))
            return response

    class FrozenRuntime(AsyncRuntime):
        def execute(self, name, arguments):
            result = super().execute(name, arguments)
            result.fetched_at = datetime(2027, 1, 1, tzinfo=timezone.utc)
            return result

    async def scenario():
        fixture_agent = agent_for(runtime=FrozenRuntime(), plan=SyntheticFixtureScript([calls('search_hotels'), {}, itinerary()]),
                                  extract=SyntheticFixtureScript([{'intent': 'new_trip', 'budget': 1500}]))
        await collect(fixture_agent)
        replay = ReplayProvider('synthetic', 'synthetic-test', tmp_path)
        agent = agent_for(plan=replay, extract=replay, runtime=FrozenRuntime())
        events = parse_frames(await collect(agent))
        assert events[0]['type'] == 'message_start'
        assert events[-1]['type'] == 'done'
        assert len({event['request_id'] for event in events}) == 1
        assert [event['type'] for event in events if event['type'] != 'token'] == [
            'message_start', 'tool_start', 'tool_end', 'tool_start', 'tool_end', 'itinerary_update', 'citations', 'done']
        for start, end in zip([e for e in events if e['type'] == 'tool_start'], [e for e in events if e['type'] == 'tool_end'], strict=True):
            assert start['call_id'] == end['call_id'] and start['tool'] == end['tool']
            assert end['status'] == 'ok' and end['duration_ms'] >= 0
        done = events[-1]
        assert ''.join(e['text'] for e in events if e['type'] == 'token') == done['message']
        assert events[-3]['itinerary']['days']
        assert len(done['usage']['calls']) == 4
        assert agent.store.load(done['trip_id'])['itinerary'] == events[-3]['itinerary']
    asyncio.run(scenario())


def test_heartbeat_sent_during_slow_tool():
    async def scenario():
        entered, release, clock_ready = asyncio.Event(), asyncio.Event(), asyncio.Event()
        tick = asyncio.get_running_loop().create_future()

        async def fake_sleep(seconds):
            assert seconds == 15
            clock_ready.set()
            await tick

        class SlowRuntime(AsyncRuntime):
            async def aexecute(self, name, arguments):
                if name == 'search_hotels':
                    entered.set()
                    await release.wait()
                return await super().aexecute(name, arguments)

        stream = stream_events(agent_for(runtime=SlowRuntime()), ChatRequest(message='Synthetic request'), uuid4(), sleep=fake_sleep)
        assert b'message_start' in await anext(stream)
        assert b'tool_start' in await anext(stream)
        await entered.wait()
        await clock_ready.wait()
        tick.set_result(None)
        assert await anext(stream) == b': heartbeat\n\n'
        release.set()
        # Use close here to exercise cancellation while the slow handler is still resumable.
        await stream.aclose()
    asyncio.run(scenario())


async def disconnect_request(agent, entered, *, send_failure=False):
    app = app_for(agent)
    first = True
    sent = []

    async def receive():
        nonlocal first
        if first:
            first = False
            return {'type': 'http.request', 'body': b'{"message":"Synthetic request"}', 'more_body': False}
        if send_failure:
            await asyncio.Future()
        await entered.wait()
        return {'type': 'http.disconnect'}

    async def send(message):
        sent.append(message)
        if send_failure and b'event: tool_start' in message.get('body', b''):
            await entered.wait()
            raise OSError('Synthetic closed socket')

    scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'}, 'http_version': '1.1',
             'method': 'POST', 'scheme': 'http', 'path': '/api/chat/stream', 'raw_path': b'/api/chat/stream',
             'query_string': b'', 'root_path': '', 'headers': [(b'content-type', b'application/json')],
             'client': ('synthetic-client', 1), 'server': ('synthetic-server', 80)}
    await asyncio.wait_for(app(scope, receive, send), 2)
    return sent


def test_client_disconnect_cancels_agent_task():
    async def scenario():
        entered, cancelled = asyncio.Event(), asyncio.Event()
        requests = []

        async def upstream(request):
            requests.append(request)
            entered.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()

        with respx.mock as mock:
            mock.post('http://localhost:11434/api/chat').mock(side_effect=upstream)
            provider = OllamaProvider('synthetic-test', {'supports': {'structured_output': True}})
            counter, bucket = Counter(), TokenBucket(100, 10000)
            managed = ManagedProvider(provider, SPEC, SETTINGS, counter=counter, bucket=bucket)
            agent = agent_for(extract=managed)
            sent = await disconnect_request(agent, entered)
            assert cancelled.is_set() and len(requests) == 1
            assert counter.count == 1 and bucket.available['requests'] == 99
            assert any(b'message_start' in event.get('body', b'') for event in sent)
            assert not any(b'event: done' in event.get('body', b'') for event in sent)
            assert all(not state['history'] and not state['versions'] for state in agent.store.states.values())
            assert not [task for task in asyncio.all_tasks() if task.get_name().startswith('agent-stream-')]
    asyncio.run(scenario())


def test_error_event_is_typed_and_final():
    events = parse_frames(asyncio.run(collect(agent_for(extract=AsyncScript([InvalidOutput('Synthetic secret: never expose')])))))
    assert [event['type'] for event in events] == ['message_start', 'error']
    assert events[-1]['code'] == 'invalid_output'
    assert 'secret' not in json.dumps(events)


def test_non_streaming_endpoint_unchanged():
    def conversation():
        return agent_for(plan=AsyncScript([{}, itinerary()]))
    original = TestClient(app_for(conversation())).post('/api/chat', json={'message': 'Synthetic request'})
    assert original.status_code == 200
    expected = original.json()
    response = TestClient(app_for(conversation())).post('/api/chat/stream', json={'message': 'Synthetic request'})
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/event-stream')
    events = parse_frames([frame.encode() for frame in response.text.split('\n\n') if frame])
    assert response.headers['x-request-id'] == events[0]['request_id']
    assert events[-1]['message'] == expected['message']
    assert events[-1]['usage'] == expected['usage']
    assert next(e for e in events if e['type'] == 'itinerary_update')['itinerary'] == expected['itinerary']
    assert set(expected) == {'trip_id', 'message', 'itinerary', 'diff', 'citations', 'tool_trace', 'budget_met', 'usage', 'issues', 'preference_proposal'}


def test_no_secrets_in_tool_start_events():
    call = calls('search_hotels')
    call.tool_calls[0].arguments = {'city': 'Synthetic Bearer hidden-value', 'api_key': 'synthetic-key',
                                    'nested': {'password': 'synthetic-password'}, 'check_in': 'synthetic-secret-date'}
    events = parse_frames(asyncio.run(collect(agent_for(plan=AsyncScript([call, {}, itinerary()])))))
    starts = [e for e in events if e['type'] == 'tool_start']
    summary = starts[0]['argument_summary']
    assert summary == {'fields': ['check_in', 'city'], 'omitted_fields': 2}
    serialized = json.dumps(starts)
    for value in ('hidden-value', 'synthetic-key', 'synthetic-password', 'synthetic-secret-date', 'api_key', 'password'):
        assert value not in serialized


def test_request_timeout_cancels_provider_and_is_final():
    async def scenario():
        cancelled = asyncio.Event()
        class SlowProvider:
            async def agenerate(self, *args, **kwargs):
                try:
                    await asyncio.Future()
                finally:
                    cancelled.set()
        agent = agent_for(extract=SlowProvider())
        agent.settings['request_timeout_seconds'] = 0.02
        events = parse_frames(await collect(agent))
        assert cancelled.is_set()
        assert events[-1]['type'] == 'error' and events[-1]['code'] == 'timeout'
        assert all(not state['history'] for state in agent.store.states.values())
    asyncio.run(scenario())


class Counter:
    def __init__(self):
        self.count = 0

    async def areserve(self, *args):
        self.count += 1


SPEC = {'limits': {'rpm': 100, 'tpm': 10000, 'rpd': 100}}
SETTINGS = {'max_output_tokens': 100, 'retry': {'attempts': 1}}


def test_cancel_before_quota_admission_refunds_minute_bucket():
    async def scenario():
        entered = asyncio.Event()
        class PendingCounter(Counter):
            async def areserve(self, *args):
                entered.set()
                await asyncio.Future()
        bucket, counter = TokenBucket(100, 10000), PendingCounter()
        provider = AsyncScript([])
        provider.provider, provider.model = 'synthetic', 'synthetic-test'
        managed = ManagedProvider(provider, SPEC, SETTINGS, bucket=bucket, counter=counter)
        task = asyncio.create_task(managed.agenerate([]))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert bucket.available == bucket.capacity and not provider.calls and counter.count == 0
    asyncio.run(scenario())


def test_async_quota_denial_refunds_admission_without_provider_call():
    async def scenario():
        class Exhausted(Counter):
            async def areserve(self, *args):
                raise QuotaExhausted('Synthetic quota exhausted')
        bucket = TokenBucket(100, 10000)
        provider = AsyncScript([])
        provider.provider, provider.model = 'synthetic', 'synthetic-test'
        managed = ManagedProvider(provider, SPEC, SETTINGS, bucket=bucket, counter=Exhausted())
        with pytest.raises(QuotaExhausted):
            await managed.agenerate([])
        assert not provider.calls and bucket.available == bucket.capacity
    asyncio.run(scenario())


def test_cancel_during_retry_does_not_retry_or_refund_sent_request():
    async def scenario():
        sleeping = asyncio.Event()
        async def pause(delay):
            sleeping.set()
            await asyncio.Future()
        provider = AsyncScript([RateLimited('Synthetic upstream 429')])
        provider.provider, provider.model = 'synthetic', 'synthetic-test'
        counter = Counter()
        managed = ManagedProvider(provider, SPEC, SETTINGS, counter=counter, bucket=TokenBucket(100, 10000),
                                  retry_options={'attempts': 3, 'sleep': pause})
        task = asyncio.create_task(managed.agenerate([]))
        await sleeping.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(provider.calls) == counter.count == 1
    asyncio.run(scenario())


def test_async_success_reconciles_actual_tokens():
    async def scenario():
        provider = AsyncScript([Response(provider='synthetic', model='synthetic-test', tokens_in=4, tokens_out=2)])
        provider.provider, provider.model = 'synthetic', 'synthetic-test'
        bucket = TokenBucket(100, 10000, clock=lambda: 0)
        managed = ManagedProvider(provider, SPEC, SETTINGS, counter=Counter(), bucket=bucket)
        await managed.agenerate([])
        assert bucket.available == {'requests': 99, 'tokens': 9994}
    asyncio.run(scenario())


def test_send_failure_cancels_tool_and_agent():
    async def scenario():
        entered, cancelled = asyncio.Event(), asyncio.Event()
        class SlowRuntime(AsyncRuntime):
            async def aexecute(self, *args):
                entered.set()
                try:
                    await asyncio.Future()
                finally:
                    cancelled.set()
        agent = agent_for(runtime=SlowRuntime())
        await disconnect_request(agent, entered, send_failure=True)
        assert cancelled.is_set()
        assert all(not state['history'] for state in agent.store.states.values())
        assert not [task for task in asyncio.all_tasks() if task.get_name().startswith('agent-stream-')]
    asyncio.run(scenario())


@pytest.mark.parametrize('cancel', [False, True])
def test_async_gemini_sdk_context_closes_on_success_and_cancel(cancel):
    from types import SimpleNamespace
    from backend.llm.gemini import GeminiProvider
    async def scenario():
        entered = asyncio.Event()
        class SDKContext:
            closed = False
            def __init__(self):
                self.models = SimpleNamespace(generate_content=self.generate_content)
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                self.closed = True
            async def generate_content(self, **kwargs):
                assert kwargs['config']['automatic_function_calling'] == {'disable': True}
                entered.set()
                if cancel:
                    await asyncio.Future()
                return {'candidates': [{'content': {'parts': [{'text': 'Synthetic response'}]}, 'finish_reason': 'STOP'}],
                        'usage_metadata': {'prompt_token_count': 3, 'candidates_token_count': 2}}
        context = SDKContext()
        provider = GeminiProvider('synthetic-test', {}, client=SimpleNamespace(aio=context))
        task = asyncio.create_task(provider.agenerate([{'role': 'user', 'content': 'Synthetic request'}]))
        await entered.wait()
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            result = await task
            assert result.text == 'Synthetic response' and result.tokens_in == 3 and result.tokens_out == 2
        assert context.closed
    asyncio.run(scenario())


def test_cancelled_tool_worker_does_not_store_a_result():
    import threading
    from dataclasses import replace
    from types import SimpleNamespace
    from backend.tools.registry import REGISTRY
    from backend.tools.runtime import ToolRuntime
    async def scenario():
        entered, finished = threading.Event(), threading.Event()
        stored = []
        def handler(request, context):
            entered.set()
            try:
                while True:
                    context.pause(1)
            finally:
                finished.set()
        definition = replace(REGISTRY['search_hotels'], handler=handler)
        runtime = ToolRuntime(definitions={'search_hotels': definition}, store=SimpleNamespace(save_result=stored.append))
        try:
            task = asyncio.create_task(runtime.aexecute('search_hotels', {'city': 'Synthetic city', 'check_in': '2027-04-10', 'check_out': '2027-04-12'}))
            assert await asyncio.to_thread(entered.wait, 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert await asyncio.to_thread(finished.wait, 1)
            assert stored == []
        finally:
            runtime.close()
    asyncio.run(scenario())


def test_missing_gemini_key_does_not_consume_quota(monkeypatch):
    from backend.llm.gemini import GeminiProvider
    from backend.llm.types import ProviderUnavailable
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    async def scenario():
        counter, bucket = Counter(), TokenBucket(100, 10000)
        managed = ManagedProvider(GeminiProvider('synthetic-test', {}), SPEC, SETTINGS, counter=counter, bucket=bucket)
        with pytest.raises(ProviderUnavailable):
            await managed.agenerate([])
        assert counter.count == 0 and bucket.available == bucket.capacity
    asyncio.run(scenario())


def test_unexpected_producer_cancellation_still_ends_connected_stream():
    async def scenario():
        class CancelledAgent:
            settings = {'request_timeout_seconds': 10}
            async def chat(self, *args, **kwargs):
                raise asyncio.CancelledError()
        frames = await asyncio.wait_for(collect(CancelledAgent()), 1)
        assert [event['type'] for event in parse_frames(frames)] == ['message_start', 'error']
    asyncio.run(scenario())
