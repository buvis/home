# State Schema

State file location: `dev/local/autopilot/state.json`

## Schema

```json
{
  "prd": "00004-feature-x.md",
  "phase": "work",
  "next_phase": "work",
  "catchup_mode": "skipped",
  "phases_completed": ["catchup", "planning"],
  "cycle": 1,
  "tasks_total": 6,
  "tasks_completed": 2,
  "tasks": [
    {"id": "task-uuid-1", "name": "Add validation endpoint", "status": "completed", "model": "sonnet", "attempts": [
      {"attempt": 1, "model": "sonnet", "outcome": "completed", "review_cycle": null, "cause": null}
    ]},
    {"id": "task-uuid-2", "name": "Update API types", "status": "completed"},
    {"id": "task-uuid-3", "name": "Write integration tests", "status": "in_progress"},
    {"id": "task-uuid-4", "name": "Update frontend form", "status": "pending"},
    {"id": "task-uuid-5", "name": "Add error handling", "status": "pending"},
    {"id": "task-uuid-6", "name": "Update docs", "status": "pending"}
  ],
  "task_aborts": [
    {"task_id": "task-uuid-7", "turn": -1, "total_input_tokens": 192340, "cause": "context_overrun"}
  ],
  "replan_count": 0,
  "work_start_sha": "7a962b768211be1c0c3e489f81f8e7168970db88",
  "rework_task_ids": ["task-uuid-3"],
  "stall_reason": {
    "stalled": "oversized_task",
    "task": "task-uuid-8",
    "estimated_tokens": 167000
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
  "needs_attention": false
}
```

## Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `prd` | string | PRD filename (with `.md` extension), e.g. `"00004-feature-x.md"`. Resolves to `dev/local/prds/wip/<prd>` while active, or `dev/local/prds/stalled/<prd>` after a Phase 2 (`oversized_task`) or Phase 6 (`escalation_exhausted`) stall move. Phase 0's `context_overrun`/`subagent_prompt_overrun` handlers do NOT move the PRD — they replan in place (PRD stays in `wip/`). Written by Phase 0 step 6 at PRD selection. The dashboard derives `name` by stripping the extension. |
| `phase` | enum | Current phase: `prd-selection`, `catchup`, `planning`, `work`, `review`, `decision-gate`, `rework`, `blind-review`, `doubt-review`, `done`, `paused` |
| `next_phase` | string | Phase the next iteration of `/run-autopilot` will run. Written by `/run-autopilot` immediately before the `signal` file. Read by `autoclaude` to pick `--model` for the next launch. Empty string means "no preference; consumer defaults to Opus." |
| `catchup_mode` | enum | `"run"` (default; Phase 1 honors the batch cache), `"skip"` (PRD frontmatter requested skip), `"force"` (PRD frontmatter forces full catchup ignoring batch cache), or `"skipped"` (Phase 1 was bypassed for this PRD). Set at Phase 0 from PRD frontmatter `catchup:`; defaults to `"run"` on missing/malformed frontmatter. |
| `phases_completed` | string[] | Phases finished this session |
| `cycle` | int | Current review-rework cycle (starts at 1) |
| `tasks_total` | int | Total task count from TaskList (pending + in_progress + completed) |
| `tasks_completed` | int | Number of completed tasks from TaskList |
| `tasks` | object[] | Task list from TaskList: `{"id": "<task-id>", "name": "...", "status": "pending\|in_progress\|completed", "model"?: "haiku\|sonnet\|opus", "attempts"?: object[]}`. Include `id` — a PostToolUse hook uses it to sync status changes automatically. |
| `tasks[].model` | enum? | Per-task model tier: `"haiku"`, `"sonnet"`, `"opus"`. Mirror of `task.metadata.model` (the canonical source `/work` reads via `TaskGet`). Written by /run-autopilot Phase 3 snapshot (initial; mirrors metadata.model that plan-tasks set via `TaskCreate(metadata={model})` in step 4.7) and rewritten by /run-autopilot Phase 6 escalation (paired `TaskUpdate(metadata={model})` + direct `state.tasks[i].model` write per the metadata.model↔state.tasks[].model sync; see SKILL.md Phase 6). The dashboard and the review phase read this snapshot field; `/work` reads `task.metadata.model`. When absent (plans created before PRD 00025), `/work` omits `model` and subagents inherit the session model. |
| `tasks[].attempts` | object[]? | Per-task execution log: `{"attempt": int, "model": string, "outcome": "completed"\|"aborted"\|"review_flagged"\|"rework_failed", "review_cycle": int\|null, "cause": string\|null}`. Records each Work pass on the task. Appended by `/work` at task exit (success or abort). Outcome upgraded later by /run-autopilot Phase 6: `review_flagged` at the start of escalation (step 2), then `rework_failed` if the chain exhausts at `opus` (step 3's escalation-exhausted branch). Rework reads the last entry's `model` to determine the next tier. Absent on plans created before PRD 00025. |
| `tasks[].estimated_tokens` | int? | Per-task input-token budget estimate produced by plan-tasks step 4.7 tier classifier. Used by the hydration round-trip to restore TaskCreate metadata across sessions. Written by plan-tasks step 4.7 via `TaskCreate(metadata={estimated_tokens})`; mirrored into the Phase 3 snapshot; round-tripped by the State Management hydration sub-step. Absent when plan-tasks did not record a budget estimate. |
| `tasks[].est_context_peak` | int? | Per-task estimated peak working-context size produced by plan-tasks step 4.7. Used to predict subagent dispatch budget headroom. Written by plan-tasks step 4.7 via `TaskCreate(metadata={est_context_peak})`; mirrored into the Phase 3 snapshot; round-tripped by the State Management hydration sub-step. Absent when plan-tasks did not record a context estimate. |
| `task_aborts` | object[] | Per-task abort log: `{"task_id": string, "turn": int, "total_input_tokens": int, "cause": "context_overrun"\|"subagent_prompt_overrun"}`. Two writers (matching the Session Loop `task_aborted` signal table): (a) `autopilot_context_cap_hook.py` appends a `cause: "context_overrun"` entry when a Work turn exceeds the context cap (see `context_window`); (b) `/work` Subagent Dispatch Budget appends a `cause: "subagent_prompt_overrun"` entry when an assembled subagent prompt exceeds 50K after one trim pass. Both writers set `turn: -1` when the actual turn is unknown (the transcript usage line carries no turn counter). Empty array on fresh state. **`task_aborts[]` is ephemeral per-PRD state — Phase 9 step 10 clears it on PRD completion.** The durable, never-cleared companion is `dev/local/autopilot/dispatch-log.jsonl`, which spans all PRDs and is the input to `dispatch_health_metrics.py`. |
| `replan_count` | int? | Number of replans applied to the current PRD after Phase 0 saw a `context_overrun` or `subagent_prompt_overrun` stall. Incremented by Phase 0's replan procedure before each retry. Each replan tightens the per-task budget by halving (floored at 40K) — see `recovery.md` "Budget floor guard" for the `target_budget = max(40000, int(75000 / (2 ** (replan_count - 1))))` schedule. Phase 0 PAUSEs only when `replan_count > 5` AND the same task keeps aborting (genuinely execution-overflowing, not capability-bound). Reset to 0 by Phase 9 step 10 when the PRD completes. Absent or 0 means the current PRD has not been replanned. |
| `work_start_sha` | string? | Git `HEAD` SHA captured at Phase 3 start, immediately before `/work` is dispatched. Bounds the commit range `work_start_sha..HEAD` produced by this PRD's `/work` dispatches — read by Phase 9 step 1's regrouping procedure (remote guard, granularity assessment, cherry-pick rewrite, conflict-safe abort). Captured once per PRD; in a multi-PRD batch each PRD overwrites it with current HEAD at Phase 3 start, so ranges never overlap. Cleared by Phase 9 step 10 on PRD-to-PRD reset. Optional: absent on plans created before this field was introduced, and on PRDs where Phase 3 has not yet run. |
| `regroup_outcome` | string? | One of the four outcome lines emitted by Phase 9 step 1's regrouping procedure: `regrouped: N -> M commits`, `skipped: commits already well-grouped`, `skipped: remote guard (commits already on remote)`, or `skipped: cherry-pick conflict, history left untouched`. Written by Phase 9 step 1 once the outcome is determined; read by Phase 9 step 7 and rendered as the `- Regroup:` bullet in the per-PRD batch report section (see `references/batch-report-format.md`). Cleared by Phase 9 step 10 on PRD-to-PRD reset. Optional: absent on plans created before this field was introduced, and on PRDs where Phase 9 has not yet run. |
| `context_window` | int? | Context window (tokens) of the model the current session launched on. Written by `autoclaude` (`_autoclaude_pick_model`) before each launch: `200000` for the Sonnet 4.6 Work tier, `1000000` for Opus. Read by `autopilot_context_cap_hook.py` to size the Work-phase context cap — window ≥ 400000 → 500K cap, otherwise 150K (the cap must stay below native auto-compact, which fires ~165K on a 200K window). Absent → hook assumes the 150K standard-tier cap (conservative: capping a large-window session too low only over-triggers replan). |
| `rework_task_ids` | string[]? | Set by `/run-autopilot` Phase 6 (rework) to instruct `/work` to process only those task IDs at their escalated tier. Non-empty puts `/work` in rework mode (skip completed-not-flagged tasks; re-iterate the listed IDs). Cleared (set to `[]`) by `/run-autopilot` after the rework `/work` pass finishes. Empty/absent means full-plan dispatch — the default Phase 3 behavior. |
| `stall_reason` | object? | Signals a pending recovery action. Four shapes: `{"stalled": "oversized_task", "task": "<id>", "estimated_tokens": int}` (written by `/plan-tasks` — triggers a stall move to `dev/local/prds/stalled/`); `{"stalled": "context_overrun", "task": "<id>", "total_input_tokens": int}` (written by `autopilot_context_cap_hook.py` when a Work turn exceeds the context cap — triggers Phase 0's **replan procedure**, not a stall move; see `replan_count` and `/run-autopilot` Phase 0 "Handle Work-phase abort"); `{"stalled": "subagent_prompt_overrun", "task": "<id>", "prompt_bytes": int}` (written by `/work` Subagent Dispatch Budget when an assembled subagent prompt exceeds 50K after one trim pass — also triggers the replan procedure); `{"stalled": "escalation_exhausted", "task": "<id>"}` (written by `/run-autopilot` Phase 6 when a task at tier `opus` fails rework — Phase 6 performs its own stall move inline). **Merged** (not replacing) into state by the writer, then **cleared** by `/run-autopilot`. Lifecycle handoff: Phase 2 handles `oversized_task` inline with a stall move; Phase 0 of the next session handles `context_overrun` and `subagent_prompt_overrun` via the replan procedure (no stall move — the PRD stays in `wip/`, planning re-runs with `replan-context.md`); Phase 6 handles `escalation_exhausted` inline (it owns the rework path and does its own move + clear before signaling — Phase 0 should never see this in normal operation, and treats it as crash recovery if it does). Absent in normal operation. |
| `review_cycles` | object[] | History of each review cycle. Each entry: `{"cycle": int, "review_file": "<path>", "agents": {"alice": "...", "bob": "...", "carl": "...", "diana": "..."}, "issues_found": int, "follow_up_tasks": int, "deferred": int, "recurring_issues": string[]}`. Cycles 3+ may also carry `decision_gate`, `rework_commits`, `rework_notes`, `cycle3_fix_audit`, `test_run` written by user-override paths (see live state for examples). |
| `review_cycles[].recurring_issues` | string[] | Issue descriptions that appeared in a previous cycle |
| `autonomous_decisions` | object[] | Decisions made without user input. May include optional `research` field for research-backed decisions. |
| `deferred_decisions` | object[] | Decisions requiring user input. May include optional `research` field when research was attempted but inconclusive. |
| `doubts` | object[] | Findings from doubt review: `{"description": "...", "category": "fix\|verify\|known", "justification?": "...", "status": "pending\|resolved"}`. `justification` required for `known` items (why it can't be fixed in scope). Empty array on fresh state. |
| `needs_attention` | bool | Dashboard flag. Set to `true` by `~/.claude/hooks/set-pidash-attention.py` (Notification hook for permission prompts) and cleared to `false` by `~/.claude/hooks/clear-pidash-attention.py` (PostToolUse). Not written by `/run-autopilot` directly; included here so the dashboard can read a complete state object. |
| `batch` | object? | Tracks completed PRDs across sessions |
| `batch.id` | string | Batch ID: `yyyymmddHHMM` timestamp of first execution |
| `batch.mode` | string | Always `"autopilot"` |
| `batch.completed_prds` | object[] | PRDs finished so far: `{"filename", "cycles", "autonomous_decisions", "escalated_decisions"}` |
| `batch.catchup_completed_at` | string? | ISO 8601 UTC timestamp recorded when the most recent full `/catchup` invocation in this batch completed. Read by Phase 1 "Batch cache check": if present, < 4h old, AND `batch.catchup_head_sha` matches current HEAD, Phase 1 runs a delta refresh instead of full catchup. Written by Phase 1 after full catchup completes. Preserved by Phase 9 step 10 across PRD-to-PRD state resets so subsequent PRDs in the same batch can reuse the cache. Absent on first PRD of a batch and on plans that never ran full catchup. |
| `batch.catchup_head_sha` | string? | Git HEAD SHA captured at the moment full `/catchup` completed in this batch. Paired with `catchup_completed_at` for the Phase 1 cache check. Written and preserved on the same lifecycle as `catchup_completed_at`. |

**Note on PRD 00025:** `tasks[].model`, `tasks[].attempts[]`, and `rework_task_ids[]` are active fields written and read by `/plan-tasks` (Tier classifier), `/work` (per-task model dispatch + attempt logging + rework-mode iteration), and `/run-autopilot` Phase 6 (review-driven tier escalation).

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

Written at Phase 9 step 6. This is the single source of truth for batch-end review. Includes:
- `deferred_decision` — issues that failed research or were deferred for other reasons
- `doubt` — unresolved findings from doubt review (KNOWN items with justification)
- `autonomous_research` — research-backed decisions made autonomously (for user awareness at batch end)

Each entry preserves the full `research` field when available, so evidence is readable at batch-end review even after per-PRD state is cleared. Not deleted by autopilot - left for user review.

## Skip Logic

Used to determine which phases to skip:

| Phase | Skip if |
|-------|---------|
| catchup | `"catchup"` in `phases_completed` |
| planning | `TaskList` returns pending or completed tasks (evaluate **after** hydrating from `state.tasks` — see SKILL.md Phase 2) |
| work | All tasks completed, none pending (evaluate **after** hydrating from `state.tasks` — see SKILL.md Phase 3) |
| review | Review file exists for current cycle in `dev/local/reviews/` |
| blind-review | `"blind-review"` in `phases_completed` |
| doubt-review | `"doubt-review"` in `phases_completed` |
