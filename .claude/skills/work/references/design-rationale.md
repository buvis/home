# Design Rationale (incident history)

The WHY behind the work skill's load-bearing rules. The rules live in
`SKILL.md` where they are enforced; this file holds the incident stories and
design arguments. Nothing here is normative — if a statement here contradicts
`SKILL.md`, `SKILL.md` wins.

## Per-task routing has no session memory (2026-06-09, ddb)

On a 9-task ddb batch, all nine tasks were `qwen_eligible: true` with healthy
qwen infra. Task 1 correctly routed to qwen; tasks 2-9 then silently went to
Claude with **no preflight recorded** — the session had generalized a routing
decision ("qwen was used already") instead of re-running the table per task.
Zero-cost local capacity sat idle for 8/9 tasks. Hence step 3's rule: re-run
the routing table for EVERY claimed task, and self-check before each Ivan
dispatch that a Claude dispatch on a `qwen_eligible` task carries a
non-`"healthy"` `preflight_outcome` justifying the fallback.

## Parallel rework is capped at 2 agents (2026-06-25 RAM lockout)

An uncapped 3-way parallel cargo rework fan-out (18 rustc jobs each) exhausted
48 GB of RAM, triggered jetsam, logged the user out, and locked the machine.
Parallel agents share one working tree and one build lock, so their compiles
serialize anyway — but each `cargo` invocation still spawns a full `rustc`
fleet. The caps in "Parallel dispatch for independent rework fixes" (max 2
agents, never raise `CARGO_BUILD_JOBS`/`--jobs`, no full-workspace builds
inside a parallel agent) bound that fleet; the global `~/.cargo/config.toml`
`[build] jobs` cap is the backstop.

## Why self-deslop is a fresh dispatch, not an Ivan prompt extension

Ivan's prompt already injects the code-quality rules block. Adding "after
passing tests, prune your diff" to the same prompt is cheap but ineffective:
same model + same session + "this is my work" attachment defeats slop
detection — empirically, models defend their own output. A separate dispatch
with task-as-external framing breaks that loop while staying at the same tier
budget (step 5.6 dispatches at `task.metadata.model`).

## Why the infrastructure circuit breaker exists (step 4.2)

Two back-to-back infrastructure failures (lost result / watchdog-killed hang)
on the same task, silently re-dispatched in a loop, caused a multi-hour stall.
One re-dispatch is recovery; a second failure on the same task is a pattern —
stop and escalate with `stall_reason: subagent_infra_failure`.

## Why the pipeline is tier-gated (PRD 00044)

Devon (adversarial test validation, step 2.85) is the most expensive
quality-gate dispatch and pays off on the hardest tasks — so only `opus`-tier
tasks run it. Per-task code review (step 5.7) is skipped only on `haiku`-tier
tasks: cheap mechanical tasks rely on per-task test verification plus the
PRD-level review lenses (consensus, blind, doubt — every review cycle), which
review every task's diff regardless of tier. Escalation restores depth
automatically: when the review gate escalates a task to `opus`, the rework
attempt regains Devon with no extra mechanism. Tier source: `metadata.model`
set by `/plan-tasks` (PRD 00025), escalated by the review gate's Phase 6.

## Why qwen gets exactly one shot per task (PRD 00031)

The local qwen lane exists for zero-token-cost wins on small backend tasks the
test gate keeps honest. A qwen attempt that fails its tests has already spent
the cheap try; retrying qwen risks a loop on a model that plainly wasn't up to
the task, so the step-5.5 re-dispatch escalates straight to Claude Sonnet and
the remaining retry budget runs entirely on Claude. The qwen attempt does not
consume a step-5.5 retry slot — it consumed the single qwen attempt.

## Why per-task verification stays narrow

Per-task full-suite runs compound to 40+ minutes of redundant test time across
a 20-task phase, so step 5.5 runs only the tests Tess wrote for the task and
the full suite (workspace tests, smoke, integration, lint) runs exactly once
in step 7.
