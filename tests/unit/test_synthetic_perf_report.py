"""Synthetic k6 summaries test reporting, not measured performance."""
import json
import pytest
from perf.run import finalize_report


@pytest.mark.parametrize('code,count,samples,rate,expected', [
    (108, 0, 0, 0, 108), (0, 0, 0, 0, 1), (0, 2, 2, 0, 0),
    (0, 2, 3, 0.33, 1), (108, 2, 2, 0, 108),
])
def test_synthetic_perf_report_requires_successful_sessions(tmp_path, code, count, samples, rate, expected):
    output = tmp_path / 'synthetic.json'
    output.write_text(json.dumps({'provenance': 'synthetic: tests the harness, not a model', 'metrics': {
        'sse_completed_sessions': {'values': {'count': count}},
        'sse_error_rate': {'values': {'rate': rate, 'passes': 0, 'fails': samples}},
    }}))
    assert finalize_report(output, code) == expected
    report = json.loads(output.read_text())
    assert report['status'] == ('passed' if expected == 0 else 'failed')
    assert report['completed_sessions'] == count
    assert report['k6_exit_code'] == code


def test_synthetic_perf_missing_report_fails(tmp_path):
    assert finalize_report(tmp_path / 'missing-synthetic.json', 0) == 1
