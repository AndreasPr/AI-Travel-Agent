"""Offline gate configuration and fail-closed replay behavior."""
import configparser
import json
from pathlib import Path
import pytest
from backend.llm.replay import ReplayProvider
from backend.llm.types import InvalidOutput


def test_coverage_threshold_configured():
    config = configparser.ConfigParser()
    config.read('.coveragerc')
    assert config.getfloat('report', 'fail_under') >= 70
    assert config.get('run', 'source') == 'backend'
    assert 'make test-ci' in Path('.github/workflows/test-suite.yml').read_text()


def test_missing_fixture_fails_instead_of_network(tmp_path, monkeypatch):
    def denied(*a, **k):
        pytest.fail('Replay attempted network access')
    monkeypatch.setattr('socket.socket.connect', denied)
    replay = ReplayProvider('missing-recording', 'missing-recording', fixtures_dir=tmp_path)
    with pytest.raises(InvalidOutput, match='replay never calls the network'):
        replay.generate([{'role': 'user', 'content': 'unrecorded request'}])


def test_committed_recordings_replay_offline(monkeypatch):
    from backend.llm.record_fixtures import PROMPTS
    from backend.llm.replay import fixture_key
    root = Path('tests/fixtures/llm')
    rows = [(p, json.loads(p.read_text())) for p in root.glob('*.json')]
    recordings = [(p, row) for p, row in rows if row.get('provenance') == 'recorded']
    if not recordings:
        pytest.skip('no recording; run make eval-record')
    def denied(*a, **k):
        pytest.fail('Replay attempted network access')
    monkeypatch.setattr('socket.socket.connect', denied)
    replayed = 0
    for path, row in recordings:
        response = row['response']
        for prompt in PROMPTS:
            messages = [{'role': 'user', 'content': prompt}]
            if fixture_key(response['provider'], response['model'], messages) == path.stem:
                actual = ReplayProvider(response['provider'], response['model']).generate(messages)
                assert actual.model_dump() == response
                replayed += 1
                break
    assert replayed == len(recordings), 'Recording requests must remain reproducible'


def test_ci_installs_cpu_dependencies_in_separate_pip_processes(tmp_path):
    """Execute the workflow install commands with a recording pip stand-in."""
    import os
    import subprocess
    import sys
    import yaml

    workflow = yaml.safe_load(Path('.github/workflows/test-suite.yml').read_text())
    commands = [step['run'] for step in workflow['jobs']['offline']['steps']
                if 'run' in step and 'requirements' in step['run']]
    executable = tmp_path / 'python'
    calls_file = tmp_path / 'calls.jsonl'
    executable.write_text('#!' + sys.executable + '\n' +
                          'import json, os, sys\n'
                          'with open(os.environ["PIP_CALL_LOG"], "a") as log:\n'
                          '    log.write(json.dumps(sys.argv[1:]) + "\\n")\n')
    executable.chmod(0o755)
    environment = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ['PATH'], PIP_CALL_LOG=str(calls_file))
    for command in commands:
        subprocess.run(command, shell=True, executable='/bin/sh', env=environment, check=True)
    calls = [json.loads(line) for line in calls_file.read_text().splitlines()]
    assert len(calls) == 2
    assert calls[0] == ['-m', 'pip', 'install', '-r', 'requirements-docker-cpu.txt']
    assert calls[1] == ['-m', 'pip', 'install', '-r', 'requirements.txt', '-r', 'requirements-dev.txt']
