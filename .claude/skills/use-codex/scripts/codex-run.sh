#!/bin/bash
# Build and run codex command with proper flags

set -e

# Defaults
MODEL="gpt-5.1-codex-mini"
EFFORT="medium"
SANDBOX="read-only"
FULL_AUTO=""
WORKDIR=""
PROMPT=""
RESUME=""

usage() {
    echo "Usage: $0 [options] <prompt>"
    echo ""
    echo "Options:"
    echo "  -m, --model MODEL      Model to use (default: gpt-5.1-codex-mini)"
    echo "  -e, --effort EFFORT    Reasoning effort: low|medium|high (default: medium)"
    echo "  -s, --sandbox MODE     Sandbox: read-only|workspace-write|danger-full-access"
    echo "  -a, --auto             Enable full-auto mode"
    echo "  -d, --dir DIR          Working directory"
    echo "  -r, --resume           Resume last session"
    echo "  -h, --help             Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 'Analyze the codebase structure'"
    echo "  $0 -s workspace-write -a 'Fix the bug in auth.ts'"
    echo "  $0 -r 'Continue with the changes'"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -m|--model)
            MODEL="$2"
            shift 2
            ;;
        -e|--effort)
            EFFORT="$2"
            shift 2
            ;;
        -s|--sandbox)
            SANDBOX="$2"
            shift 2
            ;;
        -a|--auto)
            FULL_AUTO="--full-auto"
            shift
            ;;
        -d|--dir)
            WORKDIR="$2"
            shift 2
            ;;
        -r|--resume)
            RESUME="true"
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

if [ -z "$PROMPT" ]; then
    echo "ERROR: Prompt required"
    usage
    exit 1
fi

# Build command
if [ "$RESUME" = "true" ]; then
    # Resume mode: minimal flags
    echo "$PROMPT" | codex exec --skip-git-repo-check resume --last 2>/dev/null
else
    # New session
    CMD="codex exec --skip-git-repo-check"
    CMD="$CMD -m $MODEL"
    CMD="$CMD --config model_reasoning_effort=\"$EFFORT\""
    CMD="$CMD --sandbox $SANDBOX"

    [ -n "$FULL_AUTO" ] && CMD="$CMD $FULL_AUTO"
    [ -n "$WORKDIR" ] && CMD="$CMD -C \"$WORKDIR\""

    echo "Running: $CMD \"$PROMPT\" 2>/dev/null"
    eval "$CMD \"$PROMPT\"" 2>/dev/null
fi
