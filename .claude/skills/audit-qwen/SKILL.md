---
name: audit-qwen
description: Use when producing the qwen utilization report card - dispatch rate, preflight/exclusion histograms, gate pass rate, and a WIDEN/NARROW/HOLD fence verdict from batch telemetry. Triggers on "audit qwen", "qwen report card", "qwen utilization".
---

# Audit Qwen

One deterministic script computes every number; the model only narrates.

## Dependencies

- Script: `scripts/audit_qwen.py` (stdlib-only, read-only sweep).
- CLI: `gita` (repo discovery; falls back to `~/.claude` alone with a loud note).
- Data owned elsewhere, parse targets pinned in the script's constants block:
  `run-autopilot/cli/render_report.py` + `cli/golden/expected/report-section.md`
  (Implementor Mix layout), `run-autopilot/references/state-schema.md`
  (`tasks[].attempts[]`), `run-autopilot/references/batch-report-format.md`.

## Step 1: Run the sweep

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/audit_qwen.py"
```

Optional: `--repo PATH` (repeatable) restricts the scan; `--output FILE`
writes the card to a file (use `dev/local/audit-results/` when the user
wants it kept).

## Step 2: Show the card verbatim

Paste the script's markdown output unchanged - Discovery, UNPARSED, Per
batch, Aggregate, Verdict, Method notes. Never recompute, round, or adjust
a figure, and never invent a verdict the script did not print. If a number
looks wrong, say so next to the verbatim output; do not correct it inline.

## Step 3: Narrate, separately

After the card, prose interpretation is welcome under a clearly separate
heading (e.g. `## Reading`): what moved since the last run, whether UNPARSED
rows point at format drift worth re-pinning, which fence the WIDEN ranking
would open first. Interpretation never restates altered numbers.

## Notes

- HOLD (insufficient data) below 10 recorded qwen attempts is the expected
  early answer, not a failure - the card states the count found.
- Quinn precision is permanently dropped: PRD 00094 (2026-08-09) removed its
  data source (Quinn retired, Advisory bucket deleted, historical review
  files GC'd). The card says so; do not re-add the metric.
- UNPARSED rows mean format drift or a broken file - surface them, then
  re-pin the constants block in `scripts/audit_qwen.py` against the current
  format references if the format really moved.
