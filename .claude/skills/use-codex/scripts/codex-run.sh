#!/bin/bash
# Run Codex model via copilot CLI

set -e

FALLBACK_MODEL="gpt-5.3-codex"

detect_model() {
    # Pick latest gpt-X.Y-codex (base only, no -mini/-max suffix)
    copilot --help 2>&1 | grep -oE 'gpt-[0-9]+\.[0-9]+-codex"' | tr -d '"' | sort -t. -k1,1rn -k2,2rn | head -1
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
