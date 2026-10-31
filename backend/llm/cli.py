"""Local CLI; model identity and limits are resolved only from configuration."""
import argparse
import json

from backend.llm.config import load_config, model_config, role_chain
from backend.llm.limits import PostgresDailyCounter, effective_limits
from backend.llm.router import Router
from backend.llm.types import LLMError


def main():
    parser = argparse.ArgumentParser(description="Free-provider LLM development CLI")
    parser.add_argument("--role", default="extract")
    parser.add_argument("--profile")
    parser.add_argument("--prompt")
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--show-limits", action="store_true")
    args = parser.parse_args()
    if bool(args.provider) != bool(args.model):
        parser.error("--provider and --model must be supplied together")
    config = load_config()
    try:
        chain = [{"provider": args.provider, "model": args.model}] if args.provider else role_chain(args.role, args.profile, config)
        for entry in chain:
            model_config(entry["provider"], entry["model"], config)
        if args.show_limits:
            for entry in chain:
                limits = effective_limits(model_config(entry["provider"], entry["model"], config))
                try:
                    remaining = PostgresDailyCounter().remaining(entry["provider"], entry["model"], limits["rpd"])
                except LLMError:
                    remaining = "unavailable: migrate/start Postgres"
                print(json.dumps({**entry, "effective_limits": limits, "remaining_daily": remaining}))
        if args.prompt is None:
            if args.show_limits:
                return
            parser.error("--prompt is required unless only showing limits")
        router = Router(chain, config)
        response = router.generate([{"role": "user", "content": args.prompt}])
        remaining = router.chosen.remaining_daily() if hasattr(router.chosen, "remaining_daily") else "replay: no quota consumed"
        print(json.dumps({**response.model_dump(mode="json"), "remaining_daily": remaining}, indent=2))
    except (LLMError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
