"""Scripted tests of the pipeline, not model behavior. No provider/network calls."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path

from backend.llm.types import Response, ToolCall
from backend.llm.validation import schema_dict

FIXTURE = Path(__file__).resolve().parents[2] / 'tests/fixtures/synthetic/synthetic_chat.json'


def enabled():
    if os.getenv('LLM_STUB') != '1':
        return False
    from backend.env import config
    if config('APP_ENV', default='development').lower() != 'development' or os.getenv('TEST_SUITE_MODE') != '1':
        raise RuntimeError('LLM_STUB requires development and TEST_SUITE_MODE=1; forbidden in production')
    return True


class SyntheticProvider:
    provider = 'synthetic'
    model = 'synthetic-pipeline'

    def __init__(self, fixture=None):
        self.fixture = fixture or json.loads(FIXTURE.read_text())

    async def agenerate(self, messages, tools=None, response_schema=None, **opts):
        # Yield to cancellation and leave progress visible in the synthetic browser scenario.
        await asyncio.sleep(0.1)
        schema = schema_dict(response_schema) or {}
        title = schema.get('title')
        if title == 'Intent':
            value = self.fixture['intent']
        elif title == 'Itinerary':
            value = self.fixture['itinerary']
        elif tools and not any(row.get('role') == 'tool' for row in messages):
            return Response(provider=self.provider, model=self.model, tool_calls=[
                ToolCall(id='synthetic-retrieval', name='search_destinations', arguments={'query': 'museum', 'city': 'Lisbon'})])
        else:
            value = {}
        return Response(text=json.dumps(value), provider=self.provider, model=self.model, finish_reason='stop')


def synthetic_agent(store=None, runtime=None):
    from backend.agent.loop import Agent
    from backend.tools.runtime import ToolRuntime
    fixture = json.loads(FIXTURE.read_text())
    if runtime is None:
        import httpx
        def denied(request):
            raise AssertionError('Synthetic pipeline must not use external HTTP')
        runtime = ToolRuntime(search=lambda *args, **kwargs: [deepcopy(fixture['chunk'])],
                              client=httpx.Client(transport=httpx.MockTransport(denied)))
    return Agent(store=store, runtime=runtime, providers=lambda role: SyntheticProvider(fixture))
