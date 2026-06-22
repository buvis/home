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
# large edits). Serve via llama.cpp/LlamaBarn with `--jinja`.
#
# Provider/model are auto-detected from pi's config (~/.pi/agent/models.json):
# every provider is probed in ascending port order and the first one with a
# live server wins; the model id comes from that server's /v1/models. Override
# with --provider and/or -m. A config entry is NOT proof a server is up, so we
# probe rather than trust the lowest port blindly.
MODELS_JSON="${PI_CODING_AGENT_DIR:-$HOME/.pi/agent}/models.json"
MODEL=""             # empty = take whatever the live server reports
PROVIDER=""          # empty = auto-detect lowest live port
MODE="prompt"        # prompt, interactive, resume, continue
OUTPUT_MODE="text"   # text or json (pi --mode)
READ_ONLY=""
PROMPT=""
PROMPT_FILE=""
OUTPUT_FILE=""

usage() {
    echo "Usage: $0 [options] [prompt]"
    echo ""
    echo "Runs a local model via the pi agent + llama.cpp. Provider and model are"
    echo "auto-detected from $MODELS_JSON: providers are probed in ascending"
    echo "port order and the first with a live server wins."
    echo "Local inference - no API cost. Requires a llama.cpp server running with the model loaded."
    echo ""
    echo "Options:"
    echo "  -P, --provider NAME  Force a pi provider (default: lowest live port)"
    echo "  -m, --model MODEL    Force model id (default: whatever the live server reports)"
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
        -P|--provider)
            PROVIDER="$2"
            shift 2
            ;;
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

for tool in jq curl; do
    command -v "$tool" &>/dev/null || { echo "ERROR: '$tool' required for provider auto-detect."; exit 1; }
done
if [ ! -f "$MODELS_JSON" ]; then
    echo "ERROR: pi model config not found: $MODELS_JSON"
    exit 1
fi

# Ask a provider's llama-server for the id it's actually serving (empty if down).
probe_model() { curl -sf --max-time 2 "$1/models" 2>/dev/null | jq -r '.data[0].id // empty' 2>/dev/null; }

# Look up a provider's baseUrl from the config (empty if the provider is absent).
provider_base_url() { jq -r --arg p "$1" '.providers[$p].baseUrl // empty' "$MODELS_JSON"; }

if [ -n "$PROVIDER" ]; then
    BASE_URL="$(provider_base_url "$PROVIDER")"
    if [ -z "$BASE_URL" ]; then
        echo "ERROR: provider '$PROVIDER' not found in $MODELS_JSON"
        exit 1
    fi
    if [ -z "$MODEL" ]; then
        MODEL="$(probe_model "$BASE_URL")"
        [ -z "$MODEL" ] && { echo "ERROR: no server responding at $BASE_URL (provider $PROVIDER). Start llama-server or pass -m."; exit 1; }
    fi
else
    # Probe every provider in ascending port order; first live one wins.
    while IFS=$'\t' read -r _port name base_url; do
        [ -z "$base_url" ] && continue
        served="$(probe_model "$base_url")"
        if [ -n "$served" ]; then
            PROVIDER="$name"
            [ -z "$MODEL" ] && MODEL="$served"
            break
        fi
    done < <(jq -r '
        .providers | to_entries[]
        | [ ((.value.baseUrl // "") | capture(":(?<p>[0-9]+)").p // "0" | tonumber),
            .key, (.value.baseUrl // "") ] | @tsv
    ' "$MODELS_JSON" | sort -n)
    if [ -z "$PROVIDER" ]; then
        echo "ERROR: no llama-server responding on any provider in $MODELS_JSON. Start one (e.g. llama-server ... --port 8080)."
        exit 1
    fi
fi
echo "Using provider '$PROVIDER' model '$MODEL'" >&2

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
