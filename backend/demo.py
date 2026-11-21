"""Explicit resource-constrained public demo configuration."""
from backend.env import config


def enabled():
    return config('PUBLIC_DEMO', default=False, cast=bool)
