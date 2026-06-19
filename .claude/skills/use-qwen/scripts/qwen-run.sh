#!/bin/bash
# Run a local Qwen model (served by llama.cpp) through the pi coding agent.

set -eo pipefail

# Ensure mise-managed tools (like pi) are on PATH.
if command -v mise &>/dev/null; then
    PATH="$(mise env -s bash 2>/dev/null | sed -n "s/^export PATH='\\(.*\\)'/\\1/p"):$PATH"
fi

# Local model served by llama.cpp - free to run, no API cost.
# qwen3-coder-30b-a3b cleared a 6-task agentic Rust eval on llama.cpp; the same
# model over Ollama failed (Ollama's qwen3coder tool-call XML parser mangles
# large edits). Serve via llama.cpp/LlamaBarn with `--jinja`. The model must be
# listed in ~/.pi/agent/models.json under the `llamacpp` provider.
DEFAULT_MODEL="unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q4_K_M"
MODEL="$DEFAULT_MODEL"
PROVIDER="llamacpp"
MODE="prompt"        # prompt, interactive, resume, continue
OUTPUT_MODE="text"   # text or json (pi --mode)
READ_ONLY=""
PROMPT=""
PROMPT_FILE=""
OUTPUT_FILE=""

usage() {
    echo "Usage: $0 [options] [prompt]"
    echo ""
    echo "Runs a local model (default: $DEFAULT_MODEL) via the pi agent + llama.cpp."
    echo "Local inference - no API cost. Requires a llama.cpp server running with the model loaded."
    echo ""
    echo "Options:"
    echo "  -m, --model MODEL    Override model (default: $DEFAULT_MODEL)"
    echo "  -i, --interactive    Interactive mode with initial prompt"
    echo "  -R, --read-only      Restrict to read-only tools (no file edits)"
    echo "  -j, --json           Emit a structured JSON event stream (pi --mode json)"
    echo "  -f, --file FILE      Read prompt from file"
    echo "  -o, --output FILE    Write output to file (via tee)"
    echo "  -r, --resume [ID]    Resume session (optionally a specific session id)"
    echo "  -c, --continue       Resume most recent session"
    echo "  -h, --help           Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 -f /tmp/qwen-prompt.txt"
    echo "  $0 -R -f /tmp/qwen-prompt.txt              # read-only analysis"
    echo "  $0 -j -o /tmp/result.jsonl -f /tmp/qwen-prompt.txt"
    echo "  $0 -m other-model -f /tmp/qwen-prompt.txt"
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
        -R|--read-only)
            READ_ONLY="1"
            shift
            ;;
        -j|--json)
            OUTPUT_MODE="json"
            shift
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

if ! command -v pi &>/dev/null; then
    echo "ERROR: 'pi' not found on PATH. Install via mise, then run 'mise reshim'."
    exit 1
fi

# Common pi arguments
ARGS=(--provider "$PROVIDER" --model "$MODEL" --mode "$OUTPUT_MODE")
if [ -n "$READ_ONLY" ]; then
    ARGS+=(--tools read,grep,find,ls)
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
            run_cmd pi "${ARGS[@]}" --session "$PROMPT"
        else
            run_cmd pi "${ARGS[@]}" --resume
        fi
        ;;
    continue)
        run_cmd pi "${ARGS[@]}" --continue
        ;;
    interactive)
        if [ -z "$PROMPT" ]; then
            echo "ERROR: Prompt required for interactive mode"
            usage
            exit 1
        fi
        run_cmd pi "${ARGS[@]}" "$PROMPT"
        ;;
    prompt)
        if [ -z "$PROMPT" ]; then
            echo "ERROR: Prompt required"
            usage
            exit 1
        fi
        run_cmd pi "${ARGS[@]}" -p "$PROMPT"
        ;;
esac
