# AI Application Design

When designing systems that include an LLM step, route deterministic work to code, not the model.

## Use the model for

- Classification with fuzzy boundaries
- Drafting prose, summaries, explanations
- Extraction from unstructured input
- Judgment calls a rubric can't fully capture

## Do NOT use the model for

- Routing on structured fields (use a switch)
- Retries, backoff, rate-limiting (use a library)
- Deterministic transforms: date parsing, unit conversion, schema mapping (use code)
- Validation against a known schema (use a validator)
- Anything where the same input must always produce the same output

If code can answer, code answers. The model is the expensive, non-deterministic last resort, not the default.
