#!/bin/bash
# List sessions that have persisted tasks for the current project

set -e

CLAUDE_DIR="$HOME/.claude"
TASKS_DIR="$CLAUDE_DIR/tasks"
PROJECTS_DIR="$CLAUDE_DIR/projects"

# Encode current path: /Users/bob/github.com/foo -> -Users-bob-github-com-foo
encode_path() {
    echo "$1" | sed 's|^/|-|' | tr '/.' '-'
}

# Get current project path
PROJECT_PATH="${1:-$(pwd)}"
ENCODED_PATH=$(encode_path "$PROJECT_PATH")
PROJECT_DIR="$PROJECTS_DIR/$ENCODED_PATH"

if [[ ! -d "$PROJECT_DIR" ]]; then
    echo "No Claude project data found for: $PROJECT_PATH" >&2
    exit 1
fi

if [[ ! -d "$TASKS_DIR" ]]; then
    echo "No tasks directory found" >&2
    exit 1
fi

# Get all session IDs that have task directories
echo "Sessions with tasks for: $PROJECT_PATH"
echo "---"

found=0
for session_dir in "$TASKS_DIR"/*/; do
    [[ -d "$session_dir" ]] || continue
    session_id=$(basename "$session_dir")

    # Check if this session belongs to current project
    if [[ -f "$PROJECT_DIR/${session_id}.jsonl" ]]; then
        found=1
        task_count=$(ls -1 "$session_dir"/*.json 2>/dev/null | wc -l | tr -d ' ')

        # Try to get session summary from sessions-index.json
        summary=""
        if [[ -f "$PROJECT_DIR/sessions-index.json" ]]; then
            summary=$(grep -A5 "\"sessionId\": \"$session_id\"" "$PROJECT_DIR/sessions-index.json" 2>/dev/null | grep '"summary"' | head -1 | sed 's/.*"summary": "\([^"]*\)".*/\1/' || true)
        fi

        echo "ID: $session_id"
        echo "Tasks: $task_count"
        [[ -n "$summary" ]] && echo "Summary: $summary"
        echo "---"
    fi
done

if [[ $found -eq 0 ]]; then
    echo "No sessions with tasks found for this project"
    exit 1
fi
