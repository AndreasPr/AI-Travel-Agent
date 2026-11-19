"""PR workflow contracts: no custom secrets and no silently weakened gates."""
from pathlib import Path
import yaml


def test_ci_pr_jobs_do_not_require_secrets():
    text = Path('.github/workflows/ci.yml').read_text()
    assert 'secrets.' not in text
    assert 'pull_request_target' not in text
    assert 'continue-on-error' not in text
    config = yaml.safe_load(text)
    assert config['permissions'] == {'contents': 'read'}
    assert {'lint', 'type-check', 'unit', 'integration', 'frontend', 'docker', 'trivy',
            'pip-audit', 'npm-audit', 'gitleaks', 'eval', 'smoke'} <= set(config['jobs'])
    assert config['jobs']['eval']['uses'] == './.github/workflows/eval-gate.yml'
    assert 'secrets' not in config['jobs']['eval']


def test_ci_smoke_reuses_images_and_limits_synthetic_load():
    config = yaml.safe_load(Path('.github/workflows/ci.yml').read_text())
    smoke = config['jobs']['smoke']
    scripts = '\n'.join(step.get('run', '') for step in smoke['steps'])
    assert smoke['needs'] == 'docker'
    assert 'up --no-build' in scripts
    assert 'PERF_SESSIONS=2 PERF_HOLD=10s make perf' in scripts
    assert 'make test-e2e' in scripts
    assert any(step.get('if') == 'always()' and ' down' in step.get('run', '') for step in smoke['steps'])
