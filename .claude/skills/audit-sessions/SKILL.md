---
name: audit-sessions
description: >-
  Use when analyzing session transcripts for patterns, anomalies, skill effectiveness,
  and improvements. Triggers on "audit sessions", "session patterns", "session intelligence",
  "what am I repeating", "session anomalies", "unused skills".
---

# Audit Session Patterns

Analyze recent session transcripts across projects. Surface automation opportunities, anomalies, skill effectiveness issues, and improvement opportunities with actionable remediation plans.

Accepts an optional argument: number of days to look back (default: 30).

## Step 1: Discover sessions

Parse the days argument from the user's invocation. Default to 30 if not provided.

```
Glob("~/.claude/projects/*/sessions-index.json")
```

For each sessions-index.json, read the file and filter to sessions where:
- `modified` or `created` is within the lookback window
- `messageCount` >= 10 (skip trivial sessions)

Record each qualifying session:
- sessionId
- firstPrompt
- summary
- messageCount
- projectPath (derive from the sessions-index.json parent directory name)

If no qualifying sessions found, report that and stop.

## Step 2: Build skill inventory

Before reading any session data, build the list of installed skills from the system prompt's skill listing. Extract every skill name shown in the "The following skills are available" block.

Also scan for skills on disk:

```
Glob("~/.claude/skills/*/SKILL.md")
```

Record the union as the known skill set. This is used in Step 5 for effectiveness analysis.

## Step 3: Read session data

For each qualifying session, read the JSONL transcript:

```
~/.claude/projects/{project-dir}/{sessionId}.jsonl
```

Token efficiency rules:
- Sessions with messageCount <= 100: read the full file
- Sessions with messageCount > 100: read first 50 lines, then read last 50 lines (use offset/limit). This captures the opening context and final resolution while skipping the middle.

From each session, extract:
- **User messages**: lines where `type` is "user" or the message role is "user". Record the text content.
- **Tool calls**: lines containing tool use. Record tool name, whether it succeeded or was rejected, and any error messages.
- **Skill invocations**: tool calls to the "Skill" tool. Record which skill was invoked.
- **Correction signals**: user messages that follow an assistant turn and contain correction language (e.g., "no", "wrong", "actually", "instead", "undo", "revert", "try again", "that's not right").
- **Compaction events**: lines indicating context compaction or reset.

Process projects one at a time to keep context manageable. After processing each project's sessions, record findings before moving to the next project.

## Step 4: Analyze automation opportunities

### 4a: Repeated prompts

Compare user first-prompts and message content across sessions. Flag clusters where 3+ sessions contain semantically similar user requests. Use the firstPrompt and summary fields for initial grouping, then confirm with message content.

### 4b: Tool sequences

Identify ordered sequences of 3+ tool calls that appear in 2+ sessions. Focus on the tool names and their order, not the specific arguments.

### 4c: Workarounds

Find instances where a tool call was rejected (permission denied, error) and the user or assistant immediately tried an alternative approach. Patterns: Bash rejected then Grep used, or same tool retried with different parameters.

### 4d: Multi-step recipes

Find assistant turns with 5+ sequential tool calls for a single task type. These are candidates for skill or agent automation.

### 4e: Correction patterns

Find recurring correction signals (from Step 3) that appear across 2+ sessions with similar context. These indicate persistent misunderstandings.

## Step 5: Analyze anomalies

### 5a: Token-heavy sessions

Flag sessions where messageCount is more than 2x the median across all analyzed sessions. Include the firstPrompt and summary to identify what made them expensive.

### 5b: Retry storms

Find sequences where the same tool is called 3+ times in a row with minor parameter variations. This indicates unclear errors or flaky behavior.

### 5c: Permission friction

Count tool rejections per session. Flag sessions with 3+ rejections. Identify which tools are most frequently rejected.

### 5d: Dead ends

Find sequences of 5+ exploration tool calls (Read, Grep, Glob) that are followed by an unrelated direction change. Indicates wasted context on abandoned investigation.

### 5e: Early context resets

Flag sessions where compaction events occur in the first third of the session (by message index). This suggests context-hungry patterns.

## Step 6: Analyze skill effectiveness

This is the critical analysis section.

### 6a: Unused skills

Compare the skill inventory (Step 2) against all Skill tool invocations found across sessions (Step 3).

