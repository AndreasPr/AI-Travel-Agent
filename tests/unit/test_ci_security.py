"""Synthetic advisory reports exercise strict CI policy, not vulnerability measurements."""
from datetime import date
import pytest
from scripts.ci_security import evaluate


def synthetic_report():
    return {'Results': [{'Vulnerabilities': [{'PkgName': 'synthetic-package', 'InstalledVersion': '1.0',
        'VulnerabilityID': 'SYNTHETIC-1', 'Severity': 'HIGH', 'Title': 'Synthetic advisory'}]}]}


def synthetic_exception():
    return dict(package='synthetic-package', version='1.0', advisory='SYNTHETIC-1', severity='HIGH',
                reachability='synthetic scenario', reason='synthetic test only', review_date='2027-01-01', scanners=['trivy'])


def test_synthetic_security_gate_blocks_unapproved_high():
    blocked, accepted = evaluate('trivy', synthetic_report(), [], date(2026, 11, 19))
    assert len(blocked) == 1 and not accepted


def test_synthetic_security_exception_is_package_and_version_scoped():
    entry = synthetic_exception()
    assert not evaluate('trivy', synthetic_report(), [entry], date(2026, 11, 19))[0]
    entry['package'] = 'different-package'
    assert evaluate('trivy', synthetic_report(), [entry], date(2026, 11, 19))[0]
    entry['package'] = 'synthetic-package'
    entry['version'] = '2.0'
    assert evaluate('trivy', synthetic_report(), [entry], date(2026, 11, 19))[0]


def test_synthetic_expired_exception_fails():
    with pytest.raises(ValueError, match='Expired'):
        evaluate('trivy', synthetic_report(), [synthetic_exception()], date(2027, 1, 1))


def test_synthetic_malformed_report_fails():
    with pytest.raises(ValueError):
        evaluate('trivy', {}, [], date(2026, 11, 19))
