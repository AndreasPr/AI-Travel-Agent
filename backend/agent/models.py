"""Conversation, patch and response contracts."""
from typing import Literal
from decimal import Decimal

from pydantic import Field

from backend.tools.models import Contract, Item, Itinerary


class Preferences(Contract):
    budget: Decimal | None = Field(default=None, ge=0)
    pace: Literal['relaxed', 'moderate', 'busy'] | None = None
    interests: list[Literal['museums', 'food', 'nature', 'history', 'art', 'shopping', 'beaches', 'nightlife']] = Field(default_factory=list)
    dietary_needs: list[Literal['vegetarian', 'vegan', 'halal', 'kosher', 'gluten-free']] = Field(default_factory=list)
    mobility: Literal['standard', 'step-free', 'short-walks'] | None = None


class Intent(Contract):
    intent: Literal['new_trip', 'edit_trip', 'question_about_trip', 'chitchat']
    budget: Decimal | None = Field(default=None, ge=0)
    day: int | None = Field(default=None, ge=1)
    preference_proposal: Preferences | None = None


class PatchOperation(Contract):
    op: Literal['replace_item', 'remove_item', 'add_item']
    item_id: str | None = None
    item: Item | None = None


class DayPatch(Contract):
    day: int = Field(ge=1)
    operations: list[PatchOperation] = Field(max_length=30)


class ChatRequest(Contract):
    trip_id: str | None = Field(default=None, pattern=r'^[a-f0-9-]{36}$')
    message: str = Field(min_length=1, max_length=12000)


class Usage(Contract):
    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens: int = 0
    uncached_tokens: int = 0
    calls: list[dict] = Field(default_factory=list)


class ChatResponse(Contract):
    trip_id: str
    message: str
    itinerary: Itinerary | None = None
    diff: dict | None = None
    citations: list[dict] = Field(default_factory=list)
    tool_trace: list[dict] = Field(default_factory=list)
    budget_met: bool | None = None
    usage: Usage = Field(default_factory=Usage)
    issues: list[dict] = Field(default_factory=list)
    preference_proposal: Preferences | None = None
