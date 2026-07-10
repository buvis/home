---
name: debug-stuck-agent
description: Use when an agent is failing repeatedly, looping on tools, drifting from the task, or burning tokens without progress. Triggers on "agent introspection", "debug agent", "agent stuck", "agent loop", "diagnose failure", "why is this stuck".
---

# Debug Stuck Agent

A workflow skill, not a hidden runtime: it teaches the agent to debug itself
systematically before escalating to a human.

## Scope Boundaries

Activate this skill for:
- maximum tool call / loop-limit failures, or repeated retries with no forward progress
- context growth or prompt drift that starts degrading output quality
- file-system or environment state mismatch between expectation and reality
- tool failures likely recoverable with diagnosis and a smaller corrective action

Do not use this skill as the primary source for:
- feature verification after code changes; use `review-work-completion` or `review-blindly`
- framework-specific debugging when a narrower skill already exists
- runtime promises the current harness cannot enforce automatically

## Four-Phase Loop

### Phase 1: Failure Capture

Before trying to recover, record the failure precisely — fill every field of
the "Failure Capture" template in `references/capture-templates.md` (error,
last tool sequence, goal in progress, context pressure, environment
assumptions).

### Phase 2: Root-Cause Diagnosis

Match the failure to a known pattern before changing anything.

| Pattern | Likely Cause | Check |
| --- | --- | --- |
| Maximum tool calls / repeated same command | loop or no-exit observer path | inspect the last N tool calls for repetition |
| Context overflow / degraded reasoning | unbounded notes, repeated plans, oversized logs | inspect recent context for duplication and low-signal bulk |
| `ECONNREFUSED` / timeout | service unavailable or wrong port | verify service health, URL, and port assumptions |
| `429` / quota exhaustion | retry storm or missing backoff | count repeated calls and inspect retry spacing |
| file missing after write / stale diff | race, wrong cwd, or branch drift | re-check path, cwd, git status, and actual file existence |
| tests still failing after "fix" | wrong hypothesis | isolate the exact failing test and re-derive the bug |

Diagnosis questions:
- is this a logic failure, state failure, environment failure, or policy failure?
- did the agent lose the real objective and start optimizing the wrong subtask?
- is the failure deterministic or transient?
- what is the smallest reversible action that would validate the diagnosis?

### Phase 3: Contained Recovery

Recover with the smallest action that changes the diagnosis surface
(checklist: "Recovery Action" in `references/capture-templates.md`).

Safe recovery actions:
- stop repeated retries and restate the hypothesis
- trim low-signal context and keep only the active goal, blockers, and evidence
- re-check the actual filesystem / branch / process state
- narrow the task to one failing command, one file, or one test
- switch from speculative reasoning to direct observation
- escalate to a human when the failure is high-risk or externally blocked

Do not claim unsupported auto-healing actions like "reset agent state" or "update harness config" unless you are actually doing them through real tools in the current environment.

### Phase 4: Introspection Report

End with a report that makes the recovery legible to the next agent or human
(template: "Agent Self-Debug Report" in `references/capture-templates.md`).
Never end with "I fixed it" alone — the filled report is the deliverable.

## Recovery Heuristics

Prefer these interventions in order:

1. Restate the real objective in one sentence.
2. Verify the world state instead of trusting memory.
3. Shrink the failing scope.
4. Run one discriminating check.
5. Only then retry.

Bad pattern: retrying the same action three times with slightly different
wording. Good pattern: capture → classify → one direct check → change the
plan only if the check supports it.

## Related Skills

- `review-work-completion` after recovery if code was changed
- `convene-council` when the issue is decision ambiguity, not technical failure
- `resolve-git-conflicts` when the failure came from conflicting local state
- `catchup` if the failure came from missing project context
