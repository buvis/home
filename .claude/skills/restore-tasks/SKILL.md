---
name: restore-tasks
description: Restore tasks from a previous Claude Code session into the current session. Use when user wants to recover, restore, or load tasks from a past session, or when they mention tasks were lost after /clear or session restart. Triggers on "restore tasks", "load tasks", "recover tasks", "get my tasks back", "tasks from previous session".
---

# Restore Tasks

Recover persisted tasks from previous sessions.

## Storage Structure

```
~/.claude/tasks/<session-id>/     # Task JSON files (1.json, 2.json...)
~/.claude/projects/<encoded-path>/<session-id>.jsonl  # Session data
```

Path encoding: `/Users/bob/foo` → `-Users-bob-foo`

## Workflow

### 1. List available sessions

```bash
./scripts/list-task-sessions.sh
```

Shows sessions with tasks for current project (ID, task count, summary).

### 2. User selects session

Present the list and ask user to pick by ID or summary match.

### 3. Load tasks

```bash
./scripts/dump-tasks.sh <session-id>
```

Returns JSON array of task objects.

### 4. Recreate tasks

For each task in the JSON:

1. Call `TaskCreate` with:
   - `subject`: task.subject
   - `description`: task.description
   - `activeForm`: task.activeForm

2. After all created, call `TaskUpdate` for each with `blockedBy` dependencies:
   - `taskId`: new task ID (matches original)
   - `addBlockedBy`: task.blockedBy array

### 5. Confirm

Call `TaskList` to show restored tasks.

## Task JSON Schema

```json
{
  "id": "1",
  "subject": "Task title",
  "description": "Full description",
  "activeForm": "Present continuous form",
  "status": "pending|in_progress|completed",
  "blocks": ["2", "3"],
  "blockedBy": ["4"]
}
```

## Error Handling

| Situation | Action |
|-----------|--------|
| No project data | Report "No Claude data for this directory" |
| No task sessions | Report "No previous sessions with tasks found" |
| Session not found | Ask user to verify session ID |
