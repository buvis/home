---
name: audit-claude-config
description: Use when performing a Claude Code health check or reviewing setup quality. Triggers on "audit claude config", "full audit", "health check", "audit everything", "check my setup".
---

# Audit Claude Config

Orchestrate all audit skills into a unified health dashboard with prioritized remediation plans.

## Arguments

Parse the optional argument to select which audits to run:

| Argument | Audits included |
|----------|----------------|
| *(none)* | All audits including /doctor |
| `quick` | All except audit-sessions (slow) |
| `security` | audit-security, audit-permissions, audit-hooks, warden:audit |
| `health` | /doctor, audit-mcp-health, audit-plugins, audit-project-orphans, audit-settings, audit-memory, audit-skills |
| `efficiency` | audit-context, audit-rules, audit-sessions |

## Audit Registry

Run audits in this order (fast first, slow last):

1. `/doctor` (built-in) - health - fast
2. `/audit-context` - efficiency - fast
3. `/audit-security` - security - fast
4. `/warden:review-decisions` - security - fast
5. `/audit-permissions` - security - fast
6. `/audit-hooks` - health - fast
7. `/audit-plugins` - health - fast
8. `/audit-project-orphans` - health - fast
9. `/audit-mcp-health` - health - medium
10. `/audit-memory` - health - medium
11. `/audit-rules` - efficiency - medium
12. `/audit-settings` - health - medium
13. `/audit-skills` - health - medium
14. `/audit-sessions` - efficiency - slow

## Execution

### Step 1: Run /doctor

Run the built-in `/doctor` command first. Record its output. If /doctor reports critical issues (authentication failures, disconnected services), note these but continue with the remaining audits.

### Step 2: Run each audit skill

For each audit in the filtered registry:

1. Invoke via the Skill tool: `Skill(skill: "<audit-name>")`
2. After the skill completes, record:
   - **Status**: PASS (no actionable findings), WARN (has findings), INFO (suggestions only), FAIL (audit itself errored)
   - **Finding count**: Number of distinct findings
   - **Critical count**: Number of CRITICAL severity findings
   - **Findings list**: Each finding as `{severity, title, details}`

If a skill errors or is unavailable, record status as FAIL and continue.

### Step 3: Build dashboard

Print the dashboard table:

```
CLAUDE CODE HEALTH DASHBOARD
=============================
Date: {today}

Audit                    Status    Findings    Critical
─────────────────────────────────────────────────────────
{rows sorted by registry order}
─────────────────────────────────────────────────────────
OVERALL                  {worst}   {total}     {total_crit}
```

Overall status = worst status across all audits (FAIL > WARN > INFO > PASS).

### Step 4: Build remediation plans

Collect all findings across audits. Sort by severity: CRITICAL > HIGH > MEDIUM > LOW.

For each finding, generate a remediation block:

```
N. [{audit name}] {title}
   What:   {specific change}
   Where:  {exact file path and line if possible}
   Why:    {impact of not fixing}
   How:    {step-by-step fix or ready-to-apply command}
   Effort: {trivial / 5min / 30min / 1hr+}
```

To generate accurate remediation plans, read the relevant files mentioned in findings to provide exact locations and ready-to-apply fixes. Do not guess file contents.

Group by severity with headers:

```
━━━ CRITICAL (fix now) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
━━━ HIGH (fix this week) ━━━━━━━━━━━━━━━━━━━━━━━━━━
━━━ MEDIUM (fix when convenient) ━━━━━━━━━━━━━━━━━━
━━━ LOW (backlog) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Step 5: Save report

Save the full report to `dev/local/audit-results/{YYYY-MM-DD}.md` using the Write tool. Include:
- Dashboard table
- All remediation plans
- Summary line: `{total} findings: {crit} critical, {high} high, {med} medium, {low} low`

If a previous report exists in `dev/local/audit-results/`, compare and note:
- New findings (not in previous report)
- Resolved findings (in previous but not current)
- Unchanged findings (still present)

### Step 6: Offer next steps

After presenting the report:

- If CRITICAL findings exist: "Fix critical issues now?"
- If any finding has effort > 1hr: "Create PRD for {finding}?"
- If no findings: "Setup is clean. Consider scheduling periodic audits with `/schedule`."