For each skill that was never invoked:
- Check if any session's user messages or firstPrompts match the skill's trigger keywords
- Suggest WHY it may be unused: bad trigger description, niche use case, superseded by another skill, or user unaware
- Suggest HOW to improve adoption: better description wording, alias triggers, or deprecation if truly unused

### 6b: Underperforming skills

For each skill that was invoked, check what happened immediately after invocation:
- User correction within 3 messages of skill invocation
- User manually redoing the skill's output
- Negative language ("wrong", "no", "not what I wanted", "undo")

Flag skills with 2+ negative outcomes. Include the specific evidence (session ID, what the user said).

### 6c: Skill underuse

For each session where the user performed a manual multi-step task, check if an existing skill covers that workflow. Compare the task description (from user messages) against skill names and descriptions.

Flag cases where a matching skill exists but was not invoked.

## Step 7: Analyze improvement opportunities

### 7a: Rule violations

Check session tool calls for patterns that violate known rules:
- Bash used for `grep`/`rg` when Grep tool exists
- Bash used for `cat`/`head`/`tail` when Read tool exists
- Bash used for `find` when Glob tool exists
- Bash used for `echo >` when Write tool exists
- Full file reads (no offset/limit) on files that were later re-read with ranges

### 7b: Missing memories

Find information that the user explains 2+ times across different sessions:
- Same correction given multiple times
- Same context or preference re-stated
- Same project-specific knowledge re-explained

These should be persisted to memory files.

## Step 8: Classify and prioritize findings

Assign each finding one classification:

| Type | Criteria |
|------|----------|
| **Skill candidate** | Repeating workflow with enough structure to codify |
| **Agent candidate** | Complex multi-step task that could run autonomously |
| **Hook candidate** | Automatic action that should trigger on an event |
| **Memory candidate** | Recurring feedback or context that should be saved |
| **Config fix** | Settings, rules, or permissions that need adjustment |
| **Workflow improvement** | Process change that would reduce friction |

Rank findings by estimated impact: frequency x estimated time saved per occurrence.

## Step 9: Output report

Print in this format:

```
SESSION INTELLIGENCE REPORT
===========================

Sessions analyzed: {N} (last {days} days, across {P} projects)
Median session length: {M} messages

AUTOMATION OPPORTUNITIES:

  1. "{title}" - {classification}
     Frequency: {N} sessions | Projects: {list}
     Pattern: {one-line description}
     Sessions: {id1}, {id2}
     +-------------------------------------------------------
     | REMEDIATION PLAN
     |
     | {What to change}
     | {Where to change it}
     | {Why it helps}
     | Effort: {estimate}
     +-------------------------------------------------------

ANOMALIES:

  2. {title}
     Frequency: {N} sessions
     Pattern: {description}
     Sessions: {ids}
     +-------------------------------------------------------
     | REMEDIATION PLAN
     |
     | {Root cause analysis}
     | {Fix steps}
     | Effort: {estimate}
     +-------------------------------------------------------

SKILL EFFECTIVENESS:

  3. Unused: {skill-name}
     Likely cause: {why}
     +-------------------------------------------------------
     | REMEDIATION PLAN
     |
     | {How to improve adoption or deprecate}
     | Effort: {estimate}
     +-------------------------------------------------------

  4. Underperforming: {skill-name}
     Evidence: {what happened in which session}
     +-------------------------------------------------------
     | REMEDIATION PLAN
     |
     | {What to fix in the skill}
     | Effort: {estimate}
     +-------------------------------------------------------

  5. Underused: {skill-name} - user did {task} manually
     Sessions: {ids}
     +-------------------------------------------------------
     | REMEDIATION PLAN
     |
     | {Why skill wasn't triggered, how to fix}
     | Effort: {estimate}
     +-------------------------------------------------------

IMPROVEMENT OPPORTUNITIES:

  6. {title}
     Frequency: {N} instances across {M} sessions
     +-------------------------------------------------------
     | REMEDIATION PLAN
     |
     | {What to change, where, why}
     | Effort: {estimate}
     +-------------------------------------------------------

Summary: {counts by category}
Top 3 highest-impact findings: {numbered list with estimated weekly time savings}
```

If a category has no findings, print "None" under that heading.

## Step 10: Offer remediation

For findings the user wants to act on, execute the remediation plan directly:
- Create new skills or memory entries
- Update skill descriptions for better triggers
- Add rules to CLAUDE.md
- Adjust settings or permissions

Ask before making changes. Group related fixes when possible.
