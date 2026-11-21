"""Synthetic scripted tests of the pipeline, not model behavior."""
import asyncio
from collections import Counter

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.agent.api import router
from backend.agent.deep_plan import DeepPlanAgent
from backend.agent.loop import Agent
from backend.agent.models import ChatRequest, ChatResponse
from backend.agent.store import MemoryTripStore
from backend.llm.config import load_config
from backend.tools.models import Itinerary
from test_agent_loop import Runtime, itinerary


REQUEST = ChatRequest(message='Plan Lisbon from 2027-04-10 through 2027-04-12 under $250 USD.')


class SyntheticRuntime(Runtime):
    async def aexecute(self, name, arguments):
        return self.execute(name, arguments)


class SyntheticDays(DeepPlanAgent):
    def __init__(self, failures=(), cost=None):
        super().__init__(Agent(store=MemoryTripStore(), runtime=SyntheticRuntime(), config=load_config()))
        self.failures, self.cost = failures, cost
        self.counts = Counter()
        self.active = self.maximum = 0

    async def plan_day(self, request, day, **kwargs):
        self.counts[day] += 1
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        if (day, self.counts[day]) in self.failures:
            raise ValueError('Synthetic day failure')
        value = itinerary(self.cost)
        value['days'] = [row for row in value['days'] if row['date'] == day]
        return ChatResponse(trip_id='synthetic', message='Synthetic day', itinerary=Itinerary.model_validate(value))


def test_deep_plan_runs_days_in_parallel():
    planner = SyntheticDays()
    result = asyncio.run(planner.chat(REQUEST))
    assert planner.maximum == 3
    assert result.itinerary and len(result.itinerary.days) == 3
    assert len(planner.store.versions(result.trip_id)) == 1


def test_deep_plan_retries_failed_day_once():
    planner = SyntheticDays({('2027-04-11', 1)})
    result = asyncio.run(planner.chat(REQUEST))
    assert result.itinerary
    assert planner.counts == {'2027-04-10': 1, '2027-04-11': 2, '2027-04-12': 1}


def test_deep_plan_reports_partial_failure():
    planner = SyntheticDays({('2027-04-11', 1), ('2027-04-11', 2)})
    result = asyncio.run(planner.chat(REQUEST))
    assert result.itinerary is None
    assert result.issues[0]['day'] == '2027-04-11'
    assert 'No partial itinerary was saved' in result.message
    assert planner.store.versions(result.trip_id) == []


def test_deep_plan_global_validation_catches_budget_overrun():
    planner = SyntheticDays(cost='100')
    result = asyncio.run(planner.chat(REQUEST))
    assert result.itinerary
    assert result.budget_met is False
    assert any(i['name'] == 'budget_exceeded' for i in result.issues)
    assert 'exceeds' in result.message


def test_config_endpoint_reports_provider(monkeypatch):
    monkeypatch.setenv('PUBLIC_DEMO', 'true')
    app = FastAPI()
    app.include_router(router)
    result = TestClient(app).get('/api/config')
    assert result.status_code == 200
    assert result.json()['provider'] == load_config()['roles']['plan']['chain'][0]['provider']
    assert result.json()['demo_mode'] is True
    assert result.json()['retrieval_mode'] == 'fts'
    assert 'SECRET' not in result.text


def test_synthetic_deep_plan_cancellation_stops_workers():
    async def run():
        planner = SyntheticDays()
        started, stopped = asyncio.Event(), asyncio.Event()
        async def blocked(*args, **kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        planner.plan_day = blocked
        task = asyncio.create_task(planner.chat(REQUEST))
        await started.wait()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert stopped.is_set()
        assert all(not state['versions'] for state in planner.store.states.values())
    asyncio.run(run())


def test_synthetic_day_worker_reuses_loop_and_enforces_assigned_day():
    from test_agent_loop import Script
    class AsyncScript(Script):
        async def agenerate(self, messages, **kwargs):
            return self.generate(messages, **kwargs)
    value = itinerary()
    value['days'] = value['days'][:1]
    script = AsyncScript([{'intent': 'new_trip', 'budget': 250}, {}, value])
    planner = DeepPlanAgent(Agent(store=MemoryTripStore(), runtime=SyntheticRuntime(), providers=lambda role: script))
    planner.turn_state = planner.store.create()
    async def noop(event):
        pass
    from backend.agent.models import Usage
    from uuid import uuid4
    result = asyncio.run(planner.plan_day(REQUEST, '2027-04-10', user_id='synthetic-user', emit=noop, request_id=uuid4(), usage=Usage()))
    assert result.itinerary, result.issues
    assert len(result.itinerary.days) == 1
    assert script.calls[-1][1]['response_schema']['properties']['days']['maxItems'] == 1
    assert planner.store.versions(planner.turn_state['id']) == []


def test_synthetic_demo_retrieval_never_loads_models(monkeypatch):
    from backend.rag import search
    monkeypatch.setenv('PUBLIC_DEMO', 'true')
    def denied():
        raise AssertionError('Demo must not load embedding/reranking models')
    monkeypatch.setattr(search, 'get_local_embedder', denied)
    monkeypatch.setattr(search, 'get_reranker', denied)
    # Stop at the DB boundary, after selecting the retrieval mode and lazy resources.
    class DatabaseReached(Exception):
        pass
    def database():
        raise DatabaseReached()
    monkeypatch.setattr(search, 'SessionLocal', database)
    import pytest
    with pytest.raises(DatabaseReached):
        search.search('synthetic query', mode='hybrid', rerank=True)


def test_synthetic_deep_plan_reserves_all_attempts_and_checks_ownership():
    import pytest
    from fastapi import HTTPException
    from backend.agent.api import admit_turn
    from types import SimpleNamespace
    store = MemoryTripStore()
    foreign = store.for_owner('synthetic-owner-b').create()
    agent = Agent(store=store.for_owner('synthetic-owner-a'), runtime=SyntheticRuntime())
    planner = DeepPlanAgent(agent)
    charges = []
    service = SimpleNamespace(reserve_turn=lambda user, tokens: charges.append((user, tokens)))
    with pytest.raises(HTTPException) as error:
        admit_turn(REQUEST.model_copy(update={'trip_id': foreign['id']}), planner, service, 'synthetic-owner-a')
    assert error.value.status_code == 404
    assert charges == []
    admit_turn(REQUEST, planner, service, 'synthetic-owner-a')
    assert charges == [('synthetic-owner-a', 3 * 2 * planner.config['deep_plan']['tokens_per_attempt'])]


def test_synthetic_deep_plan_requires_full_stay_hotel_total():
    from backend.agent.deep_plan import lodging_total_issues
    value = itinerary('100')
    value['days'] = value['days'][:1]
    rows = [dict(tool_result_id='quote', status='ok', tool='search_hotels', data={'hotels': [
        dict(name='Synthetic sample hotel', currency='USD', price_per_night='100', total_price='300')
    ]})]
    assert lodging_total_issues(value, rows)[0]['name'] == 'lodging_total_required'
    value['days'][0]['items'][0]['cost'] = '300'
    assert lodging_total_issues(value, rows) == []
