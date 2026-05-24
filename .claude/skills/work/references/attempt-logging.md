# Attempt Logging

At every task exit — success in `SKILL.md` step 6, abort in step 4 (timeout / context exceeded / error after debug), or via the Subagent Dispatch Budget overrun path — append one entry to `state.tasks[i].attempts[]`:

```json
{
  "attempt": <len(existing attempts) + 1>,
  "model": "<tier>",
  "outcome": "completed" | "aborted",
  "review_cycle": <int | null>,
  "cause": "<string | null>",
  "implementor": "claude" | "gemini" | "qwen",
  "preflight_outcome": "healthy" | "pi_missing" | "endpoint_unreachable" | "model_id_missing" | null
}
```

**Field semantics**:

- `attempt`: 1-indexed; `len(existing) + 1`.
- `model`: the tier `/work` used for this pass. Read from `task.metadata.model` when set. On legacy plans where `metadata.model` is absent, record the effective session-inherited tier as a string (e.g. `"sonnet"` for a Work-phase Sonnet 4.6 launch). Always a string — never `null`.
- `outcome`: `/work` writes only `"completed"` or `"aborted"`. Later phases upgrade earlier entries — `/run-autopilot` Phase 6 (Rework) step 2 rewrites a `"completed"` entry's outcome to `"review_flagged"` at the start of escalation, then later rewrites a flagged entry's outcome to `"rework_failed"` when the rework pass also fails at the top of the chain.
- `review_cycle`: `null` on a first/Phase-3 attempt; set to the current `state.cycle` integer when the pass is a rework re-dispatch (see `SKILL.md` step 1.5 "Rework-mode task filter (PRD 00025)").
- `cause`: `null` on success; on abort, the reason — `"context_overrun"`, `"subagent_prompt_overrun"`, `"timeout"`, `"error"`, `"subagent_infra_failure"`.
- `implementor`: which agent actually ran the attempt — `"claude"` (Agent dispatch at any Claude tier, including a Claude fallback when qwen preflight failed), `"gemini"` (UI task via `use-gemini` helper), or `"qwen"` (backend qwen-eligible task with healthy preflight, dispatched via `use-qwen` helper). Sourced from the routing decision in `work` SKILL.md step 3 — the value reflects what dispatched, not what the routing table initially picked: a qwen-eligible task that preflight-failed and fell back to Claude records `"claude"`. **Multi-implementor pass (qwen → Claude retry):** when step 3 dispatches qwen and step 5.5 then fails and re-dispatches Claude Sonnet (per the one-shot qwen attempt budget), exactly one entry is appended at task exit. Record `implementor: "qwen"` — qwen DID dispatch and DID commit code at step 5 (commits precede the step-5.5 gate), so the qwen-implemented commit range remains in HEAD and the `_collect_qwen_task_ids` consumer of this field needs the qwen flag to scope the batched de-slop pass over it. The Sonnet retry's success is reflected by `outcome: "completed"`; the carve-out's existence is implicit (only qwen-routed tasks can produce a Sonnet retry of a qwen attempt). Tess / Devon / code reviewer dispatches do not write attempt entries themselves; this field labels the Ivan-implementor pass.
- `preflight_outcome`: only meaningful for attempts on qwen-eligible tasks (those with `task.metadata.qwen_eligible == true` at attempt start). For qwen-eligible attempts: one of `"healthy"`, `"pi_missing"`, `"endpoint_unreachable"`, `"model_id_missing"` — the verdict of the three-check probe defined in `references/qwen-integration.md` (Preflight section). For non-qwen-eligible attempts: `null`. Sourced from the preflight probe in `work` SKILL.md step 3.

**Write procedure**: read `state.json`, append to `tasks[i].attempts[]` (create the array if absent), write back atomically. Merge — do not replace siblings. Walk up from the resolved physical cwd to find the autopilot dir, same pattern as the cap-marker reset in `SKILL.md` step 2.

Cross-reference: `run-autopilot/references/state-schema.md` `tasks[].attempts` row defines the canonical shape.
