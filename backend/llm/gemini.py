"""Google Gen AI SDK adapter; automatic tool execution is disabled."""
import json
import os
import time

from backend.llm.retry import map_exception
from backend.llm.types import Event, InvalidOutput, ProviderUnavailable, Response, ToolCall
from backend.llm.validation import schema_dict, tool_definitions, validate_response


def field(value, name, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


class GeminiProvider:
    provider = "gemini"

    def __init__(self, model, spec, client=None):
        self.model, self.spec, self.client = model, spec, client

    def _client(self):
        if self.client is None:
            key = os.getenv("GEMINI_API_KEY")
            if not key:
                raise ProviderUnavailable("M3: export GEMINI_API_KEY for the free-tier project")
            try:
                from google import genai
            except ImportError as exc:
                raise ProviderUnavailable("Install the google-genai dependency before live Gemini use") from exc
            # Disable SDK retries so every outbound attempt passes through our quota guard.
            self.client = genai.Client(api_key=key, http_options={"retry_options": {"attempts": 1}})
        return self.client

    def _request(self, messages, tools, response_schema, opts):
        config = {**opts, "automatic_function_calling": {"disable": True}}
        supported = self.spec.get("supports", {})
        if tools:
            if not supported.get("tools"):
                raise InvalidOutput("Configured model does not support native tools")
            config["tools"] = [{"function_declarations": [
                {"name": tool["name"], "description": tool.get("description", ""),
                 "parameters_json_schema": tool.get("parameters", {"type": "object"})}
                for tool in tool_definitions(tools)]}]
        if response_schema is not None:
            if not supported.get("structured_output"):
                raise InvalidOutput("Configured model does not support structured output")
            config.update(response_mime_type="application/json", response_json_schema=schema_dict(response_schema))
        contents, instructions = [], []
        for message in messages:
            role = message["role"]
            if role == "system":
                instructions.append(message.get("content", ""))
                continue
            if role == "tool":
                result = message.get("content", {})
                if isinstance(result, str):
                    try:
                        result = json.loads(result)
                    except ValueError:
                        result = {"result": result}
                if not isinstance(result, dict):
                    result = {"result": result}
                parts = [{"function_response": {"name": message["name"], "response": result}}]
            else:
                parts = [{"text": message["content"]}] if message.get("content") else []
                for call in message.get("tool_calls", []):
                    call = call.get("function", call)
                    args = call.get("arguments", {})
                    parts.append({"function_call": {"name": call["name"], "args": json.loads(args) if isinstance(args, str) else args}})
            contents.append({"role": "model" if role == "assistant" else "user", "parts": parts})
        if instructions:
            config["system_instruction"] = "\n".join(instructions)
        return {"model": self.model, "contents": contents, "config": config}

    def _normalize(self, raw, started):
        text, calls = [], []
        candidates = field(raw, "candidates", []) or []
        candidate = candidates[0] if candidates else None
        for part in field(field(candidate, "content"), "parts", []) or []:
            if field(part, "text") and not field(part, "thought", False):
                text.append(field(part, "text"))
            call = field(part, "function_call")
            if call:
                calls.append(ToolCall(name=field(call, "name"), arguments=field(call, "args", {}) or {}, id=field(call, "id")))
        usage = field(raw, "usage_metadata")
        reason = field(candidate, "finish_reason")
        return Response(text="".join(text), tool_calls=calls, provider=self.provider, model=self.model,
                        tokens_in=field(usage, "prompt_token_count", 0) or 0,
                        tokens_out=(field(usage, "candidates_token_count", 0) or 0) + (field(usage, "thoughts_token_count", 0) or 0),
                        cached_tokens=field(usage, "cached_content_token_count", 0) or 0,
                        latency_ms=(time.monotonic() - started) * 1000, raw_id=field(raw, "response_id"),
                        finish_reason=field(reason, "value", reason))

    def generate(self, messages, tools=None, response_schema=None, stream=False, **opts):
        request = self._request(messages, tools, response_schema, opts)
        if stream:
            return self._stream(request, tools, response_schema)
        started = time.monotonic()
        try:
            raw = self._client().models.generate_content(**request)
        except Exception as exc:
            raise map_exception(exc) from exc
        return validate_response(self._normalize(raw, started), tools, response_schema)

    def _stream(self, request, tools, response_schema):
        started = time.monotonic()
        aggregate = Response(provider=self.provider, model=self.model)
        try:
            for raw in self._client().models.generate_content_stream(**request):
                chunk = self._normalize(raw, started)
                aggregate.text += chunk.text
                aggregate.tool_calls.extend(chunk.tool_calls)
                if chunk.text:
                    yield Event(type="text_delta", text=chunk.text)
                if field(raw, "usage_metadata") is not None:
                    aggregate.tokens_in, aggregate.tokens_out, aggregate.cached_tokens = chunk.tokens_in, chunk.tokens_out, chunk.cached_tokens
                    yield Event(type="usage", tokens_in=chunk.tokens_in, tokens_out=chunk.tokens_out, cached_tokens=chunk.cached_tokens)
                aggregate.raw_id = chunk.raw_id or aggregate.raw_id
                aggregate.finish_reason = chunk.finish_reason or aggregate.finish_reason
        except Exception as exc:
            raise map_exception(exc) from exc
        if aggregate.finish_reason is None:
            raise ProviderUnavailable("Gemini stream ended without a finish reason")
        aggregate.latency_ms = (time.monotonic() - started) * 1000
        aggregate = validate_response(aggregate, tools, response_schema)
        for call in aggregate.tool_calls:
            yield Event(type="tool_call", tool_call=call)
        yield Event(type="done", response=aggregate)
