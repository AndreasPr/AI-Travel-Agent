"""Regression threshold in percentage points; baseline updates are deliberate."""
import argparse
import hashlib
import json
from pathlib import Path
from eval.report import summarize
from eval.run import validate_provenance


def gate(current, baseline):
    if current['source'] != baseline['source']:
        raise ValueError('Fixture source changed; review results and deliberately update baseline')
    if current.get('suite') != baseline.get('suite'):
        raise ValueError('Fixture suite changed; deliberately update baseline after review')
    return baseline['pass_rate'] - current['pass_rate'] <= 2.0 + 1e-9


def snapshot(rows):
    for row in rows:
        validate_provenance(row)
    sources={r['source'] for r in rows}
    if len(sources)!=1:
        raise ValueError('Gate requires one nonempty provenance cohort')
    suite=hashlib.sha256(json.dumps(sorted((r['id'],r['rubric']) for r in rows),sort_keys=True).encode()).hexdigest()
    return {'source':sources.pop(),'suite':suite,'pass_rate':summarize(rows)['pass_rate'],'n':len(rows)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',default='/tmp/eval-harness-run.json')
    parser.add_argument('--baseline',default='eval/results/baseline.json')
    parser.add_argument('--update-baseline',action='store_true')
    args=parser.parse_args()
    current=snapshot(json.loads(Path(args.input).read_text()))
    path=Path(args.baseline)
    if args.update_baseline:
        path.write_text(json.dumps(current,indent=2)+'\n')
        print('Baseline deliberately updated:',current['source'])
        return
    try:
        passed=gate(current,json.loads(path.read_text()))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print('PASS' if passed else 'FAIL', 'regression gate:',current)
    if not passed:
        raise SystemExit(1)


if __name__=='__main__':
    main()
