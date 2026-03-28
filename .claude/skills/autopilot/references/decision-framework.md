# Decision Framework

Rules for classifying review findings as auto-fixable, research-then-decide, or requiring user escalation.

## Auto-fix (proceed without asking)

Proceed autonomously when ALL conditions hold:

| Condition | Examples |
|-----------|----------|
| Low severity, any consensus | Naming, style, minor cleanup |
| Medium severity, clear mechanical fix | Missing test, null check, import cleanup |
| Medium severity, 1/3 consensus | Single reviewer nit |
| Any severity where fix is additive only | Adding a test, adding validation at boundary |

**Additive-only test:** the fix only adds code or tests. It does not modify existing signatures, types, schemas, or public interfaces.

## Research-then-decide (conditional autonomy)

These issues were previously always escalated. Now: run a research protocol, auto-proceed if all checks pass, escalate if any check fails.

| Condition | Protocol | Auto-proceed if ALL pass | Escalate if ANY fail |
|-----------|----------|--------------------------|----------------------|
| New dependency needed | Protocol A | Compatible license, maintained, no CVEs, established | Incompatible/unclear license, abandoned, CVEs, niche |
| Recurring issue | Protocol B | Root cause found, different approach available, <3 recurrences | Root cause unclear, no alternative, 3rd+ recurrence |
| High + data model change | Protocol C | PRD explicitly specifies schema AND implementation matches | PRD silent on schema, or implementation diverges |
| High + public API | Protocol D | PRD requires change AND (internal-only OR PRD specifies signature) | External-facing without PRD signature, or not PRD-driven |

### Protocol A: New dependency

1. Identify package name and registry (npm, PyPI, crates.io, etc.)
2. **License:** read package metadata or LICENSE file. Must be OSI-approved and compatible with project license (check project root for LICENSE, package.json, Cargo.toml, etc.)
3. **Maintenance:** check repository via registry link or `WebSearch`. Last commit must be within 6 months. Issues/PRs should show activity.
4. **Security:** search `"<package> CVE"` or check registry advisories. No open critical or high CVEs.
5. **Adoption:** check download counts. Well-known = >10k weekly downloads (npm) or equivalent, OR commonly referenced in ecosystem docs.
6. Record each check. ALL must pass.

### Protocol B: Recurring issue

1. Read `review_cycles[].recurring_issues` and `autonomous_decisions[]` from state to find what was tried before.
2. Compare previous fix with current state. Identify why the fix didn't hold (wrong root cause? partial fix? reverted by later work?).
3. Determine if a fundamentally different approach exists (not just retrying the same fix).
4. Check recurrence count: 3rd+ time = escalate unconditionally.
5. Record: previous fix, root cause analysis, proposed new approach, recurrence count. ALL of: root cause identified, alternative available, count < 3 must hold.

### Protocol C: High + data model change

1. Read the PRD file (path from `state.prd.path`).
2. Search for explicit mention of schema, data model, database, type definition, or migration related to this finding.
3. Compare proposed implementation against PRD specification.
4. Record: relevant PRD excerpt (or "not found"), match assessment. BOTH explicit PRD mention AND implementation match must hold.

### Protocol D: High + public API

1. Read the PRD file.
2. Search for explicit mention of the API endpoint, function signature, or interface change.
3. Determine API scope: internal-only (used within project, not exposed to external consumers) or external-facing (documented public API, SDK surface, REST endpoint used by third parties).
4. Record: PRD excerpt, scope determination, match assessment. PRD must require the change AND either (internal-only) OR (PRD specifies exact new signature).

### Research tool requirements

- Protocols A needs `WebSearch`/`WebFetch`. If unavailable, skip research and escalate with check `{"check": "tools-unavailable", "result": "WebSearch not available", "pass": false}`.
- Protocols B, C, D use only local file reads - always available.
- Each protocol should complete in 1-3 tool calls. Don't deep-audit - quick checks.

## Defer to batch end (log, don't PAUSE)

Log and continue when ANY of these conditions hold:

| Condition | Examples |
|-----------|----------|
| Critical severity, always | Security, data loss, broken functionality |
| Requirements ambiguity | PRD says X, code does Y, unclear which is right |
| Research-failed items | Verdict "escalate" from research protocols |

## PAUSE (present to user, block progress)

PAUSE when ANY of these conditions hold:

| Condition | Examples |
|-----------|----------|
| >10 follow-up tasks | Single review produced too many issues |
| Cycle 3 reached | Hard stop regardless of severity |
| Decision blocks subsequent tasks | API shape needed before frontend can proceed |
| Data model choice all remaining work depends on | "If wrong, most work gets thrown out" |

## Classification Process

For each review finding:

1. Read severity from review output (emoji)
2. Check consensus level (3/3, 2/3, 1/3)
3. Determine fix type: additive-only vs modifying
4. Check against PAUSE triggers (>10 tasks, Cycle 3, blocking decision, foundational data model) - ANY match = PAUSE immediately
5. Check against defer-to-batch-end triggers (Critical, Requirements ambiguity) - ANY match = log to deferred, continue
6. Check against research-then-decide triggers (New dependency, Recurring issue, High + data model, High + public API) - ANY match = run corresponding protocol
7. If research verdict is "proceed", treat as auto-fix
8. If research verdict is "escalate", defer to batch end
9. If no trigger matches, check auto-fix criteria. If met, auto-fix. Otherwise, defer to batch end as safety default.

## Decision Logging

Every classification decision must be recorded in state:

- **Auto-fix (no research):** add to `autonomous_decisions[]` with `issue`, `severity`, `consensus`, `action`, `reason`
- **Auto-fix (research-backed):** add to `autonomous_decisions[]` with same fields plus `research` field containing category, verdict, checks, evidence_summary
- **Escalate (research-backed):** add to `deferred_decisions[]` with `issue`, `severity`, `consensus`, `reason`, `status`, plus `research` field
- **Escalate (no research):** add to `deferred_decisions[]` with `issue`, `severity`, `consensus`, `reason`, `status`

## Presenting Escalated Issues

When pausing for user input, present each escalated issue as:

```
{severity emoji} [{consensus}] {issue description}
  File: {path}
  Why escalated: {reason from escalation table}
  Options:
    1. Fix it (describe the fix)
    2. Skip / won't fix
    3. Defer to later
```

Wait for user decision on each before continuing.
