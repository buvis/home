#!/bin/bash
# Run Gemini via copilot CLI

set -e

MODEL="gemini-3-pro-preview"
MODE="prompt"  # prompt, interactive, resume
ALLOW_TOOLS=""
ALLOW_ALL=""
SILENT=""
ADD_DIRS=()
PROMPT=""

usage() {
    echo "Usage: $0 [options] [prompt]"
    echo ""
    echo "Options:"
    echo "  -i, --interactive      Interactive mode with initial prompt"
    echo "  -a, --allow-tools      Auto-approve tool use"
    echo "  -y, --yolo             Full permissions (allow-all)"
    echo "  -s, --silent           Silent mode (clean output for scripting)"
    echo "  -d, --dir DIR          Allow access to directory (can repeat)"
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

# Build and run command
case $MODE in
    resume)
        if [ -n "$PROMPT" ]; then
            copilot --model "$MODEL" --resume "$PROMPT"
        else
            copilot --model "$MODEL" --resume
        fi
        ;;
    continue)
        copilot --model "$MODEL" --continue
        ;;
    interactive)
        if [ -z "$PROMPT" ]; then
            echo "ERROR: Prompt required for interactive mode"
            usage
            exit 1
        fi
        copilot --model "$MODEL" $ALLOW_TOOLS $ALLOW_ALL $SILENT "${ADD_DIRS[@]}" -i "$PROMPT"
        ;;
    prompt)
        if [ -z "$PROMPT" ]; then
            echo "ERROR: Prompt required"
            usage
            exit 1
        fi
        copilot --model "$MODEL" $ALLOW_TOOLS $ALLOW_ALL $SILENT "${ADD_DIRS[@]}" -p "$PROMPT"
        ;;
esac
