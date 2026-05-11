# State Schema

State file location: `dev/local/autopilot/state.json`

## Schema

```json
{
  "prd": {
    "filename": "00004-feature-x.md",
    "path": "dev/local/prds/wip/00004-feature-x.md",
    "name": "00004-feature-x"
  },
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
    {"task_id": "task-uuid-7", "turn": 27, "total_input_tokens": 192340, "cause": "context_overrun"}
  ],
  "review_cycles": [
    {
      "cycle": 1,
      "issue_count": 5,
      "severity": { "critical": 0, "high": 1, "medium": 3, "low": 1 },
      "auto_fixed": 3,
      "escalated": 1,
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
    ]
  },
  "started_at": "2026-03-16T10:00:00Z",
  "updated_at": "2026-03-16T10:30:00Z"
}
```

## Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `prd.filename` | string | PRD filename without path |
| `prd.path` | string | Relative path from project root |
| `prd.name` | string | Filename without extension (used in dashboard) |
| `phase` | enum | Current phase: `prd-selection`, `catchup`, `planning`, `work`, `review`, `decision-gate`, `rework`, `blind-review`, `doubt-review`, `done`, `paused` |
| `next_phase` | string | Phase the next iteration of `/run-autopilot` will run. Written by `/run-autopilot` immediately before the `signal` file. Read by `autoclaude` to pick `--model` for the next launch. Empty string means "no preference; consumer defaults to Opus." |
| `catchup_mode` | enum | `"run"` (default), `"skip"` (PRD frontmatter requested skip), or `"skipped"` (Phase 1 was bypassed for this PRD). Set at Phase 0 from PRD frontmatter `catchup:`; defaults to `"run"` on missing/malformed frontmatter. |
| `phases_completed` | string[] | Phases finished this session |
| `cycle` | int | Current review-rework cycle (starts at 1) |
| `tasks_total` | int | Total task count from TaskList (pending + in_progress + completed) |
| `tasks_completed` | int | Number of completed tasks from TaskList |
| `tasks` | object[] | Task list from TaskList: `{"id": "<task-id>", "name": "...", "status": "pending\|in_progress\|completed", "model"?: "haiku\|sonnet\|opus", "attempts"?: object[]}`. Include `id` — a PostToolUse hook uses it to sync status changes automatically. |
| `tasks[].model` | enum? | Optional per-task model tier: `"haiku"`, `"sonnet"`, `"opus"`. Reserved for PRD 00025 (per-task model tier). Unset in this PRD; `/work` inherits the session model when absent. |
| `tasks[].attempts` | object[]? | Optional per-task execution log: `{"attempt": int, "model": string, "outcome": "completed"\|"aborted"\|"review_flagged"\|"rework_failed", "review_cycle": int\|null, "cause": string\|null}`. Records each Work pass on the task. Rework reads the last entry's model to determine the next tier. Reserved for PRD 00025; not written in this PRD. |
| `task_aborts` | object[] | Appended by `autopilot_context_cap_hook.py` when context exceeds 180K during Work phase: `{"task_id": string, "turn": int, "total_input_tokens": int, "cause": "context_overrun"\|"subagent_prompt_overrun"}`. Empty array on fresh state. |
| `review_cycles` | object[] | History of each review cycle |
| `review_cycles[].recurring_issues` | string[] | Issue descriptions that appeared in a previous cycle |
| `autonomous_decisions` | object[] | Decisions made without user input. May include optional `research` field for research-backed decisions. |
| `deferred_decisions` | object[] | Decisions requiring user input. May include optional `research` field when research was attempted but inconclusive. |
| `doubts` | object[] | Findings from doubt review: `{"description": "...", "category": "fix\|verify\|known", "justification?": "...", "status": "pending\|resolved"}`. `justification` required for `known` items (why it can't be fixed in scope). |
| `batch` | object? | Tracks completed PRDs across sessions |
| `batch.id` | string | Batch ID: `yyyymmddHHMM` timestamp of first execution |
| `batch.mode` | string | Always `"autopilot"` |
| `batch.completed_prds` | object[] | PRDs finished so far: `{"filename", "cycles", "autonomous_decisions", "escalated_decisions"}` |
| `started_at` | ISO 8601 | Session start time |
| `updated_at` | ISO 8601 | Last state change time |

**Note on PRD 00025 reservation:** `tasks[].model` and `tasks[].attempts[]` are reserved by PRD 00024 for PRD 00025 (per-task model tier). `/plan-tasks` and `/work` do not read or write these fields in this PRD — `/work` inherits the session model unset. Landing the schema fields now means PRD 00025 lands additively: it adds a `/plan-tasks` classifier that writes `task.model`, and a `/work` dispatcher that reads it. No re-work of the autopilot loop or `autoclaude` is needed at that point.

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

Written at Phase 9 step 5. This is the single source of truth for batch-end review. Includes:
- `deferred_decision` — issues that failed research or were deferred for other reasons
- `doubt` — unresolved findings from doubt review (KNOWN items with justification)
- `autonomous_research` — research-backed decisions made autonomously (for user awareness at batch end)

Each entry preserves the full `research` field when available, so evidence is readable at batch-end review even after per-PRD state is cleared. Not deleted by autopilot - left for user review.

## Skip Logic

Used to determine which phases to skip:

| Phase | Skip if |
|-------|---------|
| catchup | `"catchup"` in `phases_completed` |
| planning | `TaskList` returns pending or completed tasks |
| work | All tasks completed, none pending |
| review | Review file exists for current cycle in `dev/local/reviews/` |
| blind-review | `"blind-review"` in `phases_completed` |
| doubt-review | `"doubt-review"` in `phases_completed` |
