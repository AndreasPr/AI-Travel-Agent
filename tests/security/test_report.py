"""Safe failure reporting does not hide which invariant failed."""
from types import SimpleNamespace
from backend.agent.models import ChatResponse
from scenarios import ScenarioFailure
import report


def test_security_report_shows_failed_check_without_raw_content(capsys, monkeypatch):
    result = ChatResponse(trip_id='synthetic-trip', message='synthetic secret never print',
                          issues=[{'name': 'schema_valid', 'reason': 'schema_validation', 'message': 'synthetic secret never print'}],
                          tool_trace=[{'tool': 'search_hotels', 'status': 'error', 'data': {'error': {'code': 'untrusted_arguments', 'message': 'synthetic secret never print'}}}])
    runtime = SimpleNamespace(calls=[{'tool': 'search_destinations', 'arguments': {'secret': 'never print'}}])
    failure = ScenarioFailure('No validated final itinerary', result, runtime)
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(report, 'run_case', fail)
    monkeypatch.setattr('sys.argv', ['report.py', '--case', 'discount'])
    assert report.main() is True
    output = capsys.readouterr().out
    assert 'No validated final itinerary' in output
    assert 'schema_valid/schema_validation' in output
    assert 'untrusted_arguments' in output
    assert 'never print' not in output and 'secret' not in output


def test_live_price_check_accepts_equivalent_decimal_representation():
    from scenarios import fixture, check_result
    from backend.tools.models import Itinerary
    data = fixture()
    data['itinerary']['days'][0]['items'][0]['cost'] = '100.000'
    result = ChatResponse(trip_id='synthetic-trip', message='Synthetic plan', itinerary=Itinerary.model_validate(data['itinerary']))
    runtime = SimpleNamespace(calls=[{'tool': 'validate_itinerary', 'arguments': {}}])
    agent = SimpleNamespace(store=SimpleNamespace(load=lambda key: {'budget': '1500'}))
    check_result({}, result, runtime, agent, strict=False)


def test_activity_schema_requires_retrieved_citations_without_city_extraction():
    from copy import deepcopy
    from jsonschema import Draft202012Validator, ValidationError
    import pytest
    from scenarios import fixture, cases
    from backend.agent.requirements import bind_itinerary_schema
    from backend.tools.models import Itinerary
    data = fixture()
    result = {'tool': 'search_hotels', 'status': 'ok', 'tool_result_id': 'synthetic-search_hotels', 'data': data['hotel_result']}
    schema = bind_itinerary_schema(Itinerary, cases()[0]['user_request'], [result], [data['citation']])
    validator = Draft202012Validator(schema)
    validator.validate(data['itinerary'])
    for citations in ([], ['synthetic-unknown']):
        bad = deepcopy(data['itinerary'])
        bad['days'][0]['items'][1]['chunk_ids'] = citations
        with pytest.raises(ValidationError):
            validator.validate(bad)
