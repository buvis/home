---
name: spike
description: Use when an idea is too fuzzy to spec confidently and a throwaway build would answer faster than more spec work - runs before elicit-requirements or create-prd. Triggers on "spike", "spike this", "prototype this idea", "throwaway prototype".
---

# Spike

Build-first discovery. The spec is a guess; the throwaway build is the elicitation device. Iterate attended until the contract is real, then graduate to a PRD. Nothing built here ships.

## Loop

### 1. Rough spec (10 minutes, no polish)

Write `dev/local/spikes/<slug>/SPEC.md` (Write tool, never shell redirects):

- The user's idea, verbatim
- The smallest outcome that would demonstrate it end-to-end
- Guessed contract (inputs, outputs, interfaces) - mark each guess `(guess)`

If the user gave only a phrase, ask at most one question, then guess the rest. Wrong guesses are the point - the build exposes them.

### 2. Throwaway build (about 20 minutes of work)

Build the smallest thing that demonstrates the idea end-to-end, directly in this session - no implementor dispatch, no TDD ceremony:

- Standalone idea: build inside `dev/local/spikes/<slug>/`
- Change to existing code: work on branch `spike/<slug>` (worktree if the working tree is dirty); never the current branch
- Sandbox only: never touch production data, live services, or anything irreversible. Input validation at real trust boundaries stays; tests, changelog, review, and production-ready rules are suspended - this code is disposable by contract
- Timebox: if it will not demonstrate in about an hour of effort, stop and report; the idea is not spike-sized - take the open questions to elicit-requirements instead

### 3. Report

Show, in this order:

1. What got built and how to run it (2-3 lines plus the run command)
2. `ASSUMPTIONS:` one line per choice made where SPEC.md was silent
3. `OPEN QUESTIONS:` what the build surfaced that the spec must now answer

### 4. Decide

AskUserQuestion with exactly these three: **Refine and re-spike** (fold the answers into SPEC.md, rebuild in place, back to step 2), **Graduate** (step 5), **Discard** (delete the spike dir or branch, done). Never chain refine cycles without the user - the attended examine step is the value.

### 5. Graduate

Invoke create-prd with SPEC.md plus the final assumptions and answers. The PRD contract records observed prototype behavior, not the original guesses. Note in the PRD context that the spike exists at `dev/local/spikes/<slug>/` (or branch `spike/<slug>`) as reference.

The real implementation goes through the normal pipeline (plan-tasks, work, full review) and rebuilds from scratch - spike code never merges. Delete the spike once the PRD's implementation lands.
