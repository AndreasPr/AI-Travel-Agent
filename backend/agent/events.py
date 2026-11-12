"""Typed public stream events. Tool arguments are summarized by schema field names only."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter

from backend.agent.models import Preferences, Usage
from backend.tools.models import Chunk, Contract, Itinerary


class BaseEvent(Contract):
    request_id: UUID


class MessageStart(BaseEvent):
    type: Literal['message_start'] = 'message_start'
    trip_id: str | None = None


class Token(BaseEvent):
    type: Literal['token'] = 'token'
    text: str


class ArgumentSummary(Contract):
    fields: list[str]
    omitted_fields: int = Field(ge=0)


class ToolStart(BaseEvent):
    type: Literal['tool_start'] = 'tool_start'
    call_id: UUID
    tool: str
    argument_summary: ArgumentSummary


class ToolEnd(BaseEvent):
    type: Literal['tool_end'] = 'tool_end'
    call_id: UUID
    tool: str
    status: Literal['ok', 'no_data', 'error']
    duration_ms: float = Field(ge=0)


class ItineraryUpdate(BaseEvent):
    type: Literal['itinerary_update'] = 'itinerary_update'
    itinerary: Itinerary
    diff: dict | None = None


class Citations(BaseEvent):
    type: Literal['citations'] = 'citations'
    citations: list[Chunk]


ErrorCode = Literal['tool_unavailable', 'sensitive_content', 'usage_limit', 'timeout', 'not_found', 'conflict', 'provider_unavailable', 'rate_limited',
                    'quota_exhausted', 'invalid_output', 'step_limit', 'internal_error']


class ErrorEvent(BaseEvent):
    type: Literal['error'] = 'error'
    code: ErrorCode
    message: str
    usage: Usage


class Done(BaseEvent):
    type: Literal['done'] = 'done'
    trip_id: str
    usage: Usage
    message: str
    budget_met: bool | None
    preference_proposal: Preferences | None = None


StreamEvent = Annotated[MessageStart | Token | ToolStart | ToolEnd | ItineraryUpdate | Citations | ErrorEvent | Done,
                        Field(discriminator='type')]
EVENT_ADAPTER = TypeAdapter(StreamEvent)


def argument_summary(tool, arguments):
    from backend.tools.registry import REGISTRY
    definition = REGISTRY.get(tool)
    permitted = set(definition.input_model.model_json_schema(by_alias=True)['properties']) if definition else set()
    fields = sorted(permitted.intersection(arguments))
    return ArgumentSummary(fields=fields, omitted_fields=len(arguments) - len(fields))
