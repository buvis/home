# Attempt Logging

At every task exit — success in `SKILL.md` step 6, abort in step 4 (timeout / context exceeded / error after debug), or via the Subagent Dispatch Budget overrun path — append one entry to `state.tasks[i].attempts[]`. Under in-loop escalation (PRD 00065) a task can run at more than one rung: each rung that dispatched writes its own entry, at exit or when the task escalates away from it — see Cardinality below.

```json
{
  "attempt": <len(existing attempts) + 1>,
  "model": "<tier>",
  "outcome": "completed" | "aborted" | "escalated",
  "review_cycle": <int | null>,
  "cause": "<string | null>",
  "implementor": "claude" | "gemini" | "qwen",
  "preflight_outcome": "healthy" | "pi_missing" | "endpoint_unreachable" | "model_id_missing" | "completion_failed" | null,
  "pipeline": "minimal" | "lean" | "full",
  "escalation_reason": "gate_failure" | "review_flag" | null,
  "escalated_from": "qwen" | "haiku" | "sonnet" | "opus" | null,
  "diagnosis": "spec_gap" | "solid_spec" | null,
  "repair_used": true | null,
  "breaker_skipped": true | null,
  "qwen_gate_failed": true | null,
  "verification": "skipped:<cause>" | null,
  "red_check": "skipped:<cause>" | null,
  "self_deslop": "committed:<sha>" | "noop" | "skipped:trivial" | "timeout" | "errored:<cause>" | null,
  "review": "failed:<cause>" | null
}
```

**Cardinality (PRD 00065)**: today `/work` appends exactly one entry per task at exit. Under in-loop escalation the rule widens to one entry per rung/dispatch-group: each rung that dispatched writes its own entry when the task escalates away from it or exits on it. `attempt` numbers stay sequential across rungs (`len(existing)+1`). This is a widening, not a break — a task that never escalates still writes exactly one entry, byte-identical to today.

**Field semantics**:

