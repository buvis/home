# State Schema

State file location: `dev/local/autopilot/state.json`

## Schema

```json
{
  "prd": "00004-feature-x.md",
  "phase": "build",
  "next_phase": "build",
  "catchup_mode": "skipped",
  "phases_completed": [],
  "cycle": 1,
  "rework_cap": 3,
  "tasks_total": 6,
  "tasks_completed": 2,
  "tasks": [
    {"id": "task-uuid-1", "name": "Add validation endpoint", "status": "completed", "model": "sonnet", "attempts": [
      {"attempt": 1, "model": "sonnet", "outcome": "escalated", "review_cycle": null, "cause": null, "implementor": "qwen", "preflight_outcome": "healthy", "pipeline": "lean", "diagnosis": "solid_spec", "qwen_gate_failed": true},
      {"attempt": 2, "model": "sonnet", "outcome": "completed", "review_cycle": null, "cause": null, "implementor": "claude", "preflight_outcome": null, "pipeline": "lean", "self_deslop": "noop", "escalation_reason": "gate_failure", "escalated_from": "qwen"}
    ]},
    {"id": "task-uuid-2", "name": "Update API types", "status": "completed"},
    {"id": "task-uuid-3", "name": "Write integration tests", "status": "in_progress"},
    {"id": "task-uuid-4", "name": "Update frontend form", "status": "pending"},
    {"id": "task-uuid-5", "name": "Add error handling", "status": "pending"},
    {"id": "task-uuid-6", "name": "Update docs", "status": "pending"}
  ],
  "task_aborts": [
    {"task_id": "task-uuid-7", "turn": -1, "total_input_tokens": 13000, "cause": "subagent_prompt_overrun"}
  ],
  "cap_rotations": [
    {"task_id": "task-uuid-3", "cycle": 1}
  ],
  "replan_count": 0,
  "work_start_sha": "7a962b768211be1c0c3e489f81f8e7168970db88",
  "repo_root": "/Users/bob/.claude/skills/run-autopilot",
  "design_mode": "run",
  "design_gate": "user",
  "design_doc": "dev/local/designs/00004-feature-x-design.md",
  "doubt_reviewer": "codex",
  "consensus_engine": "legacy",
  "rework_task_ids": ["task-uuid-3"],
  "qwen_gate_failures_consecutive": 0,
  "qwen_breaker": {"tripped": false, "after_task": null, "failed_tasks": [], "batch_id": "202603161000"},
  "stall_reason": {
    "stalled": "oversized_task",
    "task": "task-uuid-8",
    "estimated_tokens": 167000
  },
  "cap_pause_reason": {
    "cycle": 3,
    "cap": 3,
    "unresolved_findings": [
      {"issue": "...", "severity": "high", "consensus": "3/3"}
    ]
  },
  "pause_reason": {
    "site": "reviewer_fail",
    "detail": "carl reviewer CLI hung 45m with no output"
  },
  "review_cycles": [
    {
      "cycle": 1,
      "review_file": "dev/local/reviews/00004-feature-x-review-01.md",
      "agents": {"alice": "available", "bob": "available", "carl": "disabled", "diana": "available"},
      "issues_found": 5,
      "follow_up_tasks": 3,
      "deferred": 1,
      "recurring_issues": []
    }
  ],
  "autonomous_decisions": [
    {
      "cycle": 1,
      "issue": "Missing null check in parser",
      "severity": "medium",
      "consensus": "2/3",
      "action": "auto-fix",
      "reason": "mechanical fix, additive only"
    },
    {
      "cycle": 2,
      "issue": "New dependency needed: zod",
      "severity": "high",
      "consensus": "2/3",
      "action": "auto-fix",
      "reason": "research-passed: OSI-approved (MIT), actively maintained, no CVEs",
      "research": {
        "category": "new-dependency",
        "verdict": "proceed",
        "checks": [
          {"check": "license", "result": "MIT (OSI-approved, compatible with project MIT)", "pass": true},
          {"check": "maintenance", "result": "last commit 2 weeks ago, 12k GitHub stars", "pass": true},
          {"check": "security", "result": "no known CVEs", "pass": true},
          {"check": "adoption", "result": "4.2M weekly npm downloads", "pass": true}
        ],
        "evidence_summary": "zod: MIT license, last commit 2026-03-15, no CVEs, 4.2M weekly downloads"
      }
    }
  ],
  "deferred_decisions": [
    {
      "cycle": 1,
      "issue": "API signature change needed",
      "severity": "high",
      "consensus": "3/3",
      "reason": "touches public API — research-failed: external-facing, PRD doesn't specify signature",
      "status": "pending",
      "research": {
        "category": "high-public-api",
        "verdict": "escalate",
        "checks": [
          {"check": "prd-requires-change", "result": "PRD mentions API but no signature spec", "pass": false},
          {"check": "api-scope", "result": "external-facing REST endpoint", "pass": false}
        ],
        "evidence_summary": "API is external-facing, PRD doesn't specify new signature"
      }
    }
  ],
  "batch": {
    "id": "202603161000",
    "mode": "autopilot",
    "parks_consecutive": 0,
    "completed_prds": [
      {
        "filename": "00001-user-auth.md",
        "cycles": 2,
        "autonomous_decisions": 3,
        "escalated_decisions": 0
      }
    ],
    "catchup_completed_at": "2026-03-16T10:42:13Z",
    "catchup_head_sha": "a1b2c3d4e5f6789..."
  },
  "doubts": [],
  "doubts_rubric_verdicts": [
    {"rule_id": "R1", "verdict": "pass"},
    {"rule_id": "R2", "verdict": "pass"},
    {"rule_id": "R3", "verdict": "pass"},
    {"rule_id": "R4", "verdict": "fail"},
    {"rule_id": "R5", "verdict": "pass"}
  ],
  "needs_attention": false
}
```

## Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `prd` | string | PRD filename (with `.md` extension), e.g. `"00004-feature-x.md"`. Resolves to `dev/local/prds/wip/<prd>` while active, or `dev/local/prds/hold/<prd>` after a Phase 2 (`oversized_task`) or Phase 6 (`escalation_exhausted`) stall move. Phase 0's `subagent_prompt_overrun` replan handler does NOT move the PRD — it replans in place (PRD stays in `wip/`); a context-cap fire rotates (also in place, no move). Written by Phase 0 step 6 at PRD selection. The dashboard derives `name` by stripping the extension. |
| `phase` | enum | Current gate: `build`, `review`, `done`, `paused`. `build` is ONE session (selection → catchup → design → planning → work, no mid-build handoff); the review surface runs in a fresh session; blind and doubt scrutiny are lenses inside every review cycle (PRD 00015), not phases. **Legacy values** `blind`/`doubt` (pre-00015 state files) map to the review gate on resume — `resume_target.py` sends them through one full review cycle. |
| `next_phase` | string | Gate the next session of `/run-autopilot` will run. Written by `/run-autopilot` at every transition. **Read by the `autoclaude` wrapper after each headless session exits (PRD 00014)**: a non-empty gate (`build`/`review`/`done`) → relaunch a fresh session, and `""` (empty, batch end) → archive state and stop the loop (drained). The authoritative resume signal is `phase` + `phases_completed`; build re-entry is by artifact (capsule freshness, tasks-exist, all-done). |
| `catchup_mode` | enum | `"run"` (default; Phase 1 honors the batch cache), `"skip"` (PRD frontmatter requested skip), `"force"` (PRD frontmatter forces full catchup ignoring batch cache), or `"skipped"` (Phase 1 was bypassed for this PRD). Set at Phase 0 from PRD frontmatter `catchup:`; defaults to `"run"` on missing/malformed frontmatter. |
| `design_mode` | enum? | `"run"` (default; the Phase 1.5 design sub-step invokes `/design-solution`), `"skip"` (PRD frontmatter requested skip), or `"skipped"` (Phase 1.5 was bypassed for this PRD). Set at Phase 0 step 4 from PRD frontmatter `design:`; defaults to `"run"` on missing/malformed frontmatter. Read by the Phase 1.5 design sub-step. Cleared by Phase 9 step 10 on PRD-to-PRD reset (re-derived from the next PRD's frontmatter at Phase 0). Absent on plans created before this field existed. |
| `design_gate` | string? | `"user"` when PRD frontmatter `design_gate: user` requests an interactive review pause after design; absent otherwise. Set at Phase 0 step 4 from PRD frontmatter `design_gate:` (only an exact `user` match writes the field). Read by Phase 1.5: when `"user"`, the sub-step PAUSEs with the design doc summary via `AskUserQuestion` before planning. Cleared by Phase 9 step 10 on PRD-to-PRD reset. Absent in normal operation (no gate requested). |
| `design_doc` | string? | Path to the reviewed design doc the Phase 1.5 design sub-step produced: `dev/local/designs/<prd-stem>-design.md` (`<prd-stem>` = `prd` minus `.md`). Written by Phase 1.5 on a successful `/design-solution` run, or set to the existing path when the artifact is reused. Read by `/plan-tasks` (copies the doc's `## Interfaces & contracts` into task `Contract`s) and `/review-work-completion` (appends the doc under a `## Design Doc` heading to reviewer context). The design doc FILE is a durable artifact under `dev/local/designs/` (like review files — never deleted); only this state reference is cleared by Phase 9 step 10 on PRD-to-PRD reset. Absent on PRDs that skipped design (`design_mode == "skipped"`) and on plans created before this field existed. |
| `phases_completed` | string[] | Membership markers for finished review surfaces. Post-00015 the only writer appends `"review"` (at review-loop convergence); legacy state files may also carry `"blind"`/`"doubt"`. |
| `cycle` | int | Current review-rework cycle (starts at 1) |
| `rework_cap` | int | Effective review-rework cycle cap for the current PRD. Parsed by Phase 0 from PRD frontmatter field `rework_cap: <int>`; defaults to `3` when absent, missing, or invalid. Compared against `cycle` at Phase 5 decision gate: rework allowed while `cycle < rework_cap`; pause when `cycle >= rework_cap`. Per-PRD scope, but re-derived by Phase 0 step 4 from the next PRD's frontmatter on every PRD-to-PRD transition (default 3), so it needs no explicit Phase 9 step 10 clear. |
| `doubt_reviewer` | enum? | Doubt-lens roster flag for the current PRD. Parsed by Phase 0 step 4 from PRD frontmatter field `doubt_reviewer:`; accepted values `codex` (default) and `fable`; defaults to `codex` when absent, unrecognized, or on malformed frontmatter (one-line warning logged on the unrecognized-value / malformed path, none on plain absence). Read by the review phase (PRD 00015): when `fable`, Eve (Fable 5) joins the review batch as a fifth lens running the same doubt prompt as Bob, and the rubric verdicts are recorded per reviewer with `source` tags; when `codex` (or absent) the standard roster runs unchanged. Per-PRD scope, re-derived by Phase 0 step 4 from the next PRD's frontmatter on every PRD-to-PRD transition (default `codex`), so it needs no explicit Phase 9 step 10 clear. Absent on plans created before this field existed. |
| `consensus_engine` | enum? | Engine behind Alice's consensus leg for the current PRD. Parsed by Phase 0 step 4 from PRD frontmatter field `consensus_engine:`; accepted values `legacy` (default), `shadow`, `workflow`; defaults to `legacy` when absent, unrecognized, or on malformed frontmatter (one-line warning on the unrecognized-value / malformed path, none on plain absence). Read by `review-work-completion` step 1: `legacy` runs today's single review subagent unchanged; `workflow` makes the `review-fanout` workflow Alice's leg (dimension fan-out, dedup, adversarial verify); `shadow` runs both, legacy gating and the workflow recorded as a non-gating observation. Per-PRD scope, re-derived by Phase 0 step 4 from the next PRD's frontmatter on every PRD-to-PRD transition (default `legacy`), so it needs no explicit Phase 9 step 10 clear. The workflow's `runId` is NOT stored here — it is stamped into the review file's `consensus_run_id` frontmatter, because `resumeFromRunId` is same-session only. |
| `tasks_total` | int | Total task count. Derived from the `tasks` snapshot: every writer of `tasks` recomputes `tasks_total = len(tasks)` in the same write (the pidash-era PostToolUse sync hook is retired, PRD 00063). |
| `tasks_completed` | int | Number of completed tasks. Derived with `tasks_total`: `tasks_completed = count(status == "completed")`, recomputed on every `tasks` write. |
| `tasks` | object[] | Task list from TaskList: `{"id": "<task-id>", "name": "...", "status": "pending\|in_progress\|completed", "model"?: "haiku\|sonnet\|opus", "attempts"?: object[]}`. Include `id` — state readers (tracon, the review phase, `rework_task_ids` targeting) and the hydration round-trip key on it. |
| `tasks[].model` | enum? | Per-task model tier: `"haiku"`, `"sonnet"`, `"opus"`. Mirror of `task.metadata.model` (the canonical source `/work` reads via `TaskGet`). Written by /run-autopilot Phase 3 snapshot (initial; mirrors metadata.model that plan-tasks set via `TaskCreate(metadata={model})` in step 4.7) and rewritten by /run-autopilot Phase 6 escalation (paired `TaskUpdate(metadata={model})` + direct `state.tasks[i].model` write per the metadata.model↔state.tasks[].model sync; see `references/phase-review.md` Phase 6). The dashboard and the review phase read this snapshot field; `/work` reads `task.metadata.model`. When absent (plans created before PRD 00025), `/work` omits `model` and subagents inherit the session model. |
| `tasks[].attempts` | object[]? | Per-task execution log: `{"attempt": int, "model": string, "outcome": "completed"\|"aborted"\|"review_flagged"\|"rework_failed"\|"escalated", "review_cycle": int\|null, "cause": string\|null, "implementor": "claude"\|"gemini"\|"qwen", "preflight_outcome": "healthy"\|"pi_missing"\|"endpoint_unreachable"\|"model_id_missing"\|"completion_failed"\|null, "pipeline"?: "minimal"\|"lean"\|"full", "self_deslop"?: string, "escalation_reason"?: "gate_failure"\|"review_flag", "escalated_from"?: "qwen"\|"haiku"\|"sonnet"\|"opus", "diagnosis"?: "spec_gap"\|"solid_spec", "repair_used"?: true, "breaker_skipped"?: true, "qwen_gate_failed"?: true}`. Records each Work pass on the task. Appended by `/work` at task exit (success or abort). The `implementor` field reflects what actually dispatched (NOT what step 3's routing table initially picked — a qwen pick that fell back to Claude on preflight failure records `"claude"`). The `preflight_outcome` field is set only for attempts on qwen-eligible tasks (`task.metadata.qwen_eligible == true` at attempt start); for non-qwen-eligible attempts (UI tasks, `opus`-tier tasks, backend tasks where `qwen_eligible` is `false` or absent) it is `null`. The `pipeline` field records the tier-gated pipeline depth the attempt ran — `"minimal"`/`"lean"`/`"full"` for `haiku`/`sonnet`/`opus` (absent/legacy `model` is treated as `sonnet` → `"lean"`), written at every task exit (PRD 00044) — the `?` in the signature marks read-side tolerance for pre-00044 rows only; new writes always include `pipeline`. **Cardinality (PRD 00065):** today `/work` appends exactly one entry per task at exit. Under in-loop escalation the rule widens to one entry per rung/dispatch-group: each rung that dispatched writes its own entry when the task escalates away from it or exits on it. `attempt` numbers stay sequential across rungs (`len(existing)+1`). This is a widening, not a break — a task that never escalates still writes exactly one entry, byte-identical to today. **Six escalation fields (PRD 00065, all optional, absence = legacy / not-applicable):** `escalation_reason` (`"gate_failure"` stamped by `/work` on the entry of the rung it escalated INTO (in-loop diagnosis); `"review_flag"` stamped by phase-review Phase 6 on its escalation path. Absent = neither (legacy / no escalation)); `escalated_from` (string?; a tier — on the entry of the rung escalated INTO, the immediate-prior rung it came from. Absent on non-escalated entries); `diagnosis` (string?; the 2nd-failure diagnosis verdict, stamped on the entry of the rung that was diagnosed); `repair_used` (bool?; `true` stamped on the entry of the same-tier attempt that ran after a task-description repair; absent otherwise, never written `false`); `breaker_skipped` (bool?; `true` stamped on a qwen-eligible attempt the breaker rerouted to Claude at original tier (no preflight probe); absent otherwise); `qwen_gate_failed` (bool?; `true` stamped on an `implementor:"qwen"` entry whose step-5.5 gate FAILED — the durable signal the qwen capability breaker keys on; absent otherwise). The `"escalated"` outcome value is stamped on the entry for a rung the task was reset away from and escalated up; the final rung's entry carries the real terminal outcome (`completed`/`aborted`), and the escalated-away entry keeps its true `implementor` (a qwen rung escalated to Sonnet keeps `implementor:"qwen"`). See `work/references/attempt-logging.md` for field semantics, the atomic write procedure, and the attribution row-ownership table. Outcome upgraded later by /run-autopilot Phase 6: `review_flagged` at the start of escalation (step 2), then `rework_failed` if the chain exhausts at `opus` (step 3's escalation-exhausted branch). Rework reads the last entry's `model` to determine the next tier. Absent on plans created before PRD 00025; `implementor`/`preflight_outcome` absent on attempts written before PRD 00031; `self_deslop` absent on attempts written before PRD 00041; `pipeline` absent on attempts written before PRD 00044; the six escalation fields and the `"escalated"` outcome value absent on attempts written before PRD 00065. |
| `tasks[].attempts[].self_deslop` | string? | Outcome of the per-task self-deslop pass that `/work` runs as step 5.6 between test-pass (5.5) and per-task code review (5.7). Allowed values: `"committed:{sha}"` (the self-deslop subagent committed a `chore: prune slop from ...` cleanup), `"noop"` (subagent ran but found no slop, no commit), `"skipped:trivial"` (skip rule fired — diff added <30 net lines OR touched <2 files), `"timeout"` (subagent watchdog killed it), `"errored:{cause}"` (dispatch failed; `{cause}` is a short tag). Optional; absent on legacy attempts (pre-PRD-00041) and on attempts the writer never updated. Self-deslop is best-effort: it never blocks a task, never triggers retries, and never modifies the `outcome` field. The per-task review at step 5.7 runs against the post-cleanup diff when a cleanup committed; against the original diff otherwise. |
| `tasks[].estimated_tokens` | int? | Per-task input-token budget estimate produced by plan-tasks step 4.7 tier classifier. Used by the hydration round-trip to restore TaskCreate metadata across sessions. Written by plan-tasks step 4.7 via `TaskCreate(metadata={estimated_tokens})`; mirrored into the Phase 3 snapshot; round-tripped by the State Management hydration sub-step. Absent when plan-tasks did not record a budget estimate. |
| `tasks[].est_context_peak` | int? | Per-task estimated peak working-context size produced by plan-tasks step 4.7. Used to predict subagent dispatch budget headroom. Written by plan-tasks step 4.7 via `TaskCreate(metadata={est_context_peak})`; mirrored into the Phase 3 snapshot; round-tripped by the State Management hydration sub-step. Absent when plan-tasks did not record a context estimate. |
| `tasks[].qwen_eligible` | bool? | Qwen routing eligibility computed by plan-tasks step 4.7 (PRD 00032, widened by PRD 00019): backend (not UI) AND tier ∈ {`haiku`, `sonnet`} AND `files_touched <= 3` AND no public-contract edit. Written via `TaskCreate(metadata={qwen_eligible})`; mirrored into the Phase 3 snapshot; round-tripped by the hydration sub-step. `/work` reads the metadata mirror for routing; absent (legacy plans) is treated as `false`. |
| `tasks[].qwen_excluded_reason` | string? | Why plan-tasks step 4.7 excluded the task from qwen routing: `"ui"`, `"tier"`, `"files"`, or `"contract"` (first failing condition in that order). Written on every ineligible task (PRD 00019) via `TaskCreate(metadata={qwen_excluded_reason})`; mirrored into the Phase 3 snapshot; round-tripped by the hydration sub-step. Absent on eligible tasks and legacy plans — the Phase 9 Implementor Mix render counts an ineligible task with no reason as `unknown`, never an error. |
| `task_aborts` | object[] | Per-task abort log: `{"task_id": string, "turn": int, "total_input_tokens": int, "cause": "subagent_prompt_overrun"}`. One writer: `/work` Subagent Dispatch Budget appends a `cause: "subagent_prompt_overrun"` entry when an assembled subagent prompt exceeds 50K after one trim pass. (The context cap no longer writes here — it ROTATES, appending to `cap_rotations`.) Sets `turn: -1` when the actual turn is unknown (the assembly carries no turn counter). Empty array on fresh state. **`task_aborts[]` is ephemeral per-PRD state — Phase 9 step 10 clears it on PRD completion.** |
| `cap_rotations` | object[]? | Context-cap rotation log: `{"task_id": string, "cycle": int}`. Appended by `autopilot_context_cap_hook.py` when a Work turn during `build` exceeds the hard usage cap (`USAGE_CAP`, 500K) — a ROTATION, not a replan: the hook also sets `next_phase: "build"` and resets the in-flight task's status from `in_progress` to `pending` (so the fresh session's `/work`, which iterates pending tasks, re-attempts it as the first non-completed task). The hook records the rotation and sets `next_phase: "build"`; the Stop hook then writes the `next` signal on STOP (the model writes no signal). Apart from the one in-flight task's `status`, leaves `tasks`, `phases_completed`, and `replan_count` untouched; writes no `stall_reason` and no `replan-context.md`. **Livelock guard:** if the last entry already names the in-flight task, a second consecutive fire on the same task sets `stall_reason.stalled == "oversized_task"` instead of appending another rotation (one oversized task costs at most two rotations before a loud stall). Ephemeral per-PRD state — Phase 9 step 10 clears it. Absent on fresh state and on plans created before this field existed. |
| `replan_count` | int? | Number of replans applied to the current PRD after Phase 0 saw a `subagent_prompt_overrun` stall (the one surviving replan trigger; a context-cap fire rotates instead and leaves `replan_count` unchanged). Incremented by Phase 0's replan procedure before each retry. Each replan tightens the per-task budget by halving (floored at 40K) — see `recovery.md` "Budget floor guard" for the `target_budget = max(40000, int(75000 / (2 ** (replan_count - 1))))` schedule. Phase 0 PAUSEs only when `replan_count > 5` AND the same task keeps aborting (genuinely execution-overflowing, not capability-bound). Reset to 0 by Phase 9 step 10 when the PRD completes. Absent or 0 means the current PRD has not been replanned. |
| `work_start_sha` | string? | Git `HEAD` SHA captured at Phase 3 start, immediately before `/work` is dispatched. Bounds the commit range `work_start_sha..HEAD` produced by this PRD's `/work` dispatches — read by Phase 8 to scope the codex doubt review's diff (`<work_start_sha>..HEAD`). Captured once per PRD; in a multi-PRD batch each PRD overwrites it with current HEAD at Phase 3 start, so ranges never overlap. **Empty-tree fallback (PRD 00084):** when `git rev-parse HEAD` fails at capture (unborn branch / no commits yet), this is set to the git empty-tree sentinel `4b825dc642cb6eb9a060e54bf8d69288fbee4904` so the review range spans the whole tree instead of being undefined (core `SKILL.md` § Phase 3 invariants). Cleared by Phase 9 step 10 on PRD-to-PRD reset. Optional: absent on plans created before this field was introduced, and on PRDs where Phase 3 has not yet run. |
| `repo_root` | string? | Absolute path to the git repo containing the work commits (`git rev-parse --show-toplevel`), captured at Phase 3 start alongside `work_start_sha`. Usually equals the project root; differs when the work repo is nested under a non-git project root (e.g. `~/.claude/skills/run-autopilot` under `~/.claude`). Read by the review session to run `git` (diff gathering, `head_sha` capture) in the right repo. Cleared by Phase 9 step 10 on PRD-to-PRD reset. Optional: absent on older plans; consumers fall back to the project root. |
| `rework_task_ids` | string[]? | Set by `/run-autopilot` Phase 6 (rework) to instruct `/work` to process only those task IDs at their escalated tier. Non-empty puts `/work` in rework mode (skip completed-not-flagged tasks; re-iterate the listed IDs). Cleared (set to `[]`) by `/run-autopilot` after the rework `/work` pass finishes. Empty/absent means full-plan dispatch — the default Phase 3 behavior. |
| `qwen_gate_failures_consecutive` | int? | Consecutive qwen step-5.5 gate failures, counted among qwen attempts ONLY (PRD 00065) — a non-qwen task (Claude/Gemini) between two qwen failures leaves it UNCHANGED (neither reset nor incremented). Only a qwen gate PASS resets it to 0; batch rollover also resets it. Incremented per qwen gate failure. Latches the breaker at 2. Owned entirely by `/work`. Legacy state lacking the field: readers treat it as 0. |
| `qwen_breaker` | object? | Qwen capability breaker state (PRD 00065): `{"tripped": bool, "after_task": "<task-id>"\|null, "failed_tasks": ["<id>", ...], "batch_id": "<batch.id>"}`. `tripped:true` once the counter reaches 2. `after_task` = the task id whose failure tripped it; `failed_tasks` = the two consecutive failing ids; `batch_id` = the batch this breaker state belongs to. Batch-scoped: `/work` resets the breaker lazily when `qwen_breaker.batch_id != state.batch.id` (fallback id `"no-batch"` for a manual `/work` run with no `state.batch`). Once tripped, stays tripped for the rest of the batch. Legacy state lacking the field: readers treat it as `{tripped:false}`. |
| `stall_reason` | object? | Signals a pending recovery action. Three shapes: `{"stalled": "oversized_task", "task": "<id>", ...}` (written by `/plan-tasks` when a task can't be split below budget — carries `estimated_tokens?: int`; AND by `autopilot_context_cap_hook.py`'s livelock guard on a second consecutive cap fire for the same in-flight task — carries `total_input_tokens: int`; both trigger a stall move to `dev/local/prds/hold/`); `{"stalled": "subagent_prompt_overrun", "task": "<id>", "prompt_bytes": int}` (written by `/work` Subagent Dispatch Budget when an assembled subagent prompt exceeds 50K after one trim pass — triggers Phase 0's **replan procedure**, not a stall move; see `replan_count` and `/run-autopilot` Phase 0 "Handle Work-phase abort"); `{"stalled": "escalation_exhausted", "task": "<id>"}` (written by `/run-autopilot` Phase 6 when a task at tier `opus` fails rework — Phase 6 performs its own stall move inline); `{"stalled": "taskcreate_failed", "detail": "<error>"}` (written by `/plan-tasks` step 4 when a `TaskCreate` call fails mid-plan, after it rolls back the tasks it already created — PRD 00084; Phase 2 folds any non-`oversized_task` stall into its `plan_tasks_fail` PAUSE / loop re-invoke-once path, and `/plan-tasks` clears this marker itself on a successful retry). **Merged** (not replacing) into state by the writer, then **cleared** by `/run-autopilot`. Lifecycle handoff: Phase 2 handles `oversized_task` inline with a stall move; Phase 0 of the next session handles `subagent_prompt_overrun` via the replan procedure (no stall move — the PRD stays in `wip/`, planning re-runs with `replan-context.md`); Phase 6 handles `escalation_exhausted` inline (it owns the rework path and does its own move + clear before signaling — Phase 0 should never see this in normal operation, and treats it as crash recovery if it does). The context cap no longer writes `stall_reason` on a normal overrun — it ROTATES (see `cap_rotations`); only its livelock guard escalates to `oversized_task`. Absent in normal operation. |
| `cap_pause_reason` | object? | Set by Phase 5 when the rework cap is hit AND the current review did not converge (`cycle >= rework_cap` AND unresolved findings remain). A clean cycle-at-cap convergence does NOT trigger cap-pause — it falls through to Phase 7 hand-off. Records the unresolved review findings and the cycle count. Shape: `{"cycle": int, "cap": int, "unresolved_findings": object[]}`. **Distinct from `stall_reason`'s `oversized_task`, `subagent_prompt_overrun`, and `escalation_exhausted` shapes** — `cap_pause_reason` is a separate top-level state field, not another `stall_reason` discriminator. The authoritative, durable indicator of a cap pause is `phase == "paused"` PLUS this field — not `needs_attention`. Cleared by (a) the Phase 0 Cap-Pause Resume Handler on user "resume", (b) Phase 9 step 10's PRD-to-PRD reset, and (c) the per-PRD reset lists in `recovery.md`. Previously only (a) applied — a cap pause halts the flow before Phase 9, so Phase 9 step 10 never observed this field in normal operation — but (b) and (c) are now added as defense-in-depth against the residual-leakage path (a manual "abandon" followed by a manual PRD move, which falls outside the automated flow). Absent in normal operation. |
| `pause_reason` | object? | Set by every turn-ending PAUSE row alongside `phase == "paused"` / `next_phase == "paused"`. Shape: `{"site": string, "detail": string}`. `site` is a stable slug, one of: `"sub_skill_fail"`, `"reviewer_fail"`, `"plan_tasks_fail"`, `"mv_verify"`, `"batch_end"`, `"replan_exhausted"`, `"work_incomplete"`, `"systemic_park"`, `"statectl_fail"`. **`statectl_fail`** (PRD 00084) is written when a `statectl` state-write fails twice (lock contention, python error, unreadable state) and the model records the pause via the hand-edit fallback (core `SKILL.md` § State Management); in loop mode the same site names a Loop-mode stall instead. **`systemic_park`** (PRD 00066) is written by the Phase 0 park handler when `batch.parks_consecutive` reaches 2 (sanctioned-halt row 9). **Converted out of this enum by PRD 00066:** `blocking_escalation` and `scope_alarm` no longer write `pause_reason` — in loop mode a blocking escalation runs the Loop-mode stall procedure (deferred-JSON `type:"stall"`, `site:"blocking_escalation"`) and a scope alarm defers-and-continues; interactively both remain mid-turn `AskUserQuestion` prompts. `clarification` likewise pauses no batch: a Phase 2 ambiguity is assumed through, or stalls (`site:"clarification"`) under `pause_on_ambiguity: true`. `detail` is a one-line human-readable string; free-form, not parsed by any consumer. **Lifecycle invariant: `pause_reason` is present ONLY during an unresolved pause.** Cleared by (a) the pre-Phase-0 `### Resuming` session-start cleanup, unconditionally, on EVERY resume; (b) the Phase 9 step 10 PRD-to-PRD reset; and (c) every per-PRD reset list in `recovery.md`. NOT overwritten by normal phase progression — this is the difference from `phase` (which advances on every transition), and the reason the explicit clears above exist. Cap-pause keeps its own `cap_pause_reason` marker and does NOT write `pause_reason`. Read by the `autoclaude` wrapper's decision table (a pause marker stops the loop and surfaces `detail` in the notification). Absent on fresh state and whenever no pause is active. |
| `review_cycles` | object[] | History of each review cycle. Each entry: `{"cycle": int, "review_file": "<path>", "agents": {"alice": "...", "bob": "...", "carl": "...", "diana": "..."}, "issues_found": int, "follow_up_tasks": int, "deferred": int, "recurring_issues": string[]}`. Cycles 3+ may also carry `decision_gate`, `rework_commits`, `rework_notes`, `cycle3_fix_audit`, `test_run` written by user-override paths (see live state for examples). |
| `review_cycles[].recurring_issues` | string[] | Issue descriptions that appeared in a previous cycle |
| `review_lenses` | object? | Live lens roster for the CURRENT review cycle, stamped by `review-work-completion` step 5 at dispatch and closed out in step 6: maps lens -> `"running"\|"done"\|"failed"`. Keys: `consensus` (Alice), `blind` (Blake), `doubt` (Bob), plus `ui` (Carl), `qwen` (Quinn), `fable` (Eve) when active. REPLACED at each cycle's dispatch; tracon expands the review phase strip from it. Absent on standalone runs and pre-field state files. |
| `autonomous_decisions` | object[] | Decisions made without user input. May include optional `research` field for research-backed decisions. |
| `deferred_decisions` | object[] | Decisions requiring user input. May include optional `research` field when research was attempted but inconclusive. |
| `doubts` | object[] | LEGACY (pre-00015 Phase 8): findings from the standalone doubt review, `{"description": "...", "category": "fix\|verify\|known", "justification?": "...", "status": "pending\|resolved", "source?": "codex\|fable"}`. Post-00015 the doubt lens's findings enter the normal review consolidation instead, so no new entries are written; Phase 9 step 6 still collects any lingering pending entries from old state files. Empty array on fresh state. |
| `doubts_rubric_verdicts` | object[]? | Per-rule verdict block recorded by the review phase's consolidation (PRD 00015; `review-work-completion` SKILL.md step 6) from the doubt lens's `R{n}: pass\|fail` lines — Bob's (codex or his Claude fallback), plus Eve's when she ran. Each entry: `{"rule_id": "R{n}", "verdict": "pass"\|"fail", "source?": "codex"\|"fable"}`. **`source?`** (PRD 00038, optional): written only when both doubt-lens reviewers ran (one entry per rule per reviewer, 10 entries); the single-reviewer path keeps 5 entries with no `source`. REPLACED every review cycle; the final cycle's verdicts are the durable ones. Used by Phase 9 step 7 to populate the "Doubt Rubric Verdicts" section of the batch report (see `references/batch-report-format.md`). Cleared by Phase 9 step 10 on PRD-to-PRD reset (per-PRD scope). Absent on PRDs that have not yet run a review cycle and on state files written before this field existed. |
| `needs_attention` | bool | Dashboard flag. Sole remaining writer: Phase 5 cap-pause MAY set `true` as a best-effort dashboard hint (the pidash Notification/PostToolUse hooks that set and cleared it are retired, PRD 00063). Nothing clears it automatically now — treat it as advisory only; tracon (PRD 00062) will own the read/clear lifecycle. **Dashboard-only state — NOT the authoritative cap-pause signal.** The authoritative cap-pause signal is `phase == "paused"` plus `cap_pause_reason` being set.
| `phase_guard` | object? | RETIRED (PRD 00014, with `autopilot_stop_hook.py`). May linger in pre-00014 state files; ignored by all consumers. |
| `thrash_halt` | object? | RETIRED (PRD 00014, with `autopilot_stop_hook.py`). May linger in pre-00014 state files; ignored by all consumers. |
| `batch` | object? | Tracks completed PRDs across sessions |
| `batch.id` | string | Batch ID: `yyyymmddHHMM` timestamp of first execution |
| `batch.mode` | string | Always `"autopilot"` |
| `batch.parks_consecutive` | int? | Consecutive `wrapper_died` parks (Phase 0 park handler) with NO healthy PRD outcome between them — the systemic-park breaker (PRD 00066). Lives under `batch` so it survives the per-PRD reset. Incremented by 1 in the park handler's per-PRD-reset write; at `>= 2` the handler PAUSEs the batch (`pause_reason.site = "systemic_park"`, sanctioned-halt row 9). Reset to 0 on ANY healthy outcome — Phase 9 PRD completion, and any non-`wrapper_died` Loop-mode stall (the stall procedure resets it whenever `site != "wrapper_died"`, `references/recovery.md`). Default 0; legacy state lacking the field: readers treat it as 0. |
| `batch.completed_prds` | object[] | PRDs finished so far: `{"filename", "cycles", "autonomous_decisions", "escalated_decisions"}` |
| `batch.catchup_completed_at` | string? | ISO 8601 UTC timestamp recorded when the most recent full `/catchup` invocation in this batch completed. Read by Phase 1 "Batch cache check": if present, < 4h old, AND `batch.catchup_head_sha` matches current HEAD, Phase 1 runs a delta refresh instead of full catchup. Written by Phase 1 after full catchup completes. Preserved by Phase 9 step 10 across PRD-to-PRD state resets so subsequent PRDs in the same batch can reuse the cache. Absent on first PRD of a batch and on plans that never ran full catchup. |
| `batch.catchup_head_sha` | string? | Git HEAD SHA captured at the moment full `/catchup` completed in this batch. Paired with `catchup_completed_at` for the Phase 1 cache check. Written and preserved on the same lifecycle as `catchup_completed_at`. |

**Note on PRD 00025:** `tasks[].model`, `tasks[].attempts[]`, and `rework_task_ids[]` are active fields written and read by `/plan-tasks` (Tier classifier), `/work` (per-task model dispatch + attempt logging + rework-mode iteration), and `/run-autopilot` Phase 6 (review-driven tier escalation).

## Marker files

The wrapper↔skill hand-off uses touch-file markers in `dev/local/autopilot/`, never `state.json` edits (state surgery stays in-skill). Each is consumed at a session boundary:

| Marker | Writer | Consumer | Content |
|--------|--------|----------|---------|
| `pause-requested` | operator (`touch`) | wrapper, at the next session boundary — stops the loop, notifies "paused by operator" | empty |
| `park-requested` | wrapper `park)` case (single writer) | Phase 0 "Handle park request" (FIRST abort-handler check); deletes it AFTER the verified `hold/` move | one-line JSON `{"prd": "<state.prd basename>", "reason": "<one-line death/thrash cause>"}` |

`park-requested` (PRD 00066) is the wrapper's entire signal that a died-session retry budget was exhausted (or the fingerprint bound fired) for a *selected* PRD: the wrapper writes it and relaunches; the next session's Phase 0 park handler parks the named PRD via the Loop-mode stall procedure (`references/phase-build.md`, `references/recovery.md`), recording a `wrapper_died` deferred stall. `prd` is the bare filename (`00XXX-` prefix, `.md` suffix), compared against the basenames of `dev/local/prds/wip/*.md`; a marker naming a PRD absent from `wip/` (or a malformed one) is consumed, logged, and dropped — never crashes selection. The wrapper never blind-`rm`s it at loop start (a valid unparked marker must survive a crash); a marker left unconsumed past one session cycle trips the wrapper's park-loop guard (sanctioned-halt row 10).

## Research Evidence Schema

When a decision is made through the research-then-decide path, the `research` field is added to the decision entry (in either `autonomous_decisions` or `deferred_decisions`):

| Field | Type | Description |
|-------|------|-------------|
| `research.category` | enum | `"new-dependency"`, `"recurring-issue"`, `"high-data-model"`, `"high-public-api"` |
| `research.verdict` | enum | `"proceed"` (all checks passed) or `"escalate"` (any check failed) |
| `research.checks` | object[] | Array of `{"check": "<name>", "result": "<finding>", "pass": true\|false}` |
| `research.evidence_summary` | string | One-line human-readable summary of findings |

**Rule:** If ANY check has `"pass": false`, verdict MUST be `"escalate"`. Inconclusive counts as fail.

## Batch Deferred Log

File: `dev/local/autopilot/deferred/{batch_id}-deferred.json` - persists across PRD sessions, not reset between PRDs.

```json
[
  {
    "prd": "00004-feature-x.md",
    "cycle": 2,
    "type": "deferred_decision",
    "issue": "API signature change needed",
    "severity": "high",
    "reason": "touches public API",
    "research": {
      "category": "high-public-api",
      "verdict": "escalate",
      "checks": [
        {"check": "prd-requires-change", "result": "PRD mentions API but no signature spec", "pass": false}
      ],
      "evidence_summary": "API is external-facing, PRD doesn't specify new signature"
    }
  },
  {
    "prd": "00005-auth-rework.md",
    "cycle": 1,
    "type": "doubt",
    "category": "known",
    "issue": "Edge case in token refresh under concurrent requests",
    "justification": "Requires distributed lock infrastructure not in scope for this PRD"
  },
  {
    "prd": "00004-feature-x.md",
    "cycle": 2,
    "type": "autonomous_research",
    "issue": "New dependency needed: zod",
    "severity": "high",
    "action": "auto-fix",
    "research": {
      "category": "new-dependency",
      "verdict": "proceed",
      "checks": [
        {"check": "license", "result": "MIT (compatible)", "pass": true},
        {"check": "maintenance", "result": "active", "pass": true},
        {"check": "security", "result": "no CVEs", "pass": true},
        {"check": "adoption", "result": "4.2M weekly downloads", "pass": true}
      ],
      "evidence_summary": "zod: MIT, active, no CVEs, 4.2M downloads"
    }
  }
]
```

Written at Phase 9 step 6, and appended incrementally by the Loop-mode stall procedure (`references/recovery.md`) for `type:"stall"` records. This is the single source of truth for batch-end review. Includes:
- `deferred_decision` — issues that failed research or were deferred for other reasons
- `doubt` — unresolved findings from doubt review (KNOWN items with justification)
- `autonomous_research` — research-backed decisions made autonomously (for user awareness at batch end)
- `stall` — a PRD parked to `dev/local/prds/hold/` by the Loop-mode stall procedure: `{"type":"stall","site":"<slug>","detail":"...","prd":"..."}`. `site` slugs: `wrapper_died` (a died-session or fingerprint-thrash park, PRD 00066), `design_gate` (a loop-mode Phase 1.5 design gate), `blocking_escalation` (a loop-mode Phase 5 blocking escalation), `clarification` (a `pause_on_ambiguity` Phase 2 stall), `statectl_fail` (a loop-mode `statectl` write failure, PRD 00084), plus the recovery stalls `oversized_task` / `escalation_exhausted`. Batch-end counts these as `{m} stalled` and lists them in the STALLED PRDS review block (`references/phase-done.md`).

Each entry preserves the full `research` field when available, so evidence is readable at batch-end review even after per-PRD state is cleared. Not deleted by autopilot - left for user review.

## Skip Logic

Used to determine which phases to skip:

| Gate | Skip if |
|-------|---------|
| catchup (build sub-step) | capsule is fresh (batch cache check holds) OR `catchup_mode == "skip"` — by ARTIFACT, not `phases_completed` |
| planning (build sub-step) | `TaskList` returns pending or completed tasks (evaluate **after** hydrating from `state.tasks` — see `references/phase-build.md` Phase 2) |
| work (build sub-step) | All tasks completed, none pending (evaluate **after** hydrating from `state.tasks` — see `references/phase-build.md` Phase 3) |
| review | `"review"` in `phases_completed` (loop converged in a prior session), OR this cycle's review file exists in `dev/local/reviews/` |
| blind | `"blind"` in `phases_completed` |
| doubt | `"doubt"` in `phases_completed` |
