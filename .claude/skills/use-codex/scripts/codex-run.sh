#!/bin/bash
# Run Codex model via copilot CLI

set -eo pipefail

# Ensure mise-managed tools (like copilot) are on PATH
if command -v mise &>/dev/null; then
    PATH="$(mise env -s bash 2>/dev/null | sed -n "s/^export PATH='\\(.*\\)'/\\1/p"):$PATH"
fi

FALLBACK_MODEL="gpt-5.5"

# Pull the highest-versioned base gpt-X.Y model (no -codex/-mini/-nano suffix)
# from the copilot SDK type definitions. Quoted match restricts results to
# entries actually listed in SUPPORTED_MODELS / HELP_VISIBLE_MODELS rather
# than passing mentions in code comments.
MODEL_PATTERN='"gpt-[0-9]+\.[0-9]+"'

detect_model() {
    local src
    for src in $(model_sources); do
        [ -f "$src" ] || continue
        local model
        model=$(grep -oE "$MODEL_PATTERN" "$src" | tr -d '"' | sort -uV | tail -1)
        if [ -n "$model" ]; then
            printf '%s\n' "$model"
            return
        fi
    done
}

# Emit candidate SDK file paths in priority order. The auto-update cache
# under ~/Library/Caches/copilot is usually ahead of the npm-installed copy,
# so check it first.
model_sources() {
    local cache_dir="$HOME/Library/Caches/copilot/pkg/universal"
    if [ -d "$cache_dir" ]; then
        local latest
        latest=$(ls -1 "$cache_dir" 2>/dev/null \
            | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' \
            | sort -V | tail -1)
        [ -n "$latest" ] && printf '%s\n' "$cache_dir/$latest/sdk/index.d.ts"
    fi

    local copilot_bin real_bin npm_pkg
    copilot_bin=$(command -v copilot 2>/dev/null) || return
    real_bin=$(readlink -f "$copilot_bin" 2>/dev/null || echo "$copilot_bin")
    npm_pkg=$(dirname "$real_bin")
    while [ "$npm_pkg" != "/" ] && [ ! -f "$npm_pkg/package.json" ]; do
        npm_pkg=$(dirname "$npm_pkg")
    done
    [ -d "$npm_pkg" ] || return
    printf '%s\n' "$npm_pkg/sdk/index.d.ts" "$npm_pkg/app.js"
}

MODEL=$(detect_model)
if [ -z "$MODEL" ]; then
    echo "WARN: Could not detect latest codex model, using $FALLBACK_MODEL" >&2
    MODEL="$FALLBACK_MODEL"
fi
MODE="prompt"  # prompt, interactive, resume, continue
ALLOW_TOOLS=""
ALLOW_ALL=""
SILENT=""
ADD_DIRS=()
PROMPT=""
PROMPT_FILE=""

usage() {
    echo "Usage: $0 [options] [prompt]"
    echo ""
    echo "Options:"
    echo "  -i, --interactive      Interactive mode with initial prompt"
    echo "  -a, --allow-tools      Auto-approve tool use"
    echo "  -y, --yolo             Full permissions (allow-all)"
    echo "  -s, --silent           Silent mode (clean output for scripting)"
    echo "  -d, --dir DIR          Allow access to directory (can repeat)"
    echo "  -f, --file FILE        Read prompt from file"
    echo "  -o, --output FILE      Write output to file (via tee)"
    echo "  -r, --resume [ID]      Resume session (optionally specify ID)"
    echo "  -c, --continue         Resume most recent session"
    echo "  -h, --help             Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 'Analyze the codebase'"
    echo "  $0 -a 'Fix the bug in auth.ts'"
    echo "  $0 -y 'Refactor the module'"
    echo "  $0 -r"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -i|--interactive)
            MODE="interactive"
            shift
            ;;
        -a|--allow-tools)
            ALLOW_TOOLS="--allow-all-tools"
            shift
            ;;
        -y|--yolo)
            ALLOW_ALL="--allow-all"
            shift
            ;;
        -s|--silent)
            SILENT="-s"
            shift
            ;;
        -d|--dir)
            ADD_DIRS+=("--add-dir" "$2")
            shift 2
            ;;
        -f|--file)
            PROMPT_FILE="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        -r|--resume)
            MODE="resume"
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                PROMPT="$2"
                shift
            fi
            shift
            ;;
        -c|--continue)
            MODE="continue"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            PROMPT="$1"
            shift
            ;;
    esac
done

# Read prompt from file if specified
if [ -n "$PROMPT_FILE" ]; then
    if [ ! -f "$PROMPT_FILE" ]; then
        echo "ERROR: Prompt file not found: $PROMPT_FILE"
        exit 1
    fi
    PROMPT=$(cat "$PROMPT_FILE")
fi

# Build and run command
run_cmd() {
    if [ -n "$OUTPUT_FILE" ]; then
        "$@" 2>&1 | tee "$OUTPUT_FILE"
    else
        "$@"
    fi
}

case $MODE in
    resume)
        if [ -n "$PROMPT" ]; then
            run_cmd copilot --model "$MODEL" --resume "$PROMPT"
        else
            run_cmd copilot --model "$MODEL" --resume
        fi
        ;;
    continue)
        run_cmd copilot --model "$MODEL" --continue
        ;;
    interactive)
        if [ -z "$PROMPT" ]; then
            echo "ERROR: Prompt required for interactive mode"
            usage
            exit 1
        fi
        run_cmd copilot --model "$MODEL" $ALLOW_TOOLS $ALLOW_ALL $SILENT "${ADD_DIRS[@]}" -i "$PROMPT"
        ;;
    prompt)
        if [ -z "$PROMPT" ]; then
            echo "ERROR: Prompt required"
            usage
            exit 1
        fi
        run_cmd copilot --model "$MODEL" $ALLOW_TOOLS $ALLOW_ALL $SILENT "${ADD_DIRS[@]}" -p "$PROMPT"
        ;;
esac
