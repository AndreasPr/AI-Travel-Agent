# Real provider recordings

Five committed Gemini responses have `provenance: recorded`. They cover the five
small requests declared in backend/llm/record_fixtures.py. They do not constitute a
full chat transcript. Replay is offline, hashes the exact request, and fails when
its fixture is missing. Tests requiring unavailable recordings explicitly skip
with `no recording; run make eval-record`.

Synthetic scripted tests of the pipeline are separate in ../synthetic/ and never
represent model behavior. Claude/Bedrock recordings remain unavailable.

`make record` requires explicit opt-in and GEMINI_API_KEY (M3); it calls the real
configured free provider. Review responses for sensitive content before committing.
