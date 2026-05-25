# Retry Policy

## When to Retry

Retry on: missing CLI tool, runtime error, or malformed output format.

1. Retry up to 3 times
2. Log: `[RETRY] {agent} attempt {n}/3`
3. After 3 failures: mark agent unavailable, continue with others
4. If ALL agents fail: report failure

Consolidation uses partial results from available agents.

## Format Compliance

If an agent's output doesn't match the required format:

1. Send one retry: "Your output format is incorrect. Reformat using exactly: `[{AGENT_NAME}] {emoji} {description} | File: {path or N/A} | Task: {id or general}` — one issue per line."
2. If still non-compliant after retry, parse what you can and note `(format warning)` next to that agent's findings in consolidation.

## Per-Rule Verdict Completeness

The reviewer prompt embeds a numbered rubric (see `references/rubric.md`) and mandates one `R{n}: pass|fail` line per rule. After parsing the agent's output, count the `R{n}` lines and compare against the rubric's expected rule IDs.

1. If any expected `R{n}` line is missing, send one retry: "Your output is missing the per-rule verdict for {missing rule IDs}. Emit one line per rule in this exact shape: `R{n}: pass` or `R{n}: fail`. One rule per line, no other text on the line, no rationale. A rule you cannot evaluate counts as `fail` — never omit the line."
2. If still incomplete after retry, mark each unspecified rule as `fail` in the consolidated record and note `(verdict warning: missing R{n}, ...)` next to that agent's findings in consolidation.
3. Combined with the issue-line retry above, the **total retry budget per agent is one retry**: the same retry can ask the agent to fix both the issue-line format and the missing verdicts together when both gates fail.
