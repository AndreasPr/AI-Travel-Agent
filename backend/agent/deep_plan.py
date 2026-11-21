"""Bounded day workers reuse the grounded agent; only the merge is persisted."""
import asyncio
from copy import copy, deepcopy
from datetime import date, timedelta
from uuid import uuid4

from backend.agent.models import ChatResponse, Usage
from backend.agent.policy import sensitive_state
from backend.agent.requirements import requested_dates
from backend.agent.store import MemoryTripStore
from backend.security.arguments import explicit_budget, request_facts
from backend.tools.models import Itinerary


class DeepPlanAgent:
    def __init__(self, agent):
        self.agent = agent
        self.config = agent.config
        self.settings = {**agent.settings, 'request_timeout_seconds': self.config['deep_plan']['request_timeout_seconds']}

    def __getattr__(self, name):
        return getattr(self.agent, name)

    def dates(self, request):
        dates = requested_dates(request_facts(request.message))
        if not dates or explicit_budget(None, request.message) is None:
            raise ValueError('Deep planning requires explicit start/end dates and a budget.')
        start, end = map(date.fromisoformat, dates)
        count = (end - start).days + 1
        if not 2 <= count <= self.config['deep_plan']['max_days']:
            raise ValueError('Deep planning requires between 2 and the configured maximum trip days.')
        return [(start + timedelta(days=i)).isoformat() for i in range(count)]

    def reservation(self, request):
        return len(self.dates(request)) * 2 * self.config['deep_plan']['tokens_per_attempt']

    async def plan_day(self, request, day, *, user_id, emit, request_id, usage):
        worker = copy(self.agent)
        worker.store = MemoryTripStore()
        private = worker.store.create()
        private['id'] = self.turn_state['id']
        private['preferences'] = deepcopy(self.turn_state['preferences'])
        worker.store.states = {private['id']: deepcopy(private)}
        worker.planning_day = day
        worker.config = deepcopy(self.config)
        worker.config['guardrails']['turn_tokens'] = self.config['deep_plan']['tokens_per_attempt']
        # Shared guard/provider counters remain authoritative across all workers.
        return await worker.chat(request.model_copy(update={'trip_id': private['id']}), event_sink=emit,
                                 request_id=request_id, usage=usage, user_id=user_id)

    async def chat(self, request, *, event_sink=None, request_id=None, usage=None, user_id='local-cli'):
        dates = self.dates(request)
        state = self.store.load(request.trip_id) if request.trip_id else self.store.create()
        self.turn_state = state
        revision = state['revision']
        output = ChatResponse(trip_id=state['id'], message='', usage=usage or Usage())
        semaphore = asyncio.Semaphore(self.config['deep_plan']['concurrency'])
        request_id = request_id or uuid4()

        async def emit(event):
            if event_sink:
                await event_sink(event)

        async def day_task(day):
            async with semaphore:
                for _attempt in range(2):
                    measured = Usage()
                    try:
                        result = await asyncio.wait_for(self.plan_day(request, day, user_id=user_id, emit=emit,
                            request_id=request_id, usage=measured), self.config['deep_plan']['day_timeout_seconds'])
                        output.tool_trace.extend(result.tool_trace)
                        if result.itinerary and [d.date.isoformat() for d in result.itinerary.days] == [day]:
                            return result
                    except (TimeoutError, ValueError):
                        pass
                    except Exception:
                        # Provider/tool failures are reported without exposing internal details.
                        pass
                    finally:
                        for key in ('tokens_in', 'tokens_out', 'cached_tokens', 'uncached_tokens'):
                            setattr(output.usage, key, getattr(output.usage, key) + getattr(measured, key))
                        output.usage.calls.extend(measured.calls)
                output.issues.append(dict(name='day_failed', severity='error', day=day,
                    message=f'Planning failed for {day} after two attempts.'))
                return None

        tasks = [asyncio.create_task(day_task(day)) for day in dates]
        try:
            results = await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        if any(result is None for result in results):
            output.message = 'Deep planning was incomplete. Failed days: ' + ', '.join(i['day'] for i in output.issues) + '. No partial itinerary was saved.'
            return output
        candidate = Itinerary(trip=results[0].itinerary.trip, days=[r.itinerary.days[0] for r in results])
        if (candidate.trip.start_date.isoformat(), candidate.trip.end_date.isoformat()) != (dates[0], dates[-1]):
            output.issues = [dict(name='dates_mismatch', severity='error', message='Merged trip dates did not match the request.')]
            output.message = 'The merged itinerary was rejected.'
            return output
        budget = explicit_budget(None, request.message)
        validation = await asyncio.wait_for(self.runtime.aexecute('validate_itinerary',
            {'itinerary': candidate.model_dump(mode='json'), 'budget': str(budget)}), 20)
        output.tool_trace.append(validation.model_dump(mode='json'))
        if validation.status != 'ok':
            output.message = 'Global itinerary validation was unavailable; nothing was saved.'
            output.issues = [dict(name='validation_unavailable', severity='error', message=output.message)]
            return output
        output.issues = [issue.model_dump() for issue in validation.data.issues]
        errors = [i for i in output.issues if i['severity'] == 'error']
        if any(i['name'] != 'budget_exceeded' for i in errors):
            output.message = 'The merged itinerary failed global validation; nothing was saved.'
            return output
        citations = {c['chunk_id']: c for result in results for c in result.citations}
        state['citations'] = list(citations.values())
        state['evidence'] = list(dict.fromkeys([*state['evidence'], *(r['tool_result_id'] for r in output.tool_trace if r.get('tool_result_id') and r['status'] == 'ok')]))
        self.agent._accept(state, candidate.model_dump(mode='json'), budget, None, output.issues, output)
        if errors:
            output.budget_met = False
            output.message = 'The merged plan exceeds your budget; budget_met=false. Review or edit it before use.'
        if any(r['status'] == 'no_data' for r in output.tool_trace):
            output.message += ' I cannot find matching data for some requested tools.'
        output.message += ' Inventory quotes are synthetic, not booking availability.'
        state['trip_request'] = request.message
        state['history'].extend([{'role': 'user', 'content': request.message}, {'role': 'assistant', 'content': output.message}])
        if sensitive_state(state):
            output.itinerary = None
            output.budget_met = None
            output.citations = []
            output.message = 'Generated sensitive content was rejected and was not saved.'
            output.issues = [dict(name='sensitive_content', severity='error', message=output.message)]
            return output
        self.store.save(state, revision)
        return output


def lodging_total_issues(candidate, results):
    from decimal import Decimal
    hotels = {r['tool_result_id']: r['data'].get('hotels', []) for r in results
              if r.get('tool') == 'search_hotels' and r.get('status') == 'ok'}
    issues = []
    for day in candidate['days']:
        for item in day['items']:
            if item['cost'] is None or item['category'].casefold() != 'hotel':
                continue
            rows = [hotel for key in item['tool_result_ids'] for hotel in hotels.get(key, [])]
            if not any(hotel.get('name') == item['place'] and hotel['currency'] == item['currency'] and
                       abs(Decimal(str(hotel['total_price'])) - Decimal(str(item['cost']))) <= Decimal('0.01') for hotel in rows):
                issues.append(dict(name='lodging_total_required', severity='error',
                    message='The first day owns lodging: use the full-stay total_price from the hotel tool, charged once.'))
    return issues
