---
name: audit-sessions
description: >-
  Use when analyzing session transcripts for patterns, anomalies, skill effectiveness,
  and improvements. Triggers on "audit sessions", "session patterns", "session intelligence",
  "what am I repeating", "session anomalies", "unused skills".
---

# Audit Session Patterns

Surface automation opportunities, retry storms, skill effectiveness gaps,
and rule violations from recent session transcripts. The deterministic
counting (parsing, n-grams, regex rule checks, set differences) lives in
`scripts/analyze.py`. This skill orchestrates the run and translates raw
findings into prioritized, actionable recommendations.

Accepts an optional argument: number of days to look back (default: 30).

## Step 1: Run analyzer

Parse the days argument from the user's invocation. Default to 30.

```
Bash: python3 ~/.claude/skills/audit-sessions/scripts/analyze.py --days {N}
```

Capture stdout JSON. If exit non-zero, surface stderr and stop.

The output schema (top level):

- `scanned`: counts and date range
- `findings`: array of finding records, each with `category`, `classification`,
  `title`, `frequency`, `sessions`, `projects`, `evidence[]`, `details{}`
- `skill_usage`: `{invoked: {name: count}, never_invoked: [name], negative_followup: [{skill, count}]}`

Categories the script emits: `tool_sequence`, `repeated_prompt`,
`rule_violation`, `rejection_storm`, `skill_unused`, `skill_negative`,
`token_heavy_session`, `compaction_early`.

## Step 2: Synthesize qualitative findings

The script flags candidates by frequency. You add the judgment.

For each `repeated_prompt` cluster: read the sample originals from `evidence[]`.
Decide if the cluster is a coherent workflow (skill candidate) or a repeated
context dump (memory candidate). Generate a candidate skill name and a
one-line description in trigger-led style.

For each `tool_sequence` n-gram: read `evidence[0]` from one example
session at the line indicated. Decide if the sequence is a routine workflow
worth automating, or just frequent reads/edits with no semantic unity.
Reject if the sequence is a generic "Read → Edit → Read" cycle that doesn't
encode a specific task.

For each `skill_unused` finding: the script confirmed at least one trigger
phrase appeared in user text. Propose a description rewrite that would
have caught the matched user phrase. Use `details.matched_triggers` as evidence.

For each `skill_negative` finding: read the evidence snippets. The user
said something corrective right after the skill ran. Decide whether the
skill misread the request, did the wrong thing, or the user just needed
to clarify. The first two are real issues; the third is noise.

For each `rejection_storm`: the script identified consecutive same-tool
failures. Look at the session at the start line and decide if the storm
reflects a tool config issue (permission, schema) or just a hard task.

For each `rule_violation`: spot-check `evidence[]` to confirm the script
caught real violations (not false positives in pipe contexts the regex missed).

## Step 3: Apply time-saved estimates

Per-classification multiplier (minutes saved per occurrence):

| classification | multiplier |
|---|---|
| `agent_candidate` | 15 |
| `skill_candidate` | 5 |
| `hook_candidate` | 4 |
| `config_fix` | 3 |
| `workflow_improvement` | 2 |
| `memory_candidate` | 1 |

Impact = `frequency × multiplier`. Sort findings by impact descending.

## Step 4: Print report

Use this layout (omit any category whose findings array is empty after Step 2 filtering):

```
SESSION INTELLIGENCE REPORT
===========================

Sessions analyzed: {scanned.sessions_total} ({scanned.days}d, {scanned.projects} projects)
Date range: {earliest} → {latest}
Median session length: {scanned.median_message_count} messages

AUTOMATION OPPORTUNITIES (skill / agent candidates):

  1. "{title}" - {classification} | impact ≈ {impact} min
     Frequency: {frequency} | Sessions: {len(sessions)} | Projects: {projects}
     Evidence: {evidence[0].snippet} (session {evidence[0].session}:{evidence[0].line})
     +-------------------------------------------------------
     | REMEDIATION
     | {what to create / change}
     | {where}
     | Effort: {S/M/L}
     +-------------------------------------------------------

ANOMALIES (storms, dead ends, token-heavy):
  ...

SKILL EFFECTIVENESS:
  Unused: {comma-separated skill_unused titles}
  Negative follow-up: {skill_negative entries}
  Top invoked: {skill_usage.invoked top 5 by count}

RULE VIOLATIONS:
  ...

Top 3 highest-impact: {numbered, with weekly-time-saved estimate}
```

If a section has no findings after qualitative filtering, print "None" under it.

## Step 5: Offer remediation

For findings the user wants to act on, execute the remediation plan directly:

- New skill: invoke `create-skill` skill or write SKILL.md to `~/.claude/skills/<name>/`.
- Memory entry: write to `~/.claude/projects/.../memory/` and update `MEMORY.md` index.
- Skill description rewrite: edit the SKILL.md frontmatter `description`.
- Rule addition: edit `~/.claude/CLAUDE.md` or appropriate rules file.
- Config fix: edit `~/.claude/settings.json` (consider `update-config` skill).

Ask before making changes. Group related fixes when possible.
