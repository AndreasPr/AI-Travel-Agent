"""Config-routed structured output with a validated JSON fallback."""
import json

from backend.llm.config import load_config, model_config, role_chain
from backend.llm.router import Router, build_provider
from backend.llm.validation import schema_dict, validate_response


class StructuredProvider:
    def __init__(self, inner, spec):
        self.inner, self.spec = inner, spec
        self.provider, self.model = inner.provider, inner.model

    def generate(self, messages, tools=None, response_schema=None, **opts):
        native = self.spec.get('supports', {}).get('structured_output', False)
        if response_schema is not None and not native:
            messages = messages + [{'role': 'user', 'content': 'Return only JSON matching this schema: ' + json.dumps(schema_dict(response_schema), sort_keys=True)}]
        result = self.inner.generate(messages, tools=tools, response_schema=response_schema if native else None, **opts)
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
