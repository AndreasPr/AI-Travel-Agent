"""Verify offline entry points in a fresh interpreter without live dependencies."""
import subprocess
import sys


def test_offline_eval_does_not_import_live_dependencies(tmp_path):
    script = r'''
import importlib.abc
import json
from pathlib import Path
import sys

class NoLiveDependencies(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {
            'jsonschema', 'httpx', 'google', 'anthropic', 'boto3', 'psycopg',
            'pgvector', 'sqlalchemy', 'torch', 'sentence_transformers',
        }:
            raise ModuleNotFoundError('Offline evaluation imported live dependency: ' + fullname)
sys.meta_path.insert(0, NoLiveDependencies())
import eval.run
import eval.report
from eval.gate import snapshot, gate

output = Path(sys.argv[1])
original_report = eval.report.write_report
eval.report.write_report = lambda rows, config: original_report(rows, config, output.parent / 'report')
sys.argv = ['eval.run', '--recorded', '--limit', '1', '--output', str(output)]
eval.run.main()
rows = json.loads(output.read_text())
assert rows
current = snapshot(rows)
assert gate(current, current)
assert 'backend.llm.router' not in sys.modules
assert 'backend.tools.runtime' not in sys.modules
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path/'run.json')],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
