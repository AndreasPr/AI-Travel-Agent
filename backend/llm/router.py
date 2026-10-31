"""Role routing with bounded retries, quota admission and streaming failover."""
import json
import os

from backend.llm.config import load_config, model_config, role_chain
from backend.llm.gemini import GeminiProvider
from backend.llm.limits import PostgresDailyCounter, effective_limits, shared_bucket
from backend.llm.ollama import OllamaProvider
from backend.llm.replay import BedrockProvider, ClaudeProvider, ReplayProvider
from backend.llm.retry import retry_call
from backend.llm.types import InvalidOutput, ProviderUnavailable, QuotaExhausted, RateLimited
from backend.llm.validation import schema_dict

FALLBACK_ERRORS = (QuotaExhausted, RateLimited, ProviderUnavailable)


class ManagedProvider:
    def __init__(self, provider, spec, settings, counter=None, bucket=None, retry_options=None):
        self.inner = provider
        self.provider, self.model = provider.provider, provider.model
        self.limits = effective_limits(spec)
        self.settings = settings
        self.counter = counter if counter is not None else PostgresDailyCounter()
        self.bucket = bucket if bucket is not None else shared_bucket(self.provider, self.model, self.limits)
        self.retry_options = retry_options if retry_options is not None else settings["retry"]

    def remaining_daily(self):
        return self.counter.remaining(self.provider, self.model, self.limits["rpd"])

    def generate(self, messages, tools=None, response_schema=None, stream=False, **opts):
        opts = {"max_output_tokens": self.settings["max_output_tokens"], **opts}
        if not isinstance(opts["max_output_tokens"], int) or opts["max_output_tokens"] <= 0:
            raise InvalidOutput("max_output_tokens must be a positive integer")
        # Conservative UTF-8 byte estimate plus the output ceiling; actual usage reconciles on success.
        reserved = len(json.dumps([messages, tools, schema_dict(response_schema)], ensure_ascii=False).encode()) + opts["max_output_tokens"]

        def attempt():
            self.bucket.reserve(reserved)
            self.counter.reserve(self.provider, self.model, self.limits["rpd"])
            result = self.inner.generate(messages, tools=tools, response_schema=response_schema, stream=stream, **opts)
            if stream:
                iterator = iter(result)
                try:
                    first = next(iterator)
                except StopIteration as exc:
                    raise ProviderUnavailable("Provider returned an empty stream") from exc
                return iterator, first
            self.bucket.reconcile(reserved, result.tokens_in + result.tokens_out)
            return result

        if not stream:
            return retry_call(attempt, **self.retry_options)

        def events():
            iterator, first = retry_call(attempt, **self.retry_options)
            try:
                event = first
                while True:
                    if event.type == "done":
                        response = event.response
                        self.bucket.reconcile(reserved, response.tokens_in + response.tokens_out)
                        yield event
                        return
                    yield event
                    try:
                        event = next(iterator)
                    except StopIteration as exc:
                        raise ProviderUnavailable("Stream ended without a done event") from exc
            finally:
                close = getattr(iterator, "close", None)
                if close:
                    close()
        return events()


def build_provider(provider, model, config, counter=None):
    spec = model_config(provider, model, config)
    if provider == "claude":
        return ClaudeProvider(model)
    if provider == "bedrock":
        return BedrockProvider(model)
    if os.getenv("LLM_REPLAY") == "1":
        return ReplayProvider(provider, model)
    if provider == "gemini":
        adapter = GeminiProvider(model, spec)
    elif provider == "ollama":
        adapter = OllamaProvider(model, spec)
    else:
        raise ValueError(f"Unsupported provider: {provider}")
    return ManagedProvider(adapter, spec, config["llm"], counter=counter)


class Router:
    def __init__(self, chain, config, factory=None):
        self.chain, self.config = chain, config
        self.factory = factory or (lambda provider, model: build_provider(provider, model, config))
        self.chosen = None

    def generate(self, messages, tools=None, response_schema=None, stream=False, **opts):
        if stream:
            return self._stream(messages, tools, response_schema, opts)
        last = None
        for entry in self.chain:
            try:
                provider = self.factory(entry["provider"], entry["model"])
                response = provider.generate(messages, tools=tools, response_schema=response_schema, **opts)
                self.chosen = provider
                return response
            except FALLBACK_ERRORS as exc:
                last = exc
        raise last or ProviderUnavailable("No provider available for role")

    def _stream(self, messages, tools, response_schema, opts):
        last = None
        for entry in self.chain:
            emitted = False
            iterator = None
            try:
                provider = self.factory(entry["provider"], entry["model"])
                iterator = provider.generate(messages, tools=tools, response_schema=response_schema, stream=True, **opts)
                for event in iterator:
                    emitted = True
                    self.chosen = provider
                    yield event
                    if event.type == "done":
                        return
                raise ProviderUnavailable("Stream ended without done")
            except FALLBACK_ERRORS as exc:
                if emitted:
                    raise
                last = exc
            finally:
                close = getattr(iterator, "close", None)
                if close:
                    close()
        raise last or ProviderUnavailable("No provider available for role")


def get_provider(role, profile=None, *, config=None, factory=None):
    config = load_config() if config is None else config
    return Router(role_chain(role, profile, config), config, factory)
