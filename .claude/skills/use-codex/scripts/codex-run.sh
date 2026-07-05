#!/bin/bash
# Run a Codex agent non-interactively. Prefers the native `codex` CLI;
# falls back to `copilot`. Every call is a fresh, one-shot run - there is
# no interactive or resume mode (this helper feeds automated dispatch).

set -eo pipefail

# Ensure mise-managed tools (like copilot) are on PATH
if command -v mise &>/dev/null; then
    PATH="$(mise env -s bash 2>/dev/null | sed -n "s/^export PATH='\\(.*\\)'/\\1/p"):$PATH"
fi

# Backend selection: the native codex CLI is preferred (OpenAI ChatGPT
# subscription, no per-request billing multiplier). copilot is the fallback
# when codex is not installed.
if command -v codex &>/dev/null; then
    BACKEND="codex"
elif command -v copilot &>/dev/null; then
    BACKEND="copilot"
else
    echo "ERROR: neither 'codex' nor 'copilot' CLI found on PATH" >&2
    exit 1
fi

# Curated 1x-multiplier default for the copilot backend only. Picking the
# "highest-versioned" model silently lands on premium tiers (gpt-5.5 burned
# 25% of monthly Copilot quota in one run). Multipliers are not exposed via
# the CLI, so we hardcode Copilot's own recommended default and require
# -m/--model to opt into a higher-multiplier tier. The codex backend has no
# multiplier, so it uses codex's own configured default unless -m is given.
DEFAULT_COPILOT_MODEL="gpt-5.4"
MODEL=""
MODEL_SET=""
ALLOW_TOOLS=""
ALLOW_ALL=""
SILENT=""
ADD_DIRS=()    # both CLIs accept --add-dir DIR
PROMPT=""
PROMPT_FILE=""

usage() {
    echo "Usage: $0 [options] [prompt]"
    echo ""
    echo "Backend: $BACKEND (codex preferred, copilot fallback)."
    echo "copilot default model: $DEFAULT_COPILOT_MODEL (1x multiplier)."
    echo "Use -m to override; on copilot a higher-multiplier model may apply."
    echo ""
    echo "Runs are non-interactive and one-shot. There is no resume mode."
    echo ""
    echo "Options:"
    echo "  -m, --model MODEL      Override model (copilot default: $DEFAULT_COPILOT_MODEL)"
    echo "  -a, --allow-tools      Auto-approve tool use (codex: --sandbox workspace-write)"
    echo "  -y, --yolo             Full permissions (codex: bypass approvals + sandbox)"
    echo "  -s, --silent           Silent mode (copilot only; ignored on codex)"
    echo "  -d, --dir DIR          Allow access to directory (can repeat)"
    echo "  -f, --file FILE        Read prompt from file"
    echo "  -o, --output FILE      Write output to file (via tee)"
    echo "  --emit-thread-id FILE  Capture codex thread id from the JSON path (codex only; requires -o)"
    echo "  -h, --help             Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 'Analyze the codebase'"
    echo "  $0 -a -f /tmp/prompt.txt"
    echo "  $0 -y -f /tmp/prompt.txt"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -m|--model)
            MODEL="$2"
            MODEL_SET=1
            shift 2
            ;;
        -a|--allow-tools)
            ALLOW_TOOLS=1
            shift
            ;;
        -y|--yolo)
            ALLOW_ALL=1
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
        --emit-thread-id)
            EMIT_THREAD_FILE="$2"
            shift 2
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

if [ -z "$PROMPT" ]; then
    echo "ERROR: Prompt required"
    usage
    exit 1
fi

if [ -n "${EMIT_THREAD_FILE:-}" ] && [ -z "${OUTPUT_FILE:-}" ]; then
    echo "ERROR: --emit-thread-id requires -o" >&2
    exit 1
fi

# Build and run command
run_cmd() {
    if [ -n "$OUTPUT_FILE" ]; then
        "$@" 2>&1 | tee "$OUTPUT_FILE"
    else
        "$@"
    fi
}

run_codex() {
    # Map permission flags to codex sandbox policy.
    local sandbox=()
    if [ -n "$ALLOW_ALL" ]; then
        sandbox=(--dangerously-bypass-approvals-and-sandbox)
    elif [ -n "$ALLOW_TOOLS" ]; then
        sandbox=(--sandbox workspace-write)
    else
        sandbox=(--sandbox read-only)
    fi

    local model=()
    [ -n "$MODEL_SET" ] && model=(-m "$MODEL")

    if [ -z "${EMIT_THREAD_FILE:-}" ]; then
        run_cmd codex exec --skip-git-repo-check "${model[@]}" "${sandbox[@]}" "${ADD_DIRS[@]}" "$PROMPT" < /dev/null
        return
    fi

    # --emit-thread-id JSON path: codex streams JSONL events on stdout, the
    # review text lands in --output-last-message (== -o's file), and the
    # thread id comes from the thread.started event. Truncate any stale
    # capture first so a run with no thread.started leaves no old id behind.
    : > "$EMIT_THREAD_FILE"

    local line type tid codex_exit
    set +e
    codex exec --skip-git-repo-check "${model[@]}" "${sandbox[@]}" "${ADD_DIRS[@]}" \
        --json --output-last-message "$OUTPUT_FILE" "$PROMPT" < /dev/null | \
    while IFS= read -r line; do
        case "$line" in
            *'"type":"'*)
                type="${line#*\"type\":\"}"
                type="${type%%\"*}"
                ;;
            *)
                type="?"
                ;;
        esac
        if [ "$type" = "thread.started" ]; then
            case "$line" in
                *'"thread_id":"'*)
                    tid="${line#*\"thread_id\":\"}"
                    tid="${tid%%\"*}"
                    printf '%s' "$tid" > "$EMIT_THREAD_FILE"
                    ;;
            esac
        fi
        echo "codex-event: $type" >&2
    done
    codex_exit=$?
    set -e

    if [ ! -s "$EMIT_THREAD_FILE" ]; then
        echo "WARNING: no thread.started event; thread id not captured" >&2
    fi

    if [ "$codex_exit" -eq 0 ]; then
        if [ -s "$OUTPUT_FILE" ]; then
            cat "$OUTPUT_FILE"
        else
            echo "WARNING: codex exited 0 but wrote no output" >&2
        fi
    fi

    return "$codex_exit"
}

run_copilot() {
    if [ -n "${EMIT_THREAD_FILE:-}" ]; then
        echo "WARNING: --emit-thread-id requires the codex backend; running one-shot" >&2
    fi

    local model="${MODEL:-$DEFAULT_COPILOT_MODEL}"
    local allow_tools=""
    local allow_all=""
    [ -n "$ALLOW_TOOLS" ] && allow_tools="--allow-all-tools"
    [ -n "$ALLOW_ALL" ] && allow_all="--allow-all"

    run_cmd copilot --model "$model" $allow_tools $allow_all $SILENT "${ADD_DIRS[@]}" -p "$PROMPT"
}

if [ "$BACKEND" = "codex" ]; then
    run_codex
else
    run_copilot
fi
