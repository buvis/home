# State Schema

State file location: `.local/prd-cycle.json`

## Schema

```json
{
  "prd": {
    "filename": "00004-feature-x.md",
    "path": ".local/prds/wip/00004-feature-x.md",
    "name": "00004-feature-x"
  },
  "phase": "work",
  "phases_completed": ["catchup", "planning"],
  "cycle": 1,
  "tasks_total": 6,
  "tasks_completed": 2,
  "tasks": [
    {"name": "Add validation endpoint", "status": "completed"},
    {"name": "Update API types", "status": "completed"},
    {"name": "Write integration tests", "status": "in_progress"},
    {"name": "Update frontend form", "status": "pending"},
    {"name": "Add error handling", "status": "pending"},
    {"name": "Update docs", "status": "pending"}
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
    }
  ],
  "deferred_decisions": [
    {
      "cycle": 1,
      "issue": "API signature change needed",
      "severity": "high",
      "consensus": "3/3",
      "reason": "touches public API",
      "status": "pending"
    }
  ],
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
| `phase` | enum | Current phase: `prd-selection`, `catchup`, `planning`, `work`, `review`, `decision-gate`, `rework`, `done`, `paused` |
| `phases_completed` | string[] | Phases finished this session |
| `cycle` | int | Current review-rework cycle (starts at 1) |
| `tasks_total` | int | Total task count from TaskList (pending + in_progress + completed) |
| `tasks_completed` | int | Number of completed tasks from TaskList |
| `tasks` | object[] | Task list from TaskList: `{"name": "...", "status": "pending\|in_progress\|completed"}` |
| `review_cycles` | object[] | History of each review cycle |
| `review_cycles[].recurring_issues` | string[] | Issue descriptions that appeared in a previous cycle |
| `autonomous_decisions` | object[] | Decisions made without user input |
| `deferred_decisions` | object[] | Decisions requiring user input |
| `started_at` | ISO 8601 | Session start time |
| `updated_at` | ISO 8601 | Last state change time |

## Skip Logic

Used to determine which phases to skip:

| Phase | Skip if |
|-------|---------|
| catchup | `"catchup"` in `phases_completed` |
| planning | `TaskList` returns pending or completed tasks |
| work | All tasks completed, none pending |
| review | Review file exists for current cycle in `.local/reviews/` |
