# Offline saved-output checks

`golden/trips.yaml` contains 49 **synthetic, DRAFT** requests, seven per category. M9 requires human review of every row. These are proposed evaluation inputs, not measured quality results or verified labels. An impossible-budget label is a proposed scenario expectation, not proof about available inventory.

Run `make eval-checks OUTPUTS=/path/to/saved.jsonl` from the repository root. No database, provider, model download or network is used. Nonzero exit means a failed check, malformed input or no checks run. Partial files evaluate only supplied rows; the table does not claim full golden coverage.

Each JSONL row has `case_id` matching the golden file, `output` containing a saved ChatResponse, and `tool_results` containing the successful ToolResult evidence ledger (including earlier turns). For edits supply `previous_itinerary` and `edit_day`. The runner uses golden constraints/category/rubric, not caller overrides. Do not commit user conversations or personal data. Multi-turn rows have an initial request and follow-up `turns`; this harness checks saved results, it does not execute those turns.

Checks return `passed` and `reason`. Malformed or missing evidence fails. Travel checks fail when coordinates cannot be verified, rather than treating a skipped calculation as success. Budget checks exclude unknown costs and reject a claim that the budget is met when costs are unknown. Price checks reuse the runtime validator's quote/currency matching within 0.01; this is not proof of booking availability or full trip pricing.

Citation support reuses `CitationVerifier(use_nli=False)` against activity place names and excerpts. It is a lexical heuristic, **not semantic entailment**. URL checks require safe HTTP(S) URLs from successful saved tool data; they do not fetch URLs or verify redirects. Edit locality compares unchanged days' compact JSON serialization, including key order. Interests, party size, pace, must-include and must-avoid are recorded constraints for review; this first harness does not independently score them. Ambiguous cases currently check URL safety only; clarification quality requires human review.

Run `pytest -q tests/test_eval_checks.py` for synthetic passing and failing examples of every check.

## Second-half harness

`make eval` rechecks committed saved responses offline and prints the report. Initially the cohort is **synthetic: tests the harness, not a model**; all real-model rows remain not run. `make eval-gate` compares the same cohort with the committed baseline and fails on a drop greater than 2 percentage points. A source/suite change fails explicitly until a human reviews and updates the baseline:

```
python -m eval.gate --update-baseline
```

That command is deliberate; CI never updates it. Recorded responses are preferred over synthetic fixtures when present. Replaying saved outputs measures checker regression, not generation repeatability. Recorded repeats are separate live executions; offline replay never fabricates additional independent samples.

### Explicit live recording (M10)

Requires your migrated Postgres tool cache/quota tables, seeded synthetic inventory, existing retrieval corpus and local embedding/reranking models. For local providers, Ollama must already serve the configured models. Nothing here downloads models. For the configured Gemini route, export your key yourself. The evaluation runner uses the existing ManagedProvider safety margins, minute/token limits and persistent Pacific-time daily counter. Concurrency is configured in models.yaml (default one); exhausted limits may produce failed agent turns, which are preserved rather than hidden.

```
make eval-record EVAL_MODEL_INDEX=0 EVAL_LIMIT=2 EVAL_REPEATS=1 EVAL_RUN_ID=gemini-trial
make eval-record EVAL_MODEL_INDEX=1 EVAL_LIMIT=2 EVAL_REPEATS=1 EVAL_RUN_ID=local-first
make eval-record EVAL_MODEL_INDEX=2 EVAL_LIMIT=2 EVAL_REPEATS=1 EVAL_RUN_ID=local-second
```

The index selects evaluation.models in config/models.yaml. Repeating an identical command resumes completed cases; changing case/config content with the same run ID is rejected. Use a new run ID for new measurements. Files are saved atomically per completed case; interruption during a case may require repeating that case and consuming quota again. Use one process per run ID.

Routing experiment (same cases/repeats for a fair comparison):

```
make eval-record EVAL_ROUTE=single EVAL_LIMIT=2 EVAL_REPEATS=1 EVAL_RUN_ID=route-single
make eval-record EVAL_ROUTE=split EVAL_LIMIT=2 EVAL_REPEATS=1 EVAL_RUN_ID=route-split
```

Routes are explicit config entries; split means the selected smaller extraction model and selected planning model, not a measured strength claim. No provider fallback is used for comparison roles, so another model cannot silently supply a named model's result. Compare matched runs; report sample sizes are included. Model-comparison and routing cohorts are separate.

After judging/calibrating (see judge/README.md), regenerate reports from all selected recordings:

```
make eval EVAL_REPEATS=1
make eval-report
```

Set EVAL_REPEATS to include all desired recorded repeat indices. RESULTS.md and results.json include check-weighted rates, per-check denominators, per-trip mean/population spread, sample size, repeat count, citation support, qualitative judge scores, latency percentiles and tokens. Unknown metrics say not run. The $0 (free tier) label describes the selected free-provider policy, not a measured provider billing statement. Claude is omitted: current config has no enabled Claude model or verified credit; no paid-provider call is made.

The README injector only replaces the EVAL marker block. The PR workflow runs the offline gate; the dispatch workflow requires an operator-provisioned self-hosted runner with the above dependencies and an explicitly added GEMINI_API_KEY secret. Protect the eval-live environment and run trusted revisions only. It does not install models or reset databases. Workflow execution itself has not been verified locally.
