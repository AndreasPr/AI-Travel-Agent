# LLM fixtures

The checked-in JSON is a synthetic unit-test fixture, not a live provider recording. Its provenance field states that explicitly. The request is `[{"role":"user","content":"Synthetic replay greeting"}]`, provider `synthetic`, model `synthetic-test-model`, with no tools or schema; these are test identifiers only.

Real recordings are written only by an explicitly enabled Recorder. Filenames hash provider, model, messages, tools and schema; files store normalized responses, not request bodies or headers. Review all generated files for personal data before committing.

Claude and Bedrock recordings are not present. Their classes are replay-only and remain unverified until actual recordings are supplied.
