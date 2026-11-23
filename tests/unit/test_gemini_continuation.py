"""Synthetic signed tool turns; SDK serialization only, no network calls."""
import json
from types import SimpleNamespace

from google.genai import types
from backend.llm.gemini import GeminiProvider
from backend.llm.replay import fixture_key
from backend.observability.telemetry import redacted_prompt
from test_llm import MODEL, SPEC, TOOL, MESSAGES


def test_synthetic_gemini_signed_tool_content_round_trips():
    content = types.Content(role='model', parts=[
        types.Part(function_call=types.FunctionCall(name='lookup', args={'city': 'Synthetic City'}, id='synthetic-id'),
                   thought_signature=b'synthetic-opaque-signature'),
        types.Part(function_call=types.FunctionCall(name='lookup', args={'city': 'Synthetic Other'})),
    ])
    raw = types.GenerateContentResponse(candidates=[types.Candidate(content=content, finish_reason='STOP')])
    adapter = GeminiProvider(MODEL, SPEC, client=SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: raw)))
    response = adapter.generate(MESSAGES, tools=[TOOL])
    history = [*MESSAGES, {'role': 'assistant', 'content': '', 'tool_calls': [],
                           '_provider_continuation': response._continuation}]
    outgoing = adapter._request(history, [TOOL], None, {})
    sent = outgoing['contents'][-1]
    assert sent == content
    assert sent.parts[0].thought_signature == b'synthetic-opaque-signature'
    assert len(sent.parts) == 2
    assert '_continuation' not in response.model_dump_json()
    assert 'thought_signature' not in redacted_prompt(history)
    plain = [{k: v for k, v in row.items() if k != '_provider_continuation'} for row in history]
    assert fixture_key('synthetic', MODEL, history) == fixture_key('synthetic', MODEL, plain)
    json.dumps(history)  # Continuation remains compatible with context/token estimates.


def test_synthetic_agent_carries_continuation_to_next_generation():
    from test_agent_loop import setup, run, itinerary
    from backend.llm.types import Response, ToolCall
    response = Response(provider='synthetic', model=MODEL, tool_calls=[ToolCall(name='search_hotels', arguments={})])
    response._continuation = {'provider': 'synthetic', 'model': MODEL, 'content': {'synthetic': True}}
    agent, _, plan = setup([response, {}, itinerary()])
    run(agent)
    assert any(row.get('_provider_continuation') == response._continuation for row in plan.calls[-1][0])


def test_synthetic_parallel_tool_responses_share_one_content_turn():
    adapter = GeminiProvider(MODEL, SPEC)
    history = [*MESSAGES,
               {'role': 'tool', 'name': 'lookup', 'content': {'synthetic': 1}},
               {'role': 'tool', 'name': 'lookup', 'content': {'synthetic': 2}}]
    outgoing = adapter._request(history, [TOOL], None, {})
    assert len(outgoing['contents']) == 2
    assert [p['function_response']['response'] for p in outgoing['contents'][-1]['parts']] == [{'synthetic': 1}, {'synthetic': 2}]


def test_synthetic_invalid_output_logs_http_status_without_payload(caplog):
    import logging
    from backend.agent.errors import failure_issue
    from backend.llm.types import InvalidOutput
    cause = Exception('synthetic-private-payload')
    cause.code = 400
    error = InvalidOutput('Provider output rejected')
    error.__cause__ = cause
    with caplog.at_level(logging.WARNING):
        failure_issue(error, 'plan')
    assert 'reason=http_error http_status=400' in caplog.text
    assert 'synthetic-private-payload' not in caplog.text
