from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from backend.env import config

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


def read_yaml(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return payload if isinstance(payload, dict) else {}


def get_embedding_model_name() -> str:
    payload = read_yaml(CONFIG_DIR / "models.yaml")
    return payload.get("embeddings", {}).get("model", "BAAI/bge-small-en-v1.5")


def get_reranker_model_name() -> str:
    payload = read_yaml(CONFIG_DIR / "models.yaml")
    return payload.get("reranker", {}).get("model", "cross-encoder/ms-marco-MiniLM-L-6-v2")


def get_nli_model_name() -> str:
    payload = read_yaml(CONFIG_DIR / "models.yaml")
    return payload.get("nli", {}).get("model", "cross-encoder/nli-deberta-v3-small")


def get_nli_threshold() -> float:
    payload = read_yaml(CONFIG_DIR / "models.yaml")
    threshold = payload.get("nli", {}).get("threshold", 0.7)
    try:
        return float(threshold)
    except (TypeError, ValueError):
        return 0.7


def read_city_country_map(path: str | Path | None = None) -> dict[str, str]:
    target = Path(path) if path else CONFIG_DIR / "cities.yaml"
    data = read_yaml(target)
    mapping: dict[str, str] = {}
    for entry in data.get("cities", []) or []:
        if isinstance(entry, dict):
            name = str(entry.get("name") or entry.get("city") or "").strip()
            country = str(entry.get("country") or entry.get("country_name") or "").strip()
            if name and country:
                mapping[name] = country
        elif isinstance(entry, str):
            mapping[str(entry).strip()] = "Unknown"
    return mapping


def read_cities(path: str | Path | None = None) -> list[str]:
    target = Path(path) if path else CONFIG_DIR / "cities.yaml"
    data = read_yaml(target)
    cities = data.get("cities")
    if isinstance(cities, list):
        entries: list[str] = []
        for city in cities:
            if isinstance(city, dict):
                name = city.get("name") or city.get("city")
                if name:
                    entries.append(str(name))
            elif city:
                entries.append(str(city))
        return entries
    if isinstance(cities, dict):
        return [str(city_name) for city_name in cities.keys()]
    return []


def get_wikivoyage_user_agent() -> str:
    return config("WIKIVOYAGE_USER_AGENT", default="ai-travel-agent-rag/0.1 (local use; contact: maintainers@example.com)")


def project_root() -> Path:
    return ROOT
