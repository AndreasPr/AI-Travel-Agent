"""Behavioral assertions against synthetic replay attacks, not a model benchmark."""
import pytest
from scenarios import cases, run_case


@pytest.mark.parametrize('case', cases(), ids=lambda case: case['id'])
def test_injection_suite_all_cases_safe_offline(case):
    run_case(case)
