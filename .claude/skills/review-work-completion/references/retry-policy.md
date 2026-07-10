# Retry Policy

## When to Retry

Retry on: missing CLI tool, runtime error, or malformed output format.

1. Retry up to 3 times
2. Log: `[RETRY] {agent} attempt {n}/3`
3. After 3 failures: mark agent unavailable, continue with others
4. If ALL agents fail: report failure

Consolidation uses partial results from available agents.

## Retry Mechanism (CLI reviewers vs Alice)

"Send one retry" below means different things by reviewer type:

- **Alice** (the native Claude Task Agent): message the running agent again in the same conversation, as written.
- **Bob (codex), Carl (gemini), Quinn (qwen)** (the bg-Bash CLI reviewers, PRD 00034): these are one-shot `run_in_background` Bash processes that have already exited by the time their output file is read, so there is no in-conversation target. A retry means re-dispatching a FRESH `run_in_background` Bash call of the same `*-run.sh` with an amended prompt file, writing the same `dev/local/tmp/{agent}-output-{id}.txt` path. The one-retry budget is unchanged.

## Format Compliance

If an agent's output doesn't match the required format:

1. Send one retry: "Your output format is incorrect. Reformat using exactly: `[{AGENT_NAME}] {emoji} {description} | File: {path or N/A} | Task: {id or general}` — one issue per line."
2. If still non-compliant after retry, parse what you can and note `(format warning)` next to that agent's findings in consolidation.

## Per-Rule Verdict Completeness

The reviewer prompt embeds a numbered rubric (see `references/rubric.md`) and mandates one `R{n}: pass|fail` line per rule. After parsing the agent's output:

1. For each expected rule ID `R{n}`, look for a line matching the exact regex `^R{n}:\s+(pass|fail)\s*$`. A line is **incomplete** when it is absent for an expected rule ID, OR when a line for an expected rule ID exists but its value is anything other than the literal token `pass` or `fail` (e.g. `R5: ok`, `R5: maybe`, `R5: pass (some rationale)`, `R5: PASS`).
2. If any expected rule's line is incomplete, send one retry: "Your output is missing or malformed for the per-rule verdict on {missing/malformed rule IDs}. Emit one line per rule in this exact shape: `R{n}: pass` or `R{n}: fail` — lowercase token, no extra text, no rationale, no trailing punctuation. One rule per line. A rule you cannot evaluate counts as `fail` — never omit or fudge the line."
3. If still incomplete after retry, mark each unsatisfied rule as `fail` in the consolidated record and note `(verdict warning: missing/malformed R{n}, ...)` next to that agent's findings in consolidation.
4. Combined with the issue-line retry above, the **total retry budget per agent is one retry**: the same retry can ask the agent to fix both the issue-line format and the missing/malformed verdicts together when both gates fail.
