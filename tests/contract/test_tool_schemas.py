"""Committed tool JSON Schema contracts."""
import json
from pathlib import Path
from backend.tools.models import Itinerary
from backend.tools.registry import tool_schemas

def test_schema_snapshots():
    root = Path(__file__).parents[1] / "snapshots/tools"
    schemas = {schema["name"]: schema for schema in tool_schemas()}
    schemas["itinerary"] = Itinerary.model_json_schema()
    assert {p.stem for p in root.glob("*.json")} == set(schemas)
    for name, schema in schemas.items():
        assert json.loads((root / f"{name}.json").read_text()) == schema
