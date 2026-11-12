"""Explicit live qualitative judging of real recordings only."""
import argparse
import json
from pathlib import Path
from backend.agent.providers import provider_for
from eval.judge import judge_batch
from backend.llm.config import load_config
from backend.llm.types import LLMError


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true',required=True)
    parser.add_argument('--batch-size',type=int,default=4)
    parser.add_argument('--seed',type=int,default=0)
    parser.add_argument('--pairwise',action='store_true',help='Randomized blind batches of two; compare rubric scores')
    args=parser.parse_args()
    size=2 if args.pairwise else args.batch_size
    settings=load_config()['evaluation']['judge']
    if not 1 <= size <= settings['max_batch_size']:
        parser.error('batch-size must be within configured judge bounds')
    paths=sorted(Path('eval/fixtures/recorded').rglob('*.json'))
    if not paths:
        parser.error('no recorded runs yet; run make eval-record first')
    provider=provider_for('judge')
    eligible=[]
    for path in paths:
        row=json.loads(path.read_text())
        if row.get('source')=='recorded' and row['output'].get('itinerary') and not row.get('judge'):
            eligible.append((path,row))
    if args.pairwise:
        eligible.sort(key=lambda pair: (pair[1]['case_id'], pair[1].get('repeat', 0), pair[1]['id']))
    for offset in range(0,len(eligible),size):
        batch=eligible[offset:offset+size]
        if args.pairwise and (len(batch)!=2 or batch[0][1]['case_id']!=batch[1][1]['case_id']):
            raise SystemExit('Pairwise judging requires two recordings of the same case per batch')
        print(f'Judging batch {offset//size+1}: {len(batch)} itineraries', flush=True)
        try:
            scores=judge_batch(provider,[r for _,r in batch],args.seed+offset,settings=settings)
        except LLMError as exc:
            raise SystemExit(f'Judge stopped ({type(exc).__name__}); this batch was not saved. Earlier judgments and human labels are preserved. Rerun to resume.') from None
        for path,row in batch:
            row['judge']=scores[row['id']]
            row['judge_protocol']={'seed':args.seed+offset,'pairwise':args.pairwise,'rubric_version':1}
            temporary=path.with_suffix('.tmp')
            temporary.write_text(json.dumps(row,indent=2))
            temporary.replace(path)


if __name__=='__main__':
    main()
