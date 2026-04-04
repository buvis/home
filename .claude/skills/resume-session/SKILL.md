---
name: resume-session
description: Use when starting a new session and want to pick up where a previous session left off. Loads saved session state and presents a briefing without starting work. Triggers on "resume session", "resume", "load session", "pick up where I left off", "continue session", "what was I working on".
argument-hint: "[session-file-path or YYYY-MM-DD]"
---

# Resume Session

Load a saved session file and present a structured briefing. Do NOT start working.

## Workflow

### 1. Find session file

**If argument provided:**
- If it's a full path, use it directly
- If it's a date (YYYY-MM-DD), find matching files via `Glob("~/.claude/session-data/YYYY-MM-DD-*.md")`

**If no argument:**
- Find most recent: `Glob("~/.claude/session-data/*.md")`, pick the latest by modification time

**If multiple matches:** Present options using AskUserQuestion with file basename and modification date.

**If no session files found:** Report "No saved sessions found. Use /save-session to create one."

### 2. Read session file

Read the full file content.

### 3. Check staleness

If the session file's date is older than 7 days, warn:
```
Warning: This session is from {date} ({n} days ago). Context may be outdated.
```

### 4. Check referenced files

Scan the session content for file paths (patterns like `~/`, `/Users/`, `src/`, `./`). For each path found, check if the file still exists using Glob. If any are missing, warn:
```
Warning: These files referenced in the session no longer exist:
- {path}
- {path}
```

### 5. Present briefing

Print each section from the session file with clear headers. Add a separator between sections for readability.

End with:
```
Ready to continue. What would you like to do?
```

Do NOT start working. Wait for instruction.

## Common Mistakes

- Starting work immediately after presenting the briefing
- Skipping the staleness check
- Not checking if referenced files still exist
