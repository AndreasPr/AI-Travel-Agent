"""Provider-independent request results, stream events and failures."""
from __future__ import annotations

from typing import Any, Iterator, Literal, Protocol

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    id: str | None = None


class Response(BaseModel):
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens: int = 0
    latency_ms: float = 0
    provider: str
    model: str
    finish_reason: str | None = None
    raw_id: str | None = None


class Event(BaseModel):
    type: Literal["text_delta", "tool_call", "usage", "done"]
    text: str | None = None
    tool_call: ToolCall | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cached_tokens: int | None = None
    response: Response | None = None


class LLMError(Exception):
    def __init__(self, message: str, *, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class QuotaExhausted(LLMError):
    pass


class RateLimited(LLMError):
    pass


class ProviderUnavailable(LLMError):
    pass


class InvalidOutput(LLMError):
    pass


class LLMProvider(Protocol):
    provider: str
    model: str

    def generate(self, messages: list[dict], tools=None, response_schema=None, stream=False, **opts) -> Response | Iterator[Event]: ...


def response_events(response: Response) -> Iterator[Event]:
    if response.text:
        yield Event(type="text_delta", text=response.text)
    for call in response.tool_calls:
        yield Event(type="tool_call", tool_call=call)
    yield Event(type="usage", tokens_in=response.tokens_in, tokens_out=response.tokens_out, cached_tokens=response.cached_tokens)
    yield Event(type="done", response=response)
