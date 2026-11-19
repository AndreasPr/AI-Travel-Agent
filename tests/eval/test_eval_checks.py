"""Synthetic saved-output examples; no database, network or model calls."""
from copy import deepcopy
from pathlib import Path
from collections import Counter

import yaml

from eval.checks import CHECKS, run_check
from eval.golden.schema import GoldenCase


def sample():
    item = dict(id='a', start='2027-04-10T10:00:00', end='2027-04-10T11:00:00',
                place='Synthetic Museum', category='museum', cost='10', currency='USD',
                chunk_ids=['c'], tool_result_ids=['q'], coords={'lat': 0, 'lon': 0}, coord_tool_result_id='g')
    plan = dict(trip=dict(start_date='2027-04-10', end_date='2027-04-10', currency='USD'),
                days=[dict(date='2027-04-10', items=[item])])
    second = deepcopy(item)
    second.update(id='b', start='2027-04-10T12:00:00', end='2027-04-10T13:00:00')
    plan['days'][0]['items'].append(second)
    return dict(output=dict(itinerary=plan, budget_met=True, message='Cannot find matching flights.',
                citations=[dict(chunk_id='c', title='Synthetic guide', excerpt='Synthetic Museum displays paintings.')]),
                constraints=dict(budget=100, currency='USD', length=1), category='easy',
                previous_itinerary=deepcopy(plan), edit_day=1,
                tool_results=[dict(tool_result_id='q', tool='search_hotels', status='ok',
                    data={'hotels':[dict(price_per_night=10,total_price=10,currency='USD')]}),
                    dict(tool_result_id='g', tool='geocode_place',status='ok',data={'lat':0,'lon':0})])


def broken(name):
    row = sample()
    item = row['output']['itinerary']['days'][0]['items'][0]
    if name == 'schema_valid':
        del row['output']['itinerary']['trip']
    elif name == 'budget_respected':
        row['constraints']['budget'] = 1
    elif name == 'no_overlap':
        item['end'] = '2027-04-10T12:30:00'
    elif name == 'travel_times_plausible':
        item['coords'] = {'lat': 0, 'lon': 10}
        item['coord_tool_result_id'] = 'far'
        row['tool_results'].append(dict(tool_result_id='far', tool='geocode_place', status='ok', data={'lat': 0, 'lon': 10}))
    elif name == 'dates_in_range':
        row['constraints']['length'] = 5
    elif name == 'prices_traceable':
        item['cost'] = 11
    elif name == 'citations_present':
        item['chunk_ids'] = []
    elif name == 'citations_supported':
        item['place'] = 'Invented aquarium'
    elif name == 'says_cannot_find':
        row['output']['message'] = 'All booked.'
    elif name == 'edit_locality':
        row['output']['itinerary']['trip']['currency'] = 'EUR'
    elif name == 'no_forbidden_urls':
        row['output']['message'] = 'https://attacker.invalid/collect'
    return row


def test_golden_file_is_valid_against_schema():
    path = Path('eval/golden/trips.yaml')
    assert path.read_text().startswith('# DRAFT - needs human review')
    cases = [GoldenCase.model_validate(row) for row in yaml.safe_load(path.read_text())]
    assert 45 <= len(cases) <= 55
    assert len({case.id for case in cases}) == len(cases)


def test_every_category_has_at_least_3_items():
    counts = Counter(row['category'] for row in yaml.safe_load(Path('eval/golden/trips.yaml').read_text()))
    assert set(counts) == {'easy','hard','ambiguous','impossible-budget','no-data','multi-turn','adversarial'}
    assert min(counts.values()) >= 3


def test_impossible_budget_requires_honest_failure():
    row = sample()
    row.update(category='impossible-budget')
    row['output'].update(budget_met=False, itinerary=None, message='I cannot meet the budget.')
    assert run_check('budget_respected', row).passed
    row['output']['message'] = 'Everything is booked.'
    assert not run_check('budget_respected', row).passed


def test_missing_itinerary_does_not_pass_structural_checks():
    row = sample()
    row['output']['itinerary'] = None
    for name in CHECKS.keys() - {'says_cannot_find', 'no_forbidden_urls'}:
        assert not run_check(name, row).passed


