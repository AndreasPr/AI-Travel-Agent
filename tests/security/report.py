"""Run synthetic attack scenarios; live mode is opt-in and local Ollama only."""
import argparse
import sys

from scenarios import cases, run_case, ScenarioFailure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', help='Use the configured local Ollama model; no paid providers')
    parser.add_argument('--case', help='Run one named synthetic case')
    args = parser.parse_args()
    selected = [case for case in cases() if not args.case or case['id'] == args.case]
    if not selected:
        parser.error('Unknown case')
    providers = None
    if args.live:
        from backend.agent.providers import provider_for
        from backend.llm.config import load_config
        config = load_config()
        # Only the free local provider; never use a paid provider or download a model.
        def providers(role):
            return provider_for(role, config, provider='ollama')
    print('Synthetic adversarial cases | ' + ('LIVE LOCAL MODEL' if args.live else 'SCRIPTED REPLAY (not a live model benchmark)'))
    print('| Case | Result | Detail |\n|---|---|---|')
    failed = 0
    for case in selected:
        try:
            run_case(case, providers=providers)
            print(f"| {case['id']} | PASS | Validated itinerary and tool-log assertions passed |")
        except ScenarioFailure as exc:
            failed += 1
            print(f"| {case['id']} | FAIL | {exc.detail} |")
        except Exception as exc:
            failed += 1
            # No raw model content, exception text, PII or credentials in the report.
            print(f"| {case['id']} | FAIL | {type(exc).__name__}: expected behavior not established |")
    print(f'{len(selected) - failed} passed; {failed} failed; {len(selected)} synthetic cases')
    return bool(failed)


if __name__ == '__main__':
    sys.exit(main())
