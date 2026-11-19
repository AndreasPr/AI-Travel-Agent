# Synthetic pipeline fixtures

These are **scripted tests of the pipeline**, not model behavior or real recordings.
Every JSON file carries synthetic provenance. Provider/model identifiers are synthetic.
`synthetic_chat.json` drives the opt-in Compose browser scenario; its fictional museum,
unknown activity price and example.invalid URL are not travel advice.

`llm/` and `security/` contain committed request-hashed synthetic fixtures extracted
from the pre-existing scripted unit tests. Tests read them and fail on a missing
hash; they do not generate replacement fixtures or call models. They do not measure
model quality. Review changes alongside their tests; never move them into recorded/.
