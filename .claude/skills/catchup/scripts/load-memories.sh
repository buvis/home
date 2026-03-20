#!/bin/bash
# Load project memories from Claude Code memory system
# Outputs all memory files for the current project, or nothing if none exist

set -e

MEMORY_DIR="$HOME/.claude/projects/$(pwd | tr '/.' '-')/memory"

if [ ! -d "$MEMORY_DIR" ]; then
    exit 0
fi

found=false
for f in "$MEMORY_DIR"/*.md; do
    [ -f "$f" ] || continue
    name=$(basename "$f")
    [ "$name" = "MEMORY.md" ] && continue
    found=true
    echo "--- $name ---"
    cat "$f"
    echo ""
done

if [ "$found" = false ]; then
    exit 0
fi
