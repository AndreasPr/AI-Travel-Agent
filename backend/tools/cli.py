"""CLI arguments are derived from the same Pydantic schemas exposed to callers."""
import argparse
import json

from backend.tools.registry import REGISTRY, tool_schemas
from backend.tools.runtime import ToolRuntime


def main():
    parser = argparse.ArgumentParser(description="Run a grounded agent tool")
    parser.add_argument("tool", choices=sorted(REGISTRY) + ["schemas"])
    known, rest = parser.parse_known_args()
    if known.tool == "schemas":
        if rest:
            parser.error("schemas accepts no extra arguments")
        print(json.dumps(tool_schemas(), indent=2))
        return
    parser = argparse.ArgumentParser(prog=f"python -m backend.tools.cli {known.tool}")
    parser.add_argument("--json", help="JSON object; required for nested itinerary input unless using --itinerary JSON")
    schema = REGISTRY[known.tool].input_model.model_json_schema(by_alias=True)
    for name in schema["properties"]:
        parser.add_argument("--" + name, dest=name)
    args = vars(parser.parse_args(rest))
    raw = args.pop("json")
    try:
        payload = json.loads(raw) if raw else {}
        for key, value in args.items():
            if value is not None:
                payload[key] = json.loads(value) if schema["properties"][key].get("type") in {"object", "array"} else value
    except (ValueError, TypeError):
        parser.error("Invalid JSON arguments")
    runtime = ToolRuntime()
    try:
        result = runtime.execute(known.tool, payload)
        print(result.model_dump_json(indent=2))
        if result.status == "error":
            parser.exit(1)
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
