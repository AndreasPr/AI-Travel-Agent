"""Synthetic modules verify the narrow third-party type-check boundary."""
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.parametrize("processor", ["dia", "csm", "voxtral"])
def test_synthetic_processor_skip_preserves_backend_type_errors(tmp_path, processor):
    config = Path('mypy.ini').resolve()
    package = tmp_path / 'transformers' / 'models' / processor
    package.mkdir(parents=True)
    for folder in (package, package.parent, package.parent.parent):
        (folder / '__init__.py').write_text('')
    (package.parent.parent / 'shared.py').write_text('def label() -> str:\n    return "synthetic"\n')
    (package / f"processing_{processor}.py").write_text('value: int = "synthetic invalid dependency value"\n')
    backend = tmp_path / 'backend'
    backend.mkdir()
    (backend / '__init__.py').write_text('')
    source = backend / 'probe.py'
    source.write_text(f'from transformers.models.{processor}.processing_{processor} import value\n'
                      'reveal_type(value)\n'
                      'count: int = 1\n'
                      'from transformers.shared import label\n'
                      'name: str = label()\n')
    command = [sys.executable, '-m', 'mypy', '--no-incremental',
               '--config-file', str(config), 'backend']
    good = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert good.returncode == 0, good.stdout + good.stderr
    assert 'Revealed type is "Any"' in good.stdout
    source.write_text(source.read_text().replace('count: int = 1', 'count: int = "invalid"'))
    bad = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert bad.returncode == 1, bad.stdout + bad.stderr
    assert 'backend/probe.py:3: error:' in bad.stdout
    assert '[assignment]' in bad.stdout
    source.write_text(source.read_text().replace('count: int = "invalid"', 'count: int = 1')
                     .replace('name: str = label()', 'name: int = label()'))
    outside = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert outside.returncode == 1, outside.stdout + outside.stderr
    assert 'backend/probe.py:5: error:' in outside.stdout
    assert '[assignment]' in outside.stdout
