"""Render committed Prometheus rules from reviewed threshold configuration."""

from pathlib import Path
import yaml


def render():
    settings = yaml.safe_load(Path("config/observability.yaml").read_text())["alerts"]
    rules = [
        (
            "TravelHighErrorRate",
            f'sum(rate(travel_requests_total{{status="error"}}[5m])) / clamp_min(sum(rate(travel_requests_total[5m])), 0.001) > {settings["error_rate"]}',
        ),
        (
            "TravelHighP95Latency",
            f'histogram_quantile(0.95, sum by (le, route) (rate(travel_request_duration_seconds_bucket[5m]))) > {settings["p95_latency_seconds"]}',
        ),
        ("TravelQuotaNearlyExhausted", f'travel_quota_requests_used / travel_quota_requests_limit > {settings["quota_fraction"]}'),
    ]
    return {
        "groups": [
            {
                "name": "travel",
                "rules": [
                    {
                        "alert": name,
                        "expr": expr,
                        "for": settings["for"],
                        "labels": {"severity": "warning"},
                        "annotations": {"summary": name},
                    }
                    for name, expr in rules
                ],
            }
        ]
    }


if __name__ == "__main__":
    Path("observability/alerts.yaml").write_text(yaml.safe_dump(render(), sort_keys=False))
