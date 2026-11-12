"""Agreement on human-filled qualitative labels; missing labels are never imputed."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr


def agreement(human, judge):
    if len(human) != len(judge) or len(human) < 2:
        raise ValueError('At least two paired scores required')
    if any(int(x) != x or not 1 <= x <= 5 for x in [*human, *judge]):
        raise ValueError('Scores must be integers from 1 to 5')
    rho = None if len(set(human)) < 2 or len(set(judge)) < 2 else float(spearmanr(human, judge).statistic)
    a, b = np.array(human) >= 4, np.array(judge) >= 4
    observed = float(np.mean(a == b))
    chance = float(a.mean() * b.mean() + (1-a.mean()) * (1-b.mean()))
    kappa = None if chance == 1 else (observed-chance)/(1-chance)
    return {'n': len(human), 'spearman': rho, 'kappa': kappa}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--labels', default='eval/judge/human_labels.csv')
    parser.add_argument('--recorded', default='eval/fixtures/recorded')
    parser.add_argument('--output', default='eval/results/judge_agreement.md')
    args = parser.parse_args()
    if not Path(args.labels).exists():
        raise SystemExit('no human labels yet; generate and fill the calibration CSV first')
    rows = list(csv.DictReader(Path(args.labels).open()))
    recorded = {r['id']: r for p in Path(args.recorded).rglob('*.json')
                if (r := json.loads(p.read_text())).get('source') == 'recorded'}
    for row in rows:
        for dimension in ('relevance', 'coherence', 'tone'):
            if row['id'] in recorded:
                row['judge_'+dimension] = recorded[row['id']].get('judge', {}).get(dimension, {}).get('score', '')
    lines = ['# Judge agreement', '', 'Binarization: scores 4–5 versus 1–3. Undefined correlations are not replaced with zero.', '', '| Dimension | n | Spearman | Cohen kappa |', '|---|---:|---|---|']
    for dimension in ('relevance', 'coherence', 'tone'):
        pairs = [(int(r['human_'+dimension]), int(r['judge_'+dimension])) for r in rows
                 if r.get('human_'+dimension) and r.get('judge_'+dimension)]
        stats = agreement(*map(list, zip(*pairs, strict=True))) if len(pairs) >= 2 else None
        lines.append(f'| {dimension} | {len(pairs)} | {stats["spearman"] if stats else "not run"} | {stats["kappa"] if stats else "not run"} |')
    Path(args.output).write_text('\n'.join(lines)+'\n')


if __name__ == '__main__':
    main()
