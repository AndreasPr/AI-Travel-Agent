"""Local Ollama chat API with validated JSON tool fallback."""
import ipaddress
import json
import os
import time
from urllib.parse import urlparse

import httpx

from backend.llm.retry import map_exception, status_error
from backend.llm.types import Event, InvalidOutput, ProviderUnavailable, Response, ToolCall, response_events
from backend.llm.validation import parse_json, schema_dict, tool_definitions, validate_response


class OllamaProvider:
    provider = "ollama"

    def __init__(self, model, spec, base_url=None, client=None):
        self.model, self.spec = model, spec
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
        parsed = urlparse(self.base_url)
        local = parsed.hostname in {"localhost", "ollama"}
        try:
            local = local or ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            pass
        if parsed.scheme not in {"http", "https"} or not local or parsed.username or parsed.password:
            raise ValueError("OLLAMA_BASE_URL must point to loopback or the local ollama service")
        self.client = client

    def _request(self, messages, tools, response_schema, stream, opts):
        opts = dict(opts)
        mode = opts.pop("tool_mode", "auto")
        if mode not in {"auto", "json"}:
            raise InvalidOutput("tool_mode must be auto or json")
        fallback = bool(tools) and (mode == "json" or not self.spec.get("supports", {}).get("tools"))
        body = {"model": self.model, "messages": [dict(message) for message in messages], "stream": stream}
        if "max_output_tokens" in opts:
            opts["num_predict"] = opts.pop("max_output_tokens")
        body["options"] = opts
        if fallback:
            envelope = {"type": "object", "properties": {
                "text": {"type": "string"},
                "tool_calls": {"type": "array", "items": {"type": "object", "properties": {
                    "name": {"type": "string", "enum": [tool["name"] for tool in tool_definitions(tools)]},
                    "arguments": {"type": "object"}}, "required": ["name", "arguments"], "additionalProperties": False}}},
                "required": ["text", "tool_calls"], "additionalProperties": False}
            body["format"] = envelope
            instruction = "Return JSON with text and tool_calls. Tools are declarations only; do not pretend they have executed. "
            instruction += json.dumps(tool_definitions(tools), sort_keys=True)
            if response_schema is not None:
                instruction += " If no tool is called, text must itself encode JSON matching: " + json.dumps(schema_dict(response_schema))
            body["messages"].insert(0, {"role": "system", "content": instruction})
        else:
            envelope = None
            if tools:
                body["tools"] = [{"type": "function", "function": tool} for tool in tool_definitions(tools)]
            if response_schema is not None:
                body["format"] = schema_dict(response_schema)
                body["messages"].insert(0, {"role": "system", "content": "Return JSON matching this schema: " + json.dumps(schema_dict(response_schema))})
        return body, envelope

    def _normalize(self, raw, started):
        message = raw.get("message", {})
        calls = []
        for call in message.get("tool_calls", []):
            function = call.get("function", call)
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                arguments = parse_json(arguments, {"type": "object"})
            calls.append(ToolCall(name=function["name"], arguments=arguments, id=call.get("id")))
        return Response(text=message.get("content", ""), tool_calls=calls,
                        provider=self.provider, model=self.model, finish_reason=raw.get("done_reason"),
                        tokens_in=raw.get("prompt_eval_count", 0), tokens_out=raw.get("eval_count", 0),
                        cached_tokens=raw.get("prompt_eval_cached_count", 0), latency_ms=(time.monotonic() - started) * 1000)

    def _finish(self, result, envelope, tools, schema):
        if envelope:
            data = parse_json(result.text, envelope)
            result.text = data["text"]
            result.tool_calls = [ToolCall(**call) for call in data["tool_calls"]]
        return validate_response(result, tools, schema)

    def generate(self, messages, tools=None, response_schema=None, stream=False, **opts):
        body, envelope = self._request(messages, tools, response_schema, stream, opts)
        if stream:
            return self._stream(body, envelope, tools, response_schema)
        started = time.monotonic()
        client = self.client or httpx.Client(timeout=120)
        try:
            raw_response = client.post(self.base_url + "/api/chat", json=body)
            if raw_response.status_code >= 400:
                raise status_error(raw_response.status_code, raw_response.headers)
            raw = raw_response.json()
        except Exception as exc:
            raise map_exception(exc) from exc
        finally:
            if self.client is None:
                client.close()
        if not raw.get("done"):
            raise InvalidOutput("Ollama returned an incomplete response")
        return self._finish(self._normalize(raw, started), envelope, tools, response_schema)

    def _stream(self, body, envelope, tools, schema):
        started = time.monotonic()
        aggregate = Response(provider=self.provider, model=self.model)
        client = self.client or httpx.Client(timeout=120)
        completed = False
        try:
            with client.stream("POST", self.base_url + "/api/chat", json=body) as response:
                if response.status_code >= 400:
                    raise status_error(response.status_code, response.headers)
                for line in response.iter_lines():
                    if not line:
                        continue
                    raw = json.loads(line)
                    if "error" in raw:
                        raise ProviderUnavailable("Ollama stream reported an error")
                    chunk = self._normalize(raw, started)
                    aggregate.text += chunk.text
                    aggregate.tool_calls.extend(chunk.tool_calls)
                    if not envelope:
                        if chunk.text:
                            yield Event(type="text_delta", text=chunk.text)
                    if raw.get("done"):
                        completed = True
                        aggregate.tokens_in, aggregate.tokens_out, aggregate.cached_tokens = chunk.tokens_in, chunk.tokens_out, chunk.cached_tokens
                        aggregate.finish_reason = chunk.finish_reason
                        break
        except Exception as exc:
            raise map_exception(exc) from exc
        finally:
            if self.client is None:
                client.close()
        if not completed:
            raise ProviderUnavailable("Ollama stream ended before done")
        aggregate.latency_ms = (time.monotonic() - started) * 1000
        aggregate = self._finish(aggregate, envelope, tools, schema)
        if envelope:
            yield from response_events(aggregate)
        else:
            for call in aggregate.tool_calls:
                yield Event(type="tool_call", tool_call=call)
            yield Event(type="usage", tokens_in=aggregate.tokens_in, tokens_out=aggregate.tokens_out, cached_tokens=aggregate.cached_tokens)
            yield Event(type="done", response=aggregate)
