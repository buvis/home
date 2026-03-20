# Decision Framework

Rules for classifying review findings as auto-fixable or requiring user escalation.

## Auto-fix (proceed without asking)

Proceed autonomously when ALL conditions hold:

| Condition | Examples |
|-----------|----------|
| Low severity, any consensus | Naming, style, minor cleanup |
| Medium severity, clear mechanical fix | Missing test, null check, import cleanup |
| Medium severity, 1/3 consensus | Single reviewer nit |
| Any severity where fix is additive only | Adding a test, adding validation at boundary |

**Additive-only test:** the fix only adds code or tests. It does not modify existing signatures, types, schemas, or public interfaces.

## Escalate (PAUSE, present to user)

PAUSE when ANY of these conditions hold:

| Condition | Examples |
|-----------|----------|
| Critical severity, always | Security, data loss, broken functionality |
| High + touches public API | Signature change, breaking change |
| High + data model change | Schema migration, type changes |
| Requirements ambiguity | PRD says X, code does Y, unclear which is right |
| New dependency needed | Package not in the project |
| Recurring issue | Same issue from previous cycle — fix didn't stick |
| >10 follow-up tasks | Single review produced too many issues |
| Cycle 3 reached | Hard stop regardless of severity |

## Classification Process

For each review finding:

1. Read severity from review output (emoji)
2. Check consensus level (3/3, 2/3, 1/3)
3. Determine fix type: additive-only vs modifying
4. Check against escalation triggers (ANY match = escalate)
5. If no escalation trigger matches, auto-fix

## Decision Logging

Every classification decision must be recorded in state:

- **Auto-fix:** add to `autonomous_decisions[]` with issue, severity, consensus, reason
- **Escalate:** add to `deferred_decisions[]` with issue, severity, consensus, reason, status=pending

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
