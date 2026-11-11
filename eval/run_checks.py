"""Evaluate saved JSONL outputs offline; never invoke the agent or a provider."""
import argparse
import json
from pathlib import Path
import yaml
from eval.checks import run_check
from eval.golden.schema import GoldenCase


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('outputs', type=Path)
    parser.add_argument('--golden', type=Path, default=Path('eval/golden/trips.yaml'))
    args = parser.parse_args()
    cases = [GoldenCase.model_validate(row) for row in yaml.safe_load(args.golden.read_text())]
    indexed = {case.id: case.model_dump(mode='json') for case in cases}
    if len(indexed) != len(cases):
        parser.error('Duplicate golden IDs')
    failed, count = 0, 0
    print('Synthetic DRAFT cases — saved-output checks; no models run')
    print('| Case | Check | Result | Reason |')
    print('|---|---|---|---|')
    for line_number, line in enumerate(args.outputs.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            case = indexed[row['case_id']]
            record = {**row, 'constraints': case['constraints'], 'category': case['category']}
        except (ValueError, KeyError, TypeError):
            print(f'| line {line_number} | input | FAIL | Invalid JSON or unknown case ID |')
            failed += 1
            continue
        for name in case['rubric']:
            result = run_check(name, record)
            count += 1
            failed += not result.passed
            print(f"| {case['id']} | {name} | {'PASS' if result.passed else 'FAIL'} | {result.reason} |")
    print(f'{count} checks run; {failed} failures; {len(cases)} draft golden cases available (not a coverage claim)')
    return 1 if failed or not count else 0


if __name__ == '__main__':
    raise SystemExit(main())