- `attempt`: 1-indexed; `len(existing) + 1`.
- `model`: the tier `/work` used for this pass. Read from `task.metadata.model` when set. On legacy plans where `metadata.model` is absent, record the effective session-inherited tier as a string (e.g. `"sonnet"` for a Work-phase Sonnet 4.6 launch). Always a string — never `null`.
- `outcome`: `/work` writes `"completed"`, `"aborted"`, or `"escalated"`. The `"escalated"` value (PRD 00065) is stamped on the entry for a rung the task was reset away from and escalated up; the final rung's entry carries the real terminal outcome (`completed`/`aborted`), and the escalated-away entry keeps its true `implementor` (a qwen rung escalated to Sonnet keeps `implementor:"qwen"`). Later phases upgrade earlier entries — `/run-autopilot` Phase 6 (Rework) step 2 rewrites a `"completed"` entry's outcome to `"review_flagged"` at the start of escalation, then later rewrites a flagged entry's outcome to `"rework_failed"` when the rework pass also fails at the top of the chain.
- `review_cycle`: `null` on a first/Phase-3 attempt; set to the current `state.cycle` integer when the pass is a rework re-dispatch (see `SKILL.md` step 1.5 "Rework-mode task filter (PRD 00025)").
- `cause`: `null` on success; on abort, the reason — `"context_overrun"`, `"subagent_prompt_overrun"`, `"timeout"`, `"error"`, `"subagent_infra_failure"`, `"commit_rejected"` (a commit blocked by `validate_commit_msg`/warden that the one-retry repair could not fix — `SKILL.md` step 5).
- `implementor`: which agent actually ran the attempt — `"claude"` (Agent dispatch at any Claude tier, including a Claude fallback when qwen preflight failed), `"gemini"` (UI task via `use-gemini` helper), or `"qwen"` (backend qwen-eligible task with healthy preflight, dispatched via `use-qwen` helper). Sourced from the routing decision in `work` SKILL.md step 3 — the value reflects what dispatched, not what the routing table initially picked: a qwen-eligible task that preflight-failed and fell back to Claude records `"claude"`. **Multi-implementor pass (qwen → Claude retry):** when step 3 dispatches qwen and step 5.5 then fails and re-dispatches Claude Sonnet (per the one-shot qwen attempt budget), exactly one entry is appended at task exit. Record `implementor: "qwen"` — qwen DID dispatch and DID commit code at step 5 (commits precede the step-5.5 gate), so the qwen-implemented commit range remains in HEAD and the `_collect_qwen_task_ids` consumer of this field needs the qwen flag to scope the batched de-slop pass over it. The Sonnet retry's success is reflected by `outcome: "completed"`; the carve-out's existence is implicit (only qwen-routed tasks can produce a Sonnet retry of a qwen attempt). Tess / Devon / code reviewer dispatches do not write attempt entries themselves; this field labels the Ivan-implementor pass.
- `preflight_outcome`: only meaningful for attempts on qwen-eligible tasks (those with `task.metadata.qwen_eligible == true` at attempt start). For qwen-eligible attempts: one of `"healthy"`, `"pi_missing"`, `"endpoint_unreachable"`, `"model_id_missing"`, `"completion_failed"` — the verdict of the four-check probe defined in `references/qwen-integration.md` (Preflight section). For non-qwen-eligible attempts: `null`. Sourced from the preflight probe in `work` SKILL.md step 3.
- `pipeline`: which pipeline depth this attempt ran, keyed on the task tier (PRD 00044) — `"minimal"` (haiku: Tess + Ivan, 2 subagents), `"lean"` (sonnet: + step-5.7 reviewer, 3 subagents), or `"full"` (opus: + Devon at step 2.85, 4 subagents). Mapped from `task.metadata.model`: `haiku` → `"minimal"`, `sonnet` → `"lean"`, `opus` → `"full"`; absent/legacy `metadata.model` is treated as `sonnet` → `"lean"` (matching the step-2.85 and step-5.7 tier gates). Written at every task exit alongside `implementor`. A Phase-6 escalation to `opus` therefore records `"full"` for the rework attempt. Always a string — never `null`. **In-loop escalation (PRD 00065):** an escalation re-dispatches the implementor for the higher rung and re-runs the tier-appropriate post-implementor gates (step 5.7 reviewer for sonnet+, plus the step-5.5 gate); Devon (step 2.85, pre-implementation adversarial tests) is NOT re-run mid-task. So an in-loop opus escalation stamps `pipeline:"lean"` (implementor+reviewer), reserving `"full"` for a from-scratch opus task/rework that actually ran Devon.
- `escalation_reason` (PRD 00065): string?; `"gate_failure"` stamped directly by `/work` on the entry of the rung it escalated INTO (in-loop diagnosis). `"review_flag"` reaches the entry a different way: phase-review Phase 6 writes it (with `escalated_from`) into `task.metadata` via `TaskUpdate`, and `/work`'s attempt write copies both from `task.metadata` onto the rework entry (`SKILL.md` step 6 point 2 / step 1.5) — the metadata is the carrier, the copy is the wiring. Compound path: if that review-flagged rung then escalates in-loop, the copy happens at `SKILL.md` step 5.5 ESCALATE point 2 (onto the escalate-away entry) and `task.metadata`'s `escalation_reason`/`escalated_from` are cleared at point 3, so the higher in-loop rung records its own `gate_failure` (not a leaked `review_flag`). Absent = neither (legacy / no escalation).
- `escalated_from` (PRD 00065): string?; a tier (`"qwen"`|`"haiku"`|`"sonnet"`|`"opus"`) — on the entry of the rung escalated INTO, the immediate-prior rung it came from. Set directly by `/work` on the in-loop `gate_failure` path; carried from `task.metadata` (as above) on the `review_flag` path. Absent on non-escalated entries.
- `diagnosis` (PRD 00065): string?; `"spec_gap"`|`"solid_spec"` — the 2nd-failure diagnosis verdict, stamped on the entry of the rung that was diagnosed.
- `repair_used` (PRD 00065): bool?; `true` stamped on the entry of the same-tier attempt that ran after a task-description repair; absent otherwise (never written `false`).
- `breaker_skipped` (PRD 00065): bool?; `true` stamped on a qwen-eligible attempt the breaker rerouted to Claude at original tier (no preflight probe). Absent otherwise.
- `qwen_gate_failed` (PRD 00065): bool?; `true` stamped on an `implementor:"qwen"` entry whose step-5.5 gate FAILED — the durable signal the qwen capability breaker keys on. Absent otherwise.

