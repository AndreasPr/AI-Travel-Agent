"""PR workflow contracts: no custom secrets and no silently weakened gates."""
from pathlib import Path
import os
import subprocess
import sys
import json
import pytest
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


def test_smoke_runner_and_browser_cache_use_supported_ubuntu():
    smoke = yaml.safe_load(Path('.github/workflows/ci.yml').read_text())['jobs']['smoke']
    assert smoke['runs-on'] == 'ubuntu-24.04'
    cache = next(step for step in smoke['steps'] if step.get('uses') == 'actions/cache@v4')
    assert 'ubuntu-24.04' in cache['with']['key']
    assert '${{ runner.arch }}' in cache['with']['key']


@pytest.mark.parametrize('step_name', ['Container diagnostics', 'Remove isolated test stack'])
@pytest.mark.parametrize('existing_key', [None, 'synthetic-existing-test-key'])
def test_synthetic_smoke_cleanup_handles_early_failure(tmp_path, step_name, existing_key):
    smoke = yaml.safe_load(Path('.github/workflows/ci.yml').read_text())['jobs']['smoke']
    step = next(step for step in smoke['steps'] if step.get('name') == step_name)
    assert step['if'] == ('failure()' if step_name == 'Container diagnostics' else 'always()')
    fake_docker = tmp_path / 'docker'
    fake_docker.write_text('#!' + sys.executable + '\n'
                          'import os, sys, json\n'
                          'assert os.environ.get("TEST_JWT_SECRET")\n'
                          'print(json.dumps([sys.argv[1:], os.environ["TEST_JWT_SECRET"]]))\n'
                          'sys.exit(int(os.environ.get("SYNTHETIC_DOCKER_EXIT", "0")))\n')
    fake_docker.chmod(0o755)
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ['PATH'])
    env.pop('TEST_JWT_SECRET', None)
    if existing_key:
        env['TEST_JWT_SECRET'] = existing_key
    result = subprocess.run(['bash', '-e', '-c', step['run']], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    args, key = json.loads(result.stdout)
    assert key == (existing_key or 'unused-compose-cleanup')
    assert args == ['compose', '-f', 'compose.test.yaml', '-f', 'compose.ci.yaml',
                    *(['logs', '--tail=100'] if step_name == 'Container diagnostics' else ['down'])]
    env['SYNTHETIC_DOCKER_EXIT'] = '7'
    failed = subprocess.run(['bash', '-e', '-c', step['run']], env=env, capture_output=True, text=True)
    assert failed.returncode == 7
