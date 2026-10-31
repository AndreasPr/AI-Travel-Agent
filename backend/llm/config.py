"""All provider model identities, capabilities and quotas come from YAML."""
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config/models.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def model_config(provider: str, model: str, config: dict) -> dict:
    try:
        provider_spec = config["providers"][provider]
        spec = provider_spec["models"][model]
    except KeyError as exc:
        raise ValueError("Provider/model must be declared in config/models.yaml") from exc
    return {**spec, "safety_margin": provider_spec.get("safety_margin", 1.0)}


def role_chain(role: str, profile: str | None, config: dict) -> list[dict]:
    roles = dict(config["roles"])
    if profile:
        if profile not in config.get("profiles", {}):
            raise ValueError(f"Unknown profile: {profile}")
        roles.update(config["profiles"][profile])
    if role not in roles or not roles[role].get("chain"):
        raise ValueError(f"Unknown or empty role: {role}")
    chain = roles[role]["chain"]
    for entry in chain:
        model_config(entry["provider"], entry["model"], config)
    return chain
