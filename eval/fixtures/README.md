# Fixture provenance

Every file in `synthetic/` is **synthetic: tests the harness, not a model**. These intentionally simple fixtures include expected evaluation failures; their aggregate is a regression baseline, not a quality claim. Never attribute them to a provider/model.

`recorded/<model>/<run_id>/` is populated only by explicit `make eval-record` / `python -m eval.run --live`. It stores actual complete agent responses, tool evidence, latency and usage. Review these files for sensitive data before committing them; the agent's filtering is heuristic. Do not rename synthetic fixtures as recorded. No live recordings are included initially.

Recorded mode evaluates the committed saved responses, not model generations. If any real recordings exist, it uses those instead of synthetic fixtures. The gate then requires a deliberate recorded baseline update. No request is sent by recorded mode, and missing models remain not run. Select `--limit` and `--repeats` consistently when establishing a baseline.
