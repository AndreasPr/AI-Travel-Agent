"""Synthetic schema failures; no provider calls or private data."""
import logging

from backend.agent.errors import failure_issue, safe_schema_details
from backend.llm.validation import parse_json
from backend.llm.types import InvalidOutput


def test_synthetic_schema_failure_identifies_missing_field_without_payload(caplog):
    try:
        parse_json('{"place":"synthetic-secret"}', {'type': 'object', 'required': ['cost']})
    except InvalidOutput as exc:
        with caplog.at_level(logging.WARNING):
            failure_issue(exc, 'itinerary')
            details = safe_schema_details(exc)
    assert details[0]['rule'] == 'required'
    assert details[0]['required_fields'] == ['cost']
    assert 'stage=itinerary' in caplog.text
    assert 'synthetic-secret' not in caplog.text


def test_synthetic_schema_failure_hides_unknown_property_names(caplog):
    try:
        parse_json('{"synthetic-secret":123}', {'properties': {'synthetic-secret': {'type': 'string'}}})
    except InvalidOutput as exc:
        with caplog.at_level(logging.WARNING):
            failure_issue(exc, 'plan')
            details = safe_schema_details(exc)
    assert details[0]['path'] == ['[field]']
    assert 'synthetic-secret' not in caplog.text
