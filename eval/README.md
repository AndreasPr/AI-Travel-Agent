# Offline saved-output checks

`golden/trips.yaml` contains 49 **synthetic, DRAFT** requests, seven per category. M9 requires human review of every row. These are proposed evaluation inputs, not measured quality results or verified labels. An impossible-budget label is a proposed scenario expectation, not proof about available inventory.

Run `make eval-checks OUTPUTS=/path/to/saved.jsonl` from the repository root. No database, provider, model download or network is used. Nonzero exit means a failed check, malformed input or no checks run. Partial files evaluate only supplied rows; the table does not claim full golden coverage.

Each JSONL row has `case_id` matching the golden file, `output` containing a saved ChatResponse, and `tool_results` containing the successful ToolResult evidence ledger (including earlier turns). For edits supply `previous_itinerary` and `edit_day`. The runner uses golden constraints/category/rubric, not caller overrides. Do not commit user conversations or personal data. Multi-turn rows have an initial request and follow-up `turns`; this harness checks saved results, it does not execute those turns.

Checks return `passed` and `reason`. Malformed or missing evidence fails. Travel checks fail when coordinates cannot be verified, rather than treating a skipped calculation as success. Budget checks exclude unknown costs and reject a claim that the budget is met when costs are unknown. Price checks reuse the runtime validator's quote/currency matching within 0.01; this is not proof of booking availability or full trip pricing.

Citation support reuses `CitationVerifier(use_nli=False)` against activity place names and excerpts. It is a lexical heuristic, **not semantic entailment**. URL checks require safe HTTP(S) URLs from successful saved tool data; they do not fetch URLs or verify redirects. Edit locality compares unchanged days' compact JSON serialization, including key order. Interests, party size, pace, must-include and must-avoid are recorded constraints for review; this first harness does not independently score them. Ambiguous cases currently check URL safety only; clarification quality requires human review.

Run `pytest -q tests/test_eval_checks.py` for synthetic passing and failing examples of every check.
