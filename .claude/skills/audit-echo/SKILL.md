---
name: audit-echo
description: Use when reviewing cartographer-echo fire patterns to tune stopwords, threshold false-positives, or surface duplicate-detection trends. Triggers on "audit echo", "echo audit", "duplicate detection report".
---

# Audit Echo

Read `~/.claude/cartographer/audit.jsonl`, filter to `phase: "echo"`, and produce a findings report with severity tiers (CRITICAL/HIGH/MEDIUM/LOW) plus aggregate counts and tuning recommendations.

## Step 1: Load events

Read the audit log line-by-line, parse each JSON, retain entries with `phase == "echo"` (ignore `tree_sitter_missing` and other non-Echo warnings).

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/report.py"
```

If the audit log is missing or empty: report `LOW: no Echo events recorded in window` and stop.

## Step 2: Time-window aggregates

For each event, parse `ts` (ISO-8601 UTC). Compute counts grouped by `decision` (allow/deny/skip) and `tool` (Edit/Write/MultiEdit/Bash/mcp__serena__*) over the last 7 days and last 28 days.

Report shape:

| Window | Decision | Edit | Write | MultiEdit | Bash | mcp__serena__* |
|--------|----------|-----:|------:|----------:|-----:|---------------:|
| 7d     | allow    |      |       |           |      |                |
| 7d     | deny     |      |       |           |      |                |
| 7d     | skip     |      |       |           |      |                |
| 28d    | ...      |      |       |           |      |                |

## Step 3: Top-noisy symbols

For deny events, count `(symbol, file)` pairs that were later overridden by a `second-attempt` allow in the same session (matched on the hook's own retry signal: same `file` and symbol set, each retry consumed once). These are duplicate-detection-then-override cases: high candidates for stopword expansion. Note: pairing on the `reason == "second-attempt"` marker is exact; do not approximate it with an N-event proximity window (that inflates the override count).

Report the top 10 by deny-count, with second-attempt ratio. Anything with second-attempt ratio ≥50% over ≥5 occurrences is **HIGH** severity — propose adding to the stopword frozenset.

## Step 4: False-positive sample

List `(symbol, target_file, candidate_file:line)` for every deny event with `decision == "deny"` followed by a `second-attempt` allow in the same session. Cap output at 20 examples (most recent first).

This is manual-review fodder; surface to user so they can tally TP vs FP and decide on tuning.

## Step 5: Per-language breakdown

Infer language from the `file` extension (`.py`/`.ts`/`.tsx`/`.js`/`.jsx`/`.rs`/`.go`). Report deny/allow counts per language. Identify languages with disproportionate deny rates (>1.5× the overall mean) — **MEDIUM**: tree-sitter coverage may be over-broad for that grammar.

## Step 6: Skip distribution

Count skip events by `reason`: `settings`, `large-file`, `no-tree-sitter`, `test-file`, `unsupported-ext`, `mcp-unsupported`, `ripgrep-timeout`, `tree-sitter-parse-failed`. Report counts.

**HIGH** severity if `no-tree-sitter` count > 0 (tree-sitter pack should be installed). **MEDIUM** if `ripgrep-timeout` > 1% of total events (the latency budget is at risk). **LOW** if `mcp-unsupported` > 0 (note the coverage gap for the next iteration).

## Step 7: Findings report

Synthesize:

```
## Findings

### CRITICAL
(any item that breaks Echo's contract)

### HIGH
- {symbol X has 12 denies with 75% second-attempt rate — add to stopwords}
- {no-tree-sitter fired N times — fix package install}

### MEDIUM
- {Go shows 2.1× deny rate vs mean — investigate tree-sitter Go grammar coverage}
- {ripgrep-timeout > 1%}

### LOW
- {mcp-unsupported fires on `mcp__serena__create_text_file` — add tool_input shape handling}
- {N FP samples for manual review (see §4)}

## Summary

- Window: 7d
- Total events: ...
- Allow / deny / skip: ... / ... / ...
- Top noise symbol: ...
- Recommended next action: ...
```

## Remediation snippets

For each HIGH finding, include a copy-paste-ready remediation block when possible. Example for stopword expansion:

```python
# Edit ~/.claude/hooks/cartographer-echo.py
_STOPWORDS: frozenset[str] = frozenset({
    "__init__", "__main__", "main", "init", "setup", "run", "start", "stop",
    "new", "default", "clone", "eq", "hash", "to_string", "from_string",
    "<newword>",  # added by audit-echo on YYYY-MM-DD
})
```

## Notes

- Audit log path: `~/.claude/cartographer/audit.jsonl`.
- Event schema (PRD 00010 §Audit-log emission): `ts`, `session`, `tool`, `file`, `decision`, `reason`, `symbols`, `matches`, `phase: "echo"`.
- This skill is read-only; never mutate the audit log. Stopword/threshold tuning is a separate user action surfaced as remediation snippets.
