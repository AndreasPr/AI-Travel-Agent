"""Resumable saved-response evaluation with explicit live opt-in."""
import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
import yaml

from backend.llm.config import load_config
from eval.checks import run_check
from eval.judge import LABEL


def validate_provenance(row):
    if row.get('source') == 'synthetic':
        if row.get('model') != LABEL or row.get('label') != LABEL or row.get('provider') != 'synthetic':
            raise ValueError('Synthetic fixtures must never be attributed to a real model')
    elif row.get('source') != 'recorded':
        raise ValueError('Unknown fixture provenance')


def fixture_paths(root=Path('eval/fixtures')):
    recorded = sorted((root / 'recorded').rglob('*.json'))
    return recorded or sorted((root / 'synthetic').glob('*.json'))


def evaluate(row):
    validate_provenance(row)
    return {**row, 'checks': {name: vars(run_check(name, row)) for name in row['rubric']}}


async def cached_run(path, fingerprint, execute):
    if path.exists():
        row = json.loads(path.read_text())
        if row.get('fingerprint') != fingerprint:
            raise ValueError('Run ID reused with different case/config; choose a new run ID')
        return row
    row = await execute()
    row['fingerprint'] = fingerprint
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(row, indent=2))
    temporary.replace(path)
    return row


async def live_case(case, config, route, run_id, repeat):
    from backend.agent.loop import Agent
    from backend.agent.models import ChatRequest
    from backend.agent.store import MemoryTripStore
    from backend.agent.providers import provider_for
    settings = deepcopy(config)
    for role, entry in route.items():
        settings['roles'][role] = {'chain': [entry]}
    agent = Agent(store=MemoryTripStore(), config=settings, providers=lambda role: provider_for(role, settings))
    started = time.perf_counter()
    output, previous = None, None
    ledger = {}
    tokens_in = tokens_out = 0
    try:
        for message in [case['request'], *case.get('turns', [])]:
            previous = output.itinerary.model_dump(mode='json') if output and output.itinerary else None
            output = await agent.chat(ChatRequest(message=message, trip_id=output.trip_id if output else None))
            tokens_in += output.usage.tokens_in
            tokens_out += output.usage.tokens_out
            for row in output.tool_trace:
                if row.get('tool_result_id'):
                    ledger[row['tool_result_id']] = row
        entry = route['plan']
        return {**case, 'id': f'{run_id}:{case["id"]}:{repeat}', 'case_id': case['id'],
                'run_id': run_id, 'repeat': repeat, 'source': 'recorded',
                'provider': entry['provider'], 'model': entry['model'], 'route': route,
                'output': output.model_dump(mode='json'), 'tool_results': list(ledger.values()),
                'previous_itinerary': previous, 'edit_day': (output.diff or {}).get('day'),
                'latency_ms': (time.perf_counter()-started)*1000,
                'tokens_in': tokens_in, 'tokens_out': tokens_out}
    finally:
        agent.runtime.close()


async def run_live(args, config):
    cases = yaml.safe_load(Path('eval/golden/trips.yaml').read_text())[:args.limit]
    if args.route:
        route = config['evaluation']['routes'][args.route]
    else:
        entry = config['evaluation']['models'][args.model_index]
        route = {'extract': entry, 'plan': entry}
    if any(entry['provider'] not in {'gemini', 'ollama'} for entry in route.values()):
        raise ValueError('Live evaluation permits free configured providers only')
    model = route['plan']['model']
    safe_model = model.replace('/', '_').replace(':', '_')
    if not args.run_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.run_id):
        raise ValueError('Use an alphanumeric run ID with hyphens or underscores')
    # Sequential by default: each model call retains ManagedProvider rpm/tpm/rpd
    # admission, shared token buckets and the persistent Postgres daily counter.
    if config['evaluation']['concurrency'] < 1:
        raise ValueError('evaluation.concurrency must be positive')
    semaphore = asyncio.Semaphore(config['evaluation']['concurrency'])
    async def one(case, repeat):
        fingerprint = hashlib.sha256(json.dumps([case, config, route, repeat], sort_keys=True).encode()).hexdigest()
        path = Path('eval/fixtures/recorded') / safe_model / args.run_id / f'{case["id"]}-{repeat}.json'
        async def execute():
            async with semaphore:
                return await live_case(case, config, route, args.run_id, repeat)
        row = await cached_run(path, fingerprint, execute)
        row['experiment'] = args.route or 'model-single'
        # Persist experiment metadata as well as the measured response.
        path.write_text(json.dumps(row, indent=2))
        return row
    return await asyncio.gather(*(one(case, repeat) for case in cases for repeat in range(args.repeats)))


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--live', action='store_true')
    mode.add_argument('--recorded', action='store_true')
    parser.add_argument('--limit', type=int, default=49)
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--run-id')
    parser.add_argument('--model-index', type=int, default=0)
    parser.add_argument('--route', choices=['single','split'])
    parser.add_argument('--output', default='/tmp/eval-harness-run.json')
    args = parser.parse_args()
    if args.limit < 1 or args.repeats < 1:
        parser.error('limit and repeats must be positive')
    config = load_config()
    if args.live:
        rows = asyncio.run(run_live(args, config))
    else:
        rows = [json.loads(p.read_text()) for p in fixture_paths()]
        selected = list(dict.fromkeys(r['case_id'] for r in rows))[:args.limit]
        rows = [r for r in rows if r['case_id'] in selected and r.get('repeat', 0) < args.repeats]
    if not rows:
        parser.error('No evaluation fixtures selected')
    results = [evaluate(row) for row in rows]
    Path(args.output).write_text(json.dumps(results, indent=2))
    from eval.report import write_report
    print(write_report(results, config))


if __name__ == '__main__':
    main()
