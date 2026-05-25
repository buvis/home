---
name: review-blindly
description: Use when a major implementation is complete and all per-task reviews have passed, before finishing-a-development-branch. Mandatory after multi-file features and plan execution. Not for single-file fixes or refactors.
---

# Blind Review

Dispatch a review agent that receives ONLY the original spec. A reviewer who knows nothing about the implementation catches spec drift, security gaps, and race conditions that implementation-aware reviewers miss.

**Announce at start:** "I'm using the blind-review skill to validate this implementation against the spec."

## The Process

### Step 1: Gather the Spec and Rubric

Extract the original requirements. This is the ONLY narrative context the reviewer gets.

**Do NOT include:** implementation summaries, file lists, notes about how it was built, implementer's self-review.

Also load the numbered blind-review rubric from `references/rubric.md`. Its contents will be embedded inline into the reviewer's prompt (see Step 2). The rubric is spec-only by design — it does NOT introduce implementation context. Inline embedding (not a file reference) is REQUIRED because the blind reviewer is dispatched with a self-contained prompt and cannot resolve relative paths.

### Step 2: Dispatch Blind Reviewer

Pin the reviewer to Sonnet for model diversity — different family from the typical Opus implementer breaks shared priors and gives you actual independence rather than narrative-only blindness.

```text
Task tool (general-purpose):
  model: "sonnet"
  description: "Blind spec review for [feature name]"
  prompt: |
    You are a hostile auditor reviewing code you've never seen before.
    You know ONLY what was supposed to be built. You must find the code,
    read it, and determine if it does what the spec says.

    ## The Specification

    [PASTE FULL SPEC/REQUIREMENTS — NOTHING ELSE]

    ## The Rubric (binary pass/fail rules, spec-only)

    # Review-Blindly Rubric

    This rubric provides binary pass/fail criteria for the spec-only hostile audit performed by the review-blindly skill. The reviewer's prompt contains ONLY the PRD — no diff, no file list, no implementation summary, no implementer self-review. The reviewer must independently locate and read the relevant code to evaluate each rule against the spec.

    ## Rules

    ### Spec Compliance

    R1: The implementation satisfies all specified behaviors and outputs described in the PRD.

    R2: All stated data formats and structures in the PRD are preserved in the implementation.

    R3: Every API endpoint or interface specified in the PRD is implemented with the correct signature and behavior.

    R4: All stated performance requirements and constraints from the PRD are met.

    R5: The implementation matches all specified error handling behaviors and status codes.

    ### Scope Creep

    R6: No new functionality or features beyond those explicitly specified in the PRD are present.

    R7: No additional parameters, options, or flags are added beyond those in the PRD.

    R8: No new external dependencies or libraries are introduced beyond those specified.

    ### Security

    R9: All specified authentication mechanisms from the PRD are implemented and enforced.

    R10: Required input validation and sanitization are present as specified in the PRD.

    R11: Any specified rate-limiting or throttling controls are implemented as described.

    ### Data Safety

    R12: No destructive operations (delete, update, etc.) are performed without proper safeguards.

    R13: All data migrations include rollback or reversal mechanisms as specified.

    R14: No unguarded database queries or file operations are present in the implementation.

    ### Acceptance Criteria

    R15: All acceptance criteria for Phase 1 tasks are satisfied in the implementation.

    R16: All acceptance criteria for Phase 2 tasks are satisfied in the implementation.

    R17: All acceptance criteria for Phase 3 tasks are satisfied in the implementation.

    ### Out-of-Scope

    R18: All items explicitly marked as out-of-scope in the PRD are absent from the implementation.

    R19: No features or functionality mentioned in the PRD as out-of-scope are present in the diff.

    ## Your Job

    Read the actual codebase and verify against the spec above.
    You have NO implementation context. Find the code yourself.

    **Check for:**

    1. **Spec compliance** — Every requirement implemented? Anything
       extra? Requirements misinterpreted?

    2. **Security and deployment readiness** — Secrets with empty
       defaults? Missing auth checks? Fail-open paths? Race conditions
       (check-then-act)?

    3. **Data safety** — Backward compatibility? Migration paths?
       Malformed/missing data handling?

    4. **Missing error paths** — Token expiry, network failure, partial
       writes? Retry and recovery?

    **IMPORTANT: If you cannot find implementation files, you MUST still
    produce a full report.** Enumerate every spec requirement, flag every
    security concern derivable from the spec. "Code not found" is a
    Critical finding, not a reason to stop.

    **Report format:**
    - Critical: Must fix before merge (security, data loss, spec violations)
    - Important: Should fix (missing error handling, race conditions)
    - Minor: Nice to fix (style, naming)
    - Spec compliance: ✅ Met / ❌ Not met — line-by-line breakdown
    - Spec-derived risks: Concerns to verify in code

    **PER-RULE VERDICTS ARE MANDATORY.** For every rule in The Rubric above, emit one line in this exact shape:
    ```
    R{n}: pass
    ```
    or
    ```
    R{n}: fail
    ```
    One rule per line, no other text on the line, no rationale. Answer every rule — a rule you cannot evaluate (insufficient context, no implementation found, etc.) counts as `fail`; never omit the line. Rule IDs are stable; do not renumber.
```

### Step 3: Act on Findings

- **Critical:** Fix immediately, re-run blind review on affected areas
- **Important:** Fix before merge
- **Minor:** Fix or note for follow-up
- Zero issues found? Be suspicious — verify the reviewer actually read code (check for file:line references)

## Integration

```text
subagent-driven-development: Per-task reviews → All tasks done → BLIND REVIEW → finishing-a-development-branch
executing-plans:             All batches done → BLIND REVIEW → finishing-a-development-branch
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Including implementation context | Spec only — let reviewer find code independently |
| Skipping because per-task reviews passed | Per-task reviews catch different bugs than whole-spec review |
| Trusting "zero issues" result | Verify reviewer read the code (check for file references) |
| Short-circuiting on "code not found" | Still enumerate every spec requirement and flag spec-derived risks |
| Cutting corners under time pressure | "Merge today" is not a reason for a "quick review" |

## Red Flags

**Never:** give the reviewer implementation context, skip because standard reviews passed, merge with unresolved Critical findings, do a "quick" blind review under time pressure, stop because files weren't found.

**Always:** provide only the spec, let the reviewer find code independently, enumerate spec-derived risks before reading code, fix Critical/Important before merge, re-review after significant fixes.