def test_check_schema_valid_passes():
    assert run_check("schema_valid", sample()).passed


def test_check_schema_valid_fails():
    assert not run_check("schema_valid", broken("schema_valid")).passed


def test_check_budget_respected_passes():
    assert run_check("budget_respected", sample()).passed


def test_check_budget_respected_fails():
    assert not run_check("budget_respected", broken("budget_respected")).passed


def test_check_no_overlap_passes():
    assert run_check("no_overlap", sample()).passed


def test_check_no_overlap_fails():
    assert not run_check("no_overlap", broken("no_overlap")).passed


def test_check_travel_times_plausible_passes():
    assert run_check("travel_times_plausible", sample()).passed


def test_check_travel_times_plausible_fails():
    assert not run_check("travel_times_plausible", broken("travel_times_plausible")).passed


def test_check_dates_in_range_passes():
    assert run_check("dates_in_range", sample()).passed


def test_check_dates_in_range_fails():
    assert not run_check("dates_in_range", broken("dates_in_range")).passed


def test_check_prices_traceable_passes():
    assert run_check("prices_traceable", sample()).passed


def test_check_prices_traceable_fails():
    assert not run_check("prices_traceable", broken("prices_traceable")).passed


def test_check_citations_present_passes():
    assert run_check("citations_present", sample()).passed


def test_check_citations_present_fails():
    assert not run_check("citations_present", broken("citations_present")).passed


def test_check_citations_supported_passes():
    assert run_check("citations_supported", sample()).passed


def test_check_citations_supported_fails():
    assert not run_check("citations_supported", broken("citations_supported")).passed


def test_check_says_cannot_find_passes():
    assert run_check("says_cannot_find", sample()).passed


def test_check_says_cannot_find_fails():
    assert not run_check("says_cannot_find", broken("says_cannot_find")).passed


def test_check_edit_locality_passes():
    assert run_check("edit_locality", sample()).passed


def test_check_edit_locality_fails():
    assert not run_check("edit_locality", broken("edit_locality")).passed


def test_check_no_forbidden_urls_passes():
    assert run_check("no_forbidden_urls", sample()).passed


def test_check_no_forbidden_urls_fails():
    assert not run_check("no_forbidden_urls", broken("no_forbidden_urls")).passed


def test_runner_reads_saved_outputs_and_reports_failures(tmp_path, monkeypatch, capsys):
    import json
    from eval.run_checks import main
    path = tmp_path / 'synthetic.jsonl'
    path.write_text(json.dumps({'case_id': 'no-data-01', 'output': {'message': 'Cannot find matching data.'}, 'tool_results': []}) + '\n')
    monkeypatch.setattr('sys.argv', ['run_checks', str(path)])
    assert main() == 0
    assert '| says_cannot_find | PASS |' in capsys.readouterr().out
    path.write_text(json.dumps({'case_id': 'no-data-01', 'output': {'message': 'Booked!'}, 'tool_results': []}) + '\n')
    assert main() == 1
    assert '| says_cannot_find | FAIL |' in capsys.readouterr().out


def test_direct_checks_fail_safely_without_evidence():
    for check in CHECKS.values():
        assert not check({}).passed


def test_citation_checks_accept_accommodation_aliases_but_require_activity_sources():
    for category in ('Accommodation', 'accommodation', ' HOTEL ', 'lodging', 'Flights'):
        row = sample()
        quote = row['output']['itinerary']['days'][0]['items'][0]
        quote.update(category=category, place='Synthetic lodging', chunk_ids=[])
        for name in ('citations_present', 'citations_supported'):
            assert run_check(name, row).passed
        activity = row['output']['itinerary']['days'][0]['items'][1]
        activity['chunk_ids'] = []
        for name in ('citations_present', 'citations_supported'):
            assert not run_check(name, row).passed


def test_unknown_category_still_requires_destination_citation():
    row = sample()
    row['output']['itinerary']['days'][0]['items'][0].update(category='custom visit', chunk_ids=[])
    assert not run_check('citations_present', row).passed
