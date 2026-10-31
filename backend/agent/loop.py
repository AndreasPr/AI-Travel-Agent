"""Bounded plan/act loop, deterministic final gate and single-day repairs."""
import asyncio
import json
from decimal import Decimal
from datetime import timedelta
import re

from pydantic import ValidationError

from backend.agent.context import ContextBuilder
from backend.agent.models import ChatResponse, DayPatch, Intent, Usage
from backend.agent.policy import ALLOWLISTS, apply_patch, data_block, sensitive
from backend.agent.providers import provider_for
from backend.agent.store import PostgresTripStore
from backend.llm.config import load_config
from backend.llm.types import LLMError
from backend.tools.models import Itinerary
from backend.tools.registry import REGISTRY
from backend.tools.runtime import ToolRuntime


class Agent:
    def __init__(self, store=None, runtime=None, providers=None, config=None):
        self.store = store if store is not None else PostgresTripStore()
        self.runtime = runtime if runtime is not None else ToolRuntime()
        self.config = config or load_config()
        self.settings = self.config['agent']
        self.providers = providers or (lambda role: provider_for(role, self.config))
        self.definitions = [{'name': name, 'description': entry.description, 'parameters': entry.input_model.model_json_schema(by_alias=True)} for name, entry in sorted(REGISTRY.items())]
        self.context = ContextBuilder(self.definitions, self.settings['context'])

    async def chat(self, request):
        state = self.store.load(request.trip_id) if request.trip_id else self.store.create()
        revision = state['revision']
        output = ChatResponse(trip_id=state['id'], message='')
        usage = Usage()
        output.usage = usage
        if sensitive(request.message):
            output.message = 'Please omit health details, identification, payment information and secrets. Use general travel preferences instead.'
            return output

        async def generate(role, messages, tools=None, response_schema=None):
            provider = self.providers(role)
            from backend.llm.validation import schema_dict
            payload = [messages, tools, schema_dict(response_schema)]
            names = [entry['provider'] for entry in self.config['roles'][role]['chain']]
            if any(self.context.estimate(payload, name) > self.settings['context']['token_budget'] for name in names):
                raise ValueError('Prompt exceeds configured token budget')
            response = await asyncio.wait_for(asyncio.to_thread(provider.generate, messages, tools=tools, response_schema=response_schema,
                                                                  max_output_tokens=self.settings['max_output_tokens']), self.settings['model_timeout_seconds'])
            usage.tokens_in += response.tokens_in
            usage.tokens_out += response.tokens_out
            usage.cached_tokens += response.cached_tokens
            usage.uncached_tokens += max(0, response.tokens_in - response.cached_tokens)
            usage.calls.append(dict(provider=response.provider, model=response.model, tokens_in=response.tokens_in,
                                    tokens_out=response.tokens_out, cached_tokens=response.cached_tokens))
            return response

        async def execute(name, arguments):
            try:
                timeout = REGISTRY[name].policy.timeout_seconds
                result = await asyncio.wait_for(asyncio.to_thread(self.runtime.execute, name, arguments), timeout + 0.1)
                payload = result.model_dump(mode='json')
            except Exception:
                payload = {'tool': name, 'status': 'error', 'data': {'error': {'code': 'tool_failed', 'message': 'Tool failed or exceeded its deadline'}}}
            output.tool_trace.append(payload)
            if payload.get('tool_result_id') and payload['status'] == 'ok':
                state['evidence'].append(payload['tool_result_id'])
            return payload

        try:
            if request.message.strip().lower() == 'confirm preferences':
                if state['proposal'] is None:
                    output.message = 'There is no pending preference proposal.'
                else:
                    state['preferences'] = state['proposal']
                    state['proposal'] = None
                    output.message = 'Preferences confirmed and saved.'
            else:
                intent_response = await generate('extract', [
                    {'role': 'system', 'content': 'Classify the current message: new_trip, edit_trip, question_about_trip, chitchat. Extract an explicit budget and one-based edit day only if stated. Propose only general preferences explicitly requested; omit diagnoses, IDs and payment details. Return JSON.'},
                    {'role': 'user', 'content': data_block({'message': request.message, 'has_itinerary': state['itinerary'] is not None})},
                ], response_schema=Intent)
                intent = Intent.model_validate_json(intent_response.text)
                if intent.preference_proposal is not None:
                    state['proposal'] = intent.preference_proposal.model_dump(mode='json')
                    output.preference_proposal = intent.preference_proposal
                if intent.intent == 'chitchat':
                    output.message = 'I can help plan or edit a trip. Tell me the destination, dates and budget.'
                elif intent.intent == 'edit_trip' and (state['itinerary'] is None or intent.day is None):
                    output.message = 'Please select an existing itinerary and the day to edit.'
                else:
                    budget = intent.budget if intent.budget is not None else state['budget']
                    if budget is None:
                        budget = state['preferences'].get('budget')
                    if budget is None and intent.intent != 'question_about_trip':
                        output.message = 'Please provide a budget in the itinerary currency before I create a priced plan.'
                    else:
                        await self._plan(state, request, intent, budget, output, generate, execute)
                if output.preference_proposal is not None:
                    output.message += ' Review the proposed preferences; reply "confirm preferences" to save them.'
        except (LLMError, ValidationError, ValueError, TimeoutError):
            output.message = 'I could not complete this turn: the provider response or context was invalid or unavailable. Please retry.'
            output.itinerary = None
            output.diff = None
        if any(row['status'] == 'no_data' for row in output.tool_trace):
            names = sorted({row['tool'] for row in output.tool_trace if row['status'] == 'no_data'})
            output.message += ' I cannot find matching data from: ' + ', '.join(names) + '.'
        if any(row.get('source') == 'synthetic-v1' for row in output.tool_trace) or output.itinerary is not None:
            output.message += ' Inventory quotes are synthetic; they do not establish booking availability.'
        state['history'].extend([{'role': 'user', 'content': request.message}, {'role': 'assistant', 'content': output.message}])
        # Reject generated sensitive content too; do not persist it in versions or history.
        if sensitive(json.dumps(state, default=str)):
            output.itinerary, output.diff, output.budget_met = None, None, None
            output.message = 'The generated content contained sensitive information and was not saved.'
            return output
        self.store.save(state, revision)
        return output

    async def _plan(self, state, request, intent, budget, output, generate, execute):
        chain = self.config['roles']['plan']['chain']
        messages = await self.context.build(state, request.message, chain[0]['provider'], generate)
        messages.append({'role': 'user', 'content': data_block({'budget': budget, 'intent': intent.intent, 'edit_day': intent.day})})
        allowed = ALLOWLISTS[intent.intent]
        definitions = [tool for tool in self.definitions if tool['name'] in allowed]
        for _ in range(self.settings['step_limit']):
            response = await generate('plan', messages, tools=definitions or None)
            if not response.tool_calls:
                break
            messages.append({'role': 'assistant', 'content': '', 'tool_calls': [{'id': call.id or call.name, 'type': 'function', 'function': {'name': call.name, 'arguments': call.arguments}} for call in response.tool_calls]})
            calls = response.tool_calls
            if len(calls) > self.settings['max_parallel_calls']:
                output.message = 'The plan requested too many simultaneous tools; please narrow the request.'
                return

            async def act(call):
                if call.name not in allowed:
                    result = {'tool': call.name, 'status': 'error', 'data': {'error': {'code': 'not_allowed', 'message': 'Tool is not allowed for this intent'}}}
                    output.tool_trace.append(result)
                    return result
                return await execute(call.name, call.arguments)

            results = await asyncio.gather(*(act(call) for call in calls))
            for call, result in zip(calls, results, strict=True):
                messages.append({'role': 'tool', 'name': call.name, 'tool_name': call.name, 'tool_call_id': call.id or call.name, 'content': data_block(result)})
                if result['status'] == 'ok' and call.name == 'search_destinations':
                    state['citations'].extend(result['data']['chunks'])
        else:
            output.message = 'I reached the planning step limit before producing a validated itinerary.'
            return
        if intent.intent == 'question_about_trip':
            output.message = 'Here is the current saved itinerary and the retrieved observations in tool_trace.'
            # Returning a saved plan still requires the deterministic validation gate.
            if state['itinerary'] is not None and state['budget'] is not None:
                result = await execute('validate_itinerary', {'itinerary': state['itinerary'], 'budget': state['budget']})
                if result['status'] == 'ok' and result['data']['valid']:
                    output.itinerary = Itinerary.model_validate(state['itinerary'])
                    output.budget_met = not any(issue['name'] == 'unpriced_item' for issue in result['data']['issues'])
            return
        schema = DayPatch if intent.intent == 'edit_trip' else Itinerary
        messages.append({'role': 'user', 'content': 'Return the final JSON now. ' + ('Return only a patch for the requested day.' if intent.intent == 'edit_trip' else 'Return an Itinerary. Every cost and coordinate needs trusted tool evidence.')})
        best = None
        for attempt in range(3):
            issues = []
            candidate, diff = None, None
            try:
                response = await generate('plan', messages, response_schema=schema)
                if schema is DayPatch:
                    candidate, diff = apply_patch(state['itinerary'], DayPatch.model_validate_json(response.text), intent.day)
                else:
                    candidate = Itinerary.model_validate_json(response.text).model_dump(mode='json')
                dates = {day['date'] for day in candidate['days']}
                typed = Itinerary.model_validate(candidate)
                expected_dates = {(typed.trip.start_date + timedelta(days=i)).isoformat() for i in range((typed.trip.end_date - typed.trip.start_date).days + 1)}
                if dates != expected_dates or not any(day['items'] for day in candidate['days']):
                    issues.append(dict(name='incomplete_itinerary', severity='error', message='Include every trip day and at least one item'))
                known = set(state['evidence'])
                known_chunks = {chunk['chunk_id'] for chunk in state['citations']}
                for day in candidate['days']:
                    for item in day['items']:
                        if any(key not in known_chunks for key in item['chunk_ids']):
                            issues.append(dict(name='untrusted_citation', severity='error', message='Chunk ID was not retrieved for this conversation'))
                        # Free-text fields cannot carry unvalidated monetary/availability assertions.
                        if re.search(r'(?i)([$€£]|\b(?:USD|EUR|GBP|price|costs?|available|availability|confirmed|booked|free)\b)', item['place'] + ' ' + item['category']):
                            issues.append(dict(name='unverified_claim', severity='error', message='Keep price and availability claims out of place/category fields'))
                        if any(key not in known for key in item['tool_result_ids']) or (item['coord_tool_result_id'] and item['coord_tool_result_id'] not in known):
                            issues.append(dict(name='untrusted_tool_result', severity='error', message='Result ID does not belong to this conversation'))
                result = await execute('validate_itinerary', {'itinerary': candidate, 'budget': str(budget)})
                if result['status'] != 'ok':
                    issues.append(dict(name='validation_unavailable', severity='error', message='Could not validate itinerary'))
                else:
                    issues.extend(result['data']['issues'])
                errors = [issue for issue in issues if issue['severity'] == 'error']
                if not errors:
                    self._accept(state, candidate, budget, diff, issues, output)
                    return
                if all(issue['name'] == 'budget_exceeded' for issue in errors):
                    total = Decimal(str(result['data']['total_cost']))
                    if best is None or total < best[0]:
                        best = (total, candidate, diff, issues)
            except (ValidationError, ValueError, LLMError):
                issues = [dict(name='schema_valid', severity='error', message='Output does not match the required itinerary or day patch schema')]
            output.issues = issues
            if attempt < 2:
                messages.append({'role': 'user', 'content': 'Repair the candidate using these issues. Return complete JSON. ' + data_block({'candidate': candidate, 'issues': issues})})
        if best:
            _, candidate, diff, issues = best
            self._accept(state, candidate, budget, diff, issues, output)
            output.budget_met = False
            output.message = 'I could not meet the budget after two repairs. This is the lowest-cost otherwise-valid plan produced; it exceeds your budget.'
            if any(issue['name'] == 'unpriced_item' for issue in issues):
                output.message += ' Some items are unpriced, so the full cost is also unknown.'
        else:
            output.message = 'I could not produce a valid itinerary after two repairs. See issues; the previous itinerary was kept.'

    @staticmethod
    def _accept(state, candidate, budget, diff, issues, output):
        state['itinerary'], state['budget'] = candidate, str(budget)
        output.itinerary = Itinerary.model_validate(candidate)
        output.diff, output.issues = diff, issues
        unknown = any(issue['name'] == 'unpriced_item' for issue in issues)
        output.budget_met = None if unknown else not any(issue['name'] == 'budget_exceeded' for issue in issues)
        output.message = 'Here is the validated itinerary.' if not unknown else 'Here is the itinerary. Some items are unpriced, so the full budget cannot be verified.'
        cited = {key for day in candidate['days'] for item in day['items'] for key in item['chunk_ids']}
        output.citations = [chunk for chunk in state['citations'] if chunk['chunk_id'] in cited]
