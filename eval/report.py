"""Reports distinguish harness fixtures from actual measured model runs."""
import argparse
import json
from pathlib import Path
import statistics
import numpy as np
from backend.llm.config import load_config
from eval.judge import LABEL
from eval.run import validate_provenance


def summarize(rows):
    checks = {}
    for row in rows:
        for name, value in row['checks'].items():
            checks.setdefault(name, []).append(value['passed'])
    values = [v for items in checks.values() for v in items]
    per_trip = [100*sum(c['passed'] for c in r['checks'].values())/len(r['checks']) for r in rows if r['checks']]
    scores = [j['score'] for r in rows for j in r.get('judge', {}).values()]
    latency = [r['latency_ms'] for r in rows if r.get('latency_ms') is not None]
    def stats(values):
        return {'mean': statistics.mean(values), 'stddev': statistics.pstdev(values), 'min': min(values), 'max': max(values)} if values else 'not run'
    return {'n': len(rows), 'cases': len({r['case_id'] for r in rows}),
            'repeats': len({r.get('repeat', 0) for r in rows}),
            'pass_rate': 100*sum(values)/len(values) if values else None,
            'per_check': {k: {'n':len(v), 'pass_rate':100*sum(v)/len(v)} for k,v in checks.items()},
            'trip_pass_rate': stats(per_trip), 'judge_score': stats(scores),
            'latency_ms': stats(latency), 'p50_ms': float(np.percentile(latency,50)) if latency else 'not run',
            'p95_ms': float(np.percentile(latency,95)) if latency else 'not run',
            'tokens_in_per_trip': stats([r['tokens_in'] for r in rows if r.get('tokens_in') is not None]),
            'tokens_out_per_trip': stats([r['tokens_out'] for r in rows if r.get('tokens_out') is not None])}


def write_report(rows, config, directory=Path('eval/results')):
    for row in rows:
        validate_provenance(row)
    result = {'models': [], 'routing': {}, 'synthetic': 'not run'}
    lines = ['# Evaluation results', '', 'Missing measurements are "not run". Rates are check-weighted; spread is population standard deviation. No booking or paid-price claims.', '',
             '| Model | n | Repeats | Check pass % | Citation support % | Judge mean | p50 / p95 ms | Tokens in / out mean | Cost |',
             '|---|---:|---:|---|---|---|---|---|---|']
    for entry in config['evaluation']['models']:
        matched = [r for r in rows if r['source']=='recorded' and r['provider']==entry['provider'] and r['model']==entry['model'] and r.get('experiment','model-single')=='model-single']
        stats = summarize(matched) if matched else None
        result['models'].append({**entry, 'results':stats or 'not run'})
        if not stats:
            lines.append(f'| {entry["model"]} | 0 | 0 | not run | not run | not run | not run | not run | not run |')
        else:
            citation=stats['per_check'].get('citations_supported',{}).get('pass_rate','not run')
            def mean(value):
                return value['mean'] if isinstance(value,dict) else value
            lines.append(f'| {entry["model"]} | {stats["n"]} | {stats["repeats"]} | {stats["pass_rate"]} | {citation} | {mean(stats["judge_score"])} | {stats["p50_ms"]} / {stats["p95_ms"]} | {mean(stats["tokens_in_per_trip"])} / {mean(stats["tokens_out_per_trip"])} | $0 (free tier) |')
    for route in ('single','split'):
        selected=[r for r in rows if r['source']=='recorded' and r.get('experiment')==route]
        result['routing'][route]=summarize(selected) if selected else 'not run'
    synthetic=[r for r in rows if r['source']=='synthetic']
    if synthetic:
        result['synthetic']={'label':LABEL, **summarize(synthetic)}
        lines += ['', f'{LABEL}: n={len(synthetic)}, check pass rate={result["synthetic"]["pass_rate"]}%. These are not model measurements.']
    lines += ['', 'Routing experiment and per-check sample sizes, means and spreads:', '```json', json.dumps({'routing':result['routing'], 'models':result['models']},indent=2), '```']
    directory.mkdir(parents=True,exist_ok=True)
    text='\n'.join(lines)+'\n'
    (directory/'RESULTS.md').write_text(text)
    (directory/'results.json').write_text(json.dumps(result,indent=2))
    return text


def inject_readme(readme=Path('README.md'), report=Path('eval/results/RESULTS.md')):
    start,end='<!-- EVAL:START -->','<!-- EVAL:END -->'
    text=readme.read_text()
    if start not in text and end not in text:
        text+='\n'+start+'\n'+end+'\n'
    if text.count(start)!=1 or text.count(end)!=1 or text.index(start)>text.index(end):
        raise ValueError('Expected one ordered EVAL marker pair')
    table=report.read_text().split('Routing experiment')[0].replace('# Evaluation results','## Evaluation results')
    readme.write_text(text.split(start)[0]+start+'\n'+table+'\n'+end+text.split(end)[1])


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',default='/tmp/eval-harness-run.json')
    parser.add_argument('--readme',action='store_true')
    args=parser.parse_args()
    write_report(json.loads(Path(args.input).read_text()),load_config())
    if args.readme:
        inject_readme()
