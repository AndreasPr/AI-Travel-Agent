"""Select real recorded itineraries; human labels are intentionally blank."""
import argparse
import csv
import json
import random
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='eval/fixtures/recorded')
    parser.add_argument('--output', default='eval/judge/human_labels.csv')
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    rows = [json.loads(p.read_text()) for p in sorted(Path(args.root).rglob('*.json'))]
    rows = [r for r in rows if r.get('source') == 'recorded' and r.get('output', {}).get('itinerary')]
    if not rows:
        raise SystemExit('no recorded runs yet; run make eval-record first')
    if len(rows) < 20:
        raise SystemExit(f'need 20 recorded itineraries; found {len(rows)}; run make eval-record for more')
    random.Random(args.seed).shuffle(rows)
    # Refuse to overwrite human work.
    with Path(args.output).open('x', newline='') as stream:
        dimensions = ('relevance', 'coherence', 'tone')
        fields = ['id','request','itinerary'] + ['human_'+d for d in dimensions] + ['judge_'+d for d in dimensions]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows[:20]:
            writer.writerow({'id': row['id'], 'request': row['request'], 'itinerary': json.dumps(row['output']['itinerary']),
                             **{'judge_'+d: '' for d in dimensions}})


if __name__ == '__main__':
    main()
