"""Schema for synthetic draft evaluation requests."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from eval.checks import CHECKS


class Constraints(BaseModel):
    model_config = ConfigDict(extra='forbid')
    destination: str
    start_date: date | None = None
    end_date: date | None = None
    length: int | None = Field(default=None, gt=0)
    budget: float = Field(ge=0)
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    interests: list[str]
    pace: Literal['slow', 'moderate', 'fast']
    must_include: list[str]
    must_avoid: list[str]
    party_size: int = Field(gt=0)

    @model_validator(mode='after')
    def dates(self):
        if not self.length and not (self.start_date and self.end_date):
            raise ValueError('Dates or length required')
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError('Dates reversed')
        return self


class GoldenCase(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    request: str
    constraints: Constraints
    category: Literal['easy', 'hard', 'ambiguous', 'impossible-budget', 'no-data', 'multi-turn', 'adversarial']
    rubric: list[str] = Field(min_length=1)
    turns: list[str] = Field(default_factory=list)
    synthetic: Literal[True]

    @model_validator(mode='after')
    def checks(self):
        if any(name not in CHECKS for name in self.rubric):
            raise ValueError('Unknown rubric check')
        if self.category == 'multi-turn' and not self.turns:
            raise ValueError('Edit turns required')
        return self
