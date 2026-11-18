"""Explicit push of saved eval scores; never invoked by default offline runs."""

import argparse
import json
from pathlib import Path


def push(rows, gateway):
    from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
    from eval.run import validate_provenance
    from eval.report import summarize

    registry = CollectorRegistry()
    gauge = Gauge("travel_eval_score", "Saved automated check pass rate (percent)", ["source", "model", "check"], registry=registry)
    groups = {}
    for row in rows:
        validate_provenance(row)
        groups.setdefault((row["source"], row["model"]), []).append(row)
    for (source, model), values in groups.items():
        for check, score in summarize(values)["per_check"].items():
            gauge.labels(source, model, check).set(score["pass_rate"])
    push_to_gateway(gateway, job="travel-evaluation", registry=registry)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="/tmp/eval-harness-run.json")
    parser.add_argument("--gateway", required=True)
    args = parser.parse_args()
    push(json.loads(Path(args.input).read_text()), args.gateway)