**Best-effort gate stamps (fail-loud markers, PRD 00084 R2d)**: each records that a per-task gate was skipped or failed rather than passed, so a skipped check never reads as a passed one (`rules/operating-principles.md`). All optional — absent means the gate ran normally (or its tier-skip applied). They are pass-through markers: none blocks the task or changes `outcome`.

- `verification`: string?; `"skipped:<cause>"` when step 5.5's per-task test verification could not run (e.g. the build lock was contended and cargo was backgrounded — `SKILL.md` step 5.5 / the "test verification is blocked" rule). Absent when the task's tests ran.
- `red_check`: string?; `"skipped:<cause>"` when step 2.95's red-check could not run standalone (tests import the not-yet-built feature, or the runner cannot execute them). Absent when the red-check ran (saw red, or strengthened-then-red).
- `self_deslop`: string?; the step-5.6 self-deslop outcome — `"committed:<sha>"` (a `chore: prune slop` cleanup landed), `"noop"` (ran, no slop), `"skipped:trivial"` (skip rule fired — diff <30 net lines OR <2 files), `"timeout"` (watchdog killed it), or `"errored:<cause>"` (dispatch failed). Canonical shape mirrored in `run-autopilot/references/state-schema.md` `tasks[].attempts[].self_deslop`. Absent on legacy attempts.
- `review`: string?; `"failed:<cause>"` when the step-5.7 reviewer lane (Sonnet via `use-sonnet`) failed twice (runner unavailable, nonzero exit, or empty output). Absent when the review ran or its haiku tier-gate skipped it.

**Attribution row ownership (PRD 00065)**: under one-entry-per-rung, each field lands on a specific row — do not lump them all on one entry:

| Field | Row it is stamped on |
|-------|----------------------|
| `diagnosis` | the diagnosed (lower) rung's entry |
| `qwen_gate_failed` | the qwen (lower) rung's entry |
| `repair_used` | the entry of the same-tier attempt that ran after a repair (that rung's entry) |
| `escalation_reason:"gate_failure"` | the rung escalated INTO (higher)'s entry |
| `escalated_from` | the rung escalated INTO (higher)'s entry |

**Append procedure**: append the entry with `statectl` — `python3 ~/.claude/skills/run-autopilot/scripts/statectl.py <state.json> append tasks[i].attempts '<entry-json>'` — where `i` is this task's index in `state.tasks` and `<entry-json>` is the object above. `statectl append` creates the array if absent, appends under an advisory lock, and replaces the file atomically while preserving every sibling field, so the manual read-modify-write is gone (`run-autopilot` SKILL.md § State Management). Resolve `<state.json>` by walking up from the resolved physical cwd to find the autopilot dir, same pattern as the cap-marker reset in `SKILL.md` step 2.

Two top-level fields, `qwen_gate_failures_consecutive` and `qwen_breaker`, track the qwen capability breaker across the batch (PRD 00065); see `run-autopilot/references/state-schema.md` Field Descriptions for their canonical shape.

Cross-reference: `run-autopilot/references/state-schema.md` `tasks[].attempts` row defines the canonical shape.
