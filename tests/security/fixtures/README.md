# Synthetic security fixtures

`synthetic_conversation.json` contains invented test-only inventory, source metadata and an expected itinerary. It is **synthetic**, not a real quote, travel recommendation or recorded provider response.

`../injections.jsonl` contains 26 manually authored synthetic attack cases with a user request, poisoned content and expected safe behavior. `../scenarios.py` builds explicitly malicious scripted response sequences, binds them to the current prompt/tools/schema hash in a temporary directory, and uses the existing `ReplayProvider` to validate and replay those fixture responses. Temporary fixtures are removed afterwards. No live responses or credentials are recorded. These tests exercise application boundaries even when a simulated model attempts an unsafe tool call or itinerary.

The offline report is a regression result, not a live-model robustness score. The live runner substitutes the configured local Ollama provider while keeping the synthetic tool runtime and safety assertions. A missing validated itinerary is a failed scenario, not automatically counted as a successful defense. Live results must be reported separately; they are not run by default.
