---
name: audit-security
description: Scan ~/.claude/ config for security anti-patterns (permissive permissions, hook injection, risky MCP configs, hardcoded secrets). Triggers on "audit security", "security audit", "check config security", "scan for vulnerabilities", "security check".
---

# Audit Security

Static security scan of `~/.claude/` configuration files.

## Step 1: Run scanner

```bash
python3 ~/.claude/skills/audit-security/scripts/scan.py
```

## Step 2: Parse and present results

Parse the JSON output. If `findings` is empty, report:

```
Security audit: clean. No issues found.
```

If findings exist, present grouped by severity (critical first):

```
SECURITY AUDIT RESULTS
======================

CRITICAL ({count}):

  1. {file}:{line} — {description}
     Fix: {fix}

HIGH ({count}):

  1. {file}:{line} — {description}
     Fix: {fix}

MEDIUM ({count}):

  1. {file}:{line} — {description}
     Fix: {fix}

Summary: {critical} critical, {high} high, {medium} medium
```

Omit severity sections with zero findings.

## Step 3: Offer remediation

For critical and high findings, ask if the user wants help fixing them. For medium findings, note they may be intentional (e.g. `2>/dev/null` in notification hooks is often acceptable).
