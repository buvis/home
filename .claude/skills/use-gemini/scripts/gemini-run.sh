#!/bin/bash
# Run Gemini via the native Gemini CLI (Google).

set -eo pipefail

# Ensure mise-managed tools (gemini itself, plus build/test tools Gemini may
# invoke) are on PATH. Matches codex-run.sh / sonnet-run.sh.
if command -v mise &>/dev/null; then
    PATH="$(mise env -s bash 2>/dev/null | sed -n "s/^export PATH='\\(.*\\)'/\\1/p"):$PATH"
fi

# Resolve the gemini binary. It is mise-managed and may not be on PATH.
GEMINI_BIN="$(command -v gemini 2>/dev/null || true)"
if [ -z "$GEMINI_BIN" ] && command -v mise &>/dev/null; then
    GEMINI_BIN="$(mise which gemini 2>/dev/null || true)"
fi
if [ -z "$GEMINI_BIN" ]; then
    echo "ERROR: gemini CLI not found." >&2
    echo "Install it (e.g. 'mise use -g npm:@google/gemini-cli') and retry." >&2
    exit 1
fi

MODEL=""          # empty = CLI default
MODE="prompt"     # prompt, interactive, resume, continue
APPROVAL=""       # --approval-mode value (auto_edit | yolo)
ADD_DIRS=()
PROMPT=""
PROMPT_FILE=""
OUTPUT_FILE=""
RESUME_ID=""

usage() {
    echo "Usage: $0 [options] [prompt]"
    echo ""
    echo "Runs the native Gemini CLI. With no -m, the CLI picks its default model."
    echo ""
    echo "Options:"
    echo "  -m, --model MODEL      Override model (default: CLI default)"
    echo "  -i, --interactive      Interactive mode with initial prompt"
    echo "  -a, --allow-tools      Auto-approve edit tools (--approval-mode auto_edit)"
    echo "  -y, --yolo             Auto-approve all tools (--approval-mode yolo)"
    echo "  -s, --silent           Accepted for compatibility; -p output is already clean"
    echo "  -d, --dir DIR          Include extra directory in the workspace (can repeat)"
    echo "  -f, --file FILE        Read prompt from file"
    echo "  -o, --output FILE      Write output to file (via tee)"
    echo "  -r, --resume [ID]      Resume session ('latest' or index; default: latest)"
    echo "  -c, --continue         Resume most recent session"
    echo "  -h, --help             Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 'Analyze the codebase'"
    echo "  $0 -a -f /tmp/prompt.txt"
    echo "  $0 -y 'Refactor the module'"
    echo "  $0 -r"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -m|--model)
            MODEL="$2"
            shift 2
            ;;
        -i|--interactive)
            MODE="interactive"
            shift
            ;;
        -a|--allow-tools)
            APPROVAL="auto_edit"
            shift
            ;;
        -y|--yolo)
            APPROVAL="yolo"
            shift
            ;;
        -s|--silent)
            shift
            ;;
        -d|--dir)
            ADD_DIRS+=("--include-directories" "$2")
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
                RESUME_ID="$2"
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
        echo "ERROR: Prompt file not found: $PROMPT_FILE" >&2
        exit 1
    fi
    PROMPT=$(cat "$PROMPT_FILE")
fi

# Flags common to every invocation. --skip-trust avoids the workspace-trust
# prompt blocking headless (-p) runs.
COMMON=(--skip-trust)
[ -n "$MODEL" ] && COMMON+=(-m "$MODEL")
[ -n "$APPROVAL" ] && COMMON+=(--approval-mode "$APPROVAL")
COMMON+=("${ADD_DIRS[@]}")

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
        ID="${RESUME_ID:-latest}"
        if [ -n "$PROMPT" ]; then
            run_cmd "$GEMINI_BIN" "${COMMON[@]}" --resume "$ID" -p "$PROMPT"
        else
            run_cmd "$GEMINI_BIN" "${COMMON[@]}" --resume "$ID"
        fi
        ;;
    continue)
        run_cmd "$GEMINI_BIN" "${COMMON[@]}" --resume latest
        ;;
    interactive)
        if [ -z "$PROMPT" ]; then
            echo "ERROR: Prompt required for interactive mode" >&2
            usage
            exit 1
        fi
        run_cmd "$GEMINI_BIN" "${COMMON[@]}" -i "$PROMPT"
        ;;
    prompt)
        if [ -z "$PROMPT" ]; then
            echo "ERROR: Prompt required" >&2
            usage
            exit 1
        fi
        run_cmd "$GEMINI_BIN" "${COMMON[@]}" -p "$PROMPT"
        ;;
esac
