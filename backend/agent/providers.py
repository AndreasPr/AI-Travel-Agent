"""Config-routed structured output with a validated JSON fallback."""
import json
from copy import deepcopy

from backend.agent.models import DayPatch
from backend.tools.models import Itinerary

from backend.llm.config import load_config, model_config, role_chain
from backend.llm.router import Router, build_provider
from backend.llm.validation import schema_dict, validate_response


def generation_schema(schema):
    """Constrain generated local wall-clock times to the itinerary validator's contract."""
    if schema not in (Itinerary, DayPatch):
        return schema
    result = deepcopy(schema_dict(schema))
    properties = result['$defs']['Item']['properties']
    for name in ('start', 'end'):
        properties[name].pop('format', None)
        properties[name]['pattern'] = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?$'
        properties[name]['description'] = 'Local wall-clock datetime, without Z or UTC offset; end must follow start.'
    return result


class StructuredProvider:
    def __init__(self, inner, spec):
        self.inner, self.spec = inner, spec
        self.provider, self.model = inner.provider, inner.model

    def generate(self, messages, tools=None, response_schema=None, **opts):
        native = self.spec.get('supports', {}).get('structured_output', False)
        requested_schema = generation_schema(response_schema)
        if response_schema is not None and not native:
            if self.provider == 'ollama':
                opts['json_mode'] = True
            messages = messages + [{'role': 'user', 'content': 'Return only JSON matching this schema: ' + json.dumps(schema_dict(requested_schema), sort_keys=True)}]
        result = self.inner.generate(messages, tools=tools, response_schema=requested_schema if native else None, **opts)
        return validate_response(result, tools, response_schema)


def provider_for(role, config=None, provider=None, replay=False):
    config = config or load_config()
    chain = role_chain(role, None, config)
    if provider:
        chain = [entry for entry in chain if entry['provider'] == provider]
        if not chain:
            raise ValueError('Provider is not configured for this role')

    def factory(name, model):
        if replay:
            from backend.llm.replay import ReplayProvider
            inner = ReplayProvider(name, model)
        else:
            inner = build_provider(name, model, config)
        return StructuredProvider(inner, model_config(name, model, config))

    return Router(chain, config, factory)
