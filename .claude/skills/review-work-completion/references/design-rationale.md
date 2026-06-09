# Design Rationale

Settled decisions. Do not suggest changes to these patterns during reviews.

## Agent Abstraction (Alice/Bob/Carl)

Human names decouple workflow from tool names. Tools change; review process doesn't. Enables swapping implementations without rewriting skill. Names make logs readable.

## Task Agent Wrapping + Temp Files

Required for context isolation. Direct invocation would pollute context. The indirection is the feature, not overhead.

## Skill Dependencies (use-codex, use-gemini)

Intentionally reusable. These skills are shared across multiple workflows (e.g., `work` skill). DRY principle — don't inline what's already abstracted.

## Review Dimensions Checklist

Not generic — experience-driven. LLMs consistently miss these items without explicit prompting. The checklist exists because failures happened without it.

## Strict Output Format

LLMs must follow format instructions. If they can't, that's a model problem, not a skill problem. Structured output enables reliable parsing and consolidation.

## Branch Detection Logic

Explicit script handles edge cases that prose instructions miss. "Diff against master" fails when master doesn't exist, remote isn't configured, or branch naming varies.

## `dev/local/` Directory Structure

Prerequisite, not assumption. This skill operates within a defined workflow that guarantees the structure exists. Not meant for arbitrary projects.

## Optional Skill Invocations (catchup)

Failsafe pattern. Graceful degradation if unavailable. Minimal impact on core workflow.

## This File (design-rationale.md)

Exists to prevent repeated reviewer feedback on settled design decisions. Skill-creator guidelines discourage auxiliary files, but this file pays for itself by short-circuiting review cycles. The callout in SKILL.md directs skill reviewers here before suggesting changes.

## Dependency Discovery via Prerequisites

Dependencies (use-codex, use-gemini, catchup) are validated at runtime in step 1, not listed separately. Duplicating dependency info would create maintenance burden. Step 1's prerequisite checks ARE the dependency documentation — executable and always accurate.

## Cross-Reference Pattern (Single Source of Truth)

Multiple files reference output-formats.md rather than inlining formats. This creates indirection but ensures consistency. The alternative — inlining formats at point-of-use — caused drift in earlier iterations. One authoritative location beats convenient but divergent copies.

## Hardcoded Skill Dependency Paths

Paths like `~/.claude/skills/use-codex/scripts/codex-run.sh` are intentionally hardcoded. This skill operates within a defined ecosystem where these paths are guaranteed. Dynamic resolution would add complexity without benefit.

## Separate review-dimensions.md

Kept separate despite being always-loaded. The checklist will grow as new review blind spots are discovered. Separation makes iterating on dimensions independent of workflow changes.

## Same-Family Reviewers (Alice + Diana)

Alice (Opus) and Diana (Sonnet) both use Claude models but reason differently. Sonnet is faster, less verbose, and sometimes catches patterns Opus overthinks. Consensus between same-family models may correlate more than cross-family, but practical value justifies inclusion. If same-family correlation inflates consensus scores, adjust weighting later - don't prematurely optimize.

## Dynamic Agent Count

Consolidation accepts any number of NAME:FILE pairs. Consensus scales with active agent count (Full = N/N, Majority = >50%, Minority = <=50%). Adding, removing, or disabling agents requires no script changes. Carl (Gemini) is the clearest case: he runs as a fourth agent when the Gemini CLI is available and is simply omitted from the pair list when it is not.

## Incremental Reviews on Rework Cycles

Cycle 1 reviews the full PRD diff against the branch base. Cycle 2+ (rework cycles) scope the diff to commits since the previous cycle's `head_sha`, and hand reviewers the prior findings to verify. This is deliberate, not a coverage gap: re-running every reviewer over the entire branch diff every cycle is the dominant token cost of a multi-cycle PRD, and the unchanged code was already reviewed in cycle 1. Coverage is preserved — prior findings are explicitly re-checked, the scoped diff catches rework regressions, and (under autopilot) blind review and doubt review still examine the whole result. Do not "fix" this back to a full diff every cycle.
