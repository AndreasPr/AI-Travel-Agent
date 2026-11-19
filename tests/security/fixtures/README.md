# Synthetic security scenario

`synthetic_conversation.json` contains invented test-only inventory, source metadata
and an expected itinerary. It is synthetic, not a real quote or model recording.
The 26 adversarial cases remain in ../injections.jsonl. The replay harness reads
immutable request-hashed synthetic fixtures from tests/fixtures/synthetic/security/;
it does not write replay files during tests. These are scripted tests of the pipeline,
not model behavior or evidence of immunity to prompt injection.
