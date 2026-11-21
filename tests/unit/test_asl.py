"""Offline state-machine validation using the installed, pinned npm package."""
import subprocess


def test_asl_definition_is_valid():
    result = subprocess.run(['node', 'scripts/validate_asl.cjs'], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'not deployed' in result.stdout
