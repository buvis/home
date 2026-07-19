#!/bin/bash
# Run Claude Sonnet via the native `claude` CLI (headless `-p`).
# Previously routed through the `copilot` CLI, which billed Copilot credits for
# a model Claude already provides. `claude -p` is foreground-blocking and free
# of Copilot credits, so the autopilot review reviewers (Diana, blind review)
# stop spending Copilot on Sonnet.

set -eo pipefail

# Ensure mise-managed tools (claude itself, plus the build/test tools the
# reviewer invokes agentically) are on PATH. Matches codex-run.sh / gemini-run.sh.
if command -v mise &>/dev/null; then
    PATH="$(mise env -s bash < /dev/null 2>/dev/null | sed -n "s/^export PATH='\\(.*\\)'/\\1/p"):$PATH"
fi

# Don't leak autopilot loop state into the nested claude: the autopilot Stop
# hook gates its signal-file write on _AUTOPILOT_LOOP, and a reviewer subprocess
# must never write that signal. One unset covers both the Diana subagent and the
# foreground blind-review call site.
# ponytail: single env guard, not a wrapper.
unset _AUTOPILOT_LOOP

# The unset above also re-enables the nested claude's notify.py hook (it gates
# on _AUTOPILOT_LOOP), so every reviewer dispatch pinged "done" mid-batch.
# Mark the nested session quiet instead: notify.py silences Stop/idle_prompt
# when this is set; permission_prompt still pages.
export _CLAUDE_NOTIFY_QUIET=1

# `sonnet` alias always resolves to the latest base Sonnet. No Copilot
# multiplier to dodge anymore - override with -m only when you need a specific
# model id or a different tier.
DEFAULT_MODEL="sonnet"
MODEL="$DEFAULT_MODEL"

MODE="prompt"  # prompt, interactive, resume, continue
PERM=""        # -a = acceptEdits (edits auto-approved, Bash still gated); -y = full bypass
ADD_DIRS=()
PROMPT=""
PROMPT_FILE=""
OUTPUT_FILE=""

usage() {
    echo "Usage: $0 [options] [prompt]"
    echo ""
    echo "Runs Claude Sonnet via the native claude CLI (default model: $DEFAULT_MODEL)."
    echo ""
    echo "Options:"
    echo "  -m, --model MODEL      Override model (default: $DEFAULT_MODEL; e.g. opus, claude-sonnet-5)"
    echo "  -i, --interactive      Interactive mode with initial prompt"
    echo "  -a, --allow-edits      Auto-approve file edits (--permission-mode acceptEdits; other tools stay gated)"
    echo "  -y, --yolo             Full permissions (--permission-mode bypassPermissions); required for unattended agentic runs"
    echo "  -s, --silent           Accepted for compatibility (claude -p output is already clean)"
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
    echo "  $0 -m opus -p 'Hard reasoning task'"
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
        -a|--allow-edits|--allow-tools)
            # --allow-tools kept as a deprecated spelling of -a; it now grants
            # acceptEdits, NOT bypass (the old mapping made -a a silent -y).
            PERM="--permission-mode acceptEdits"
            shift
            ;;
        -y|--yolo)
            PERM="--permission-mode bypassPermissions"
            shift
            ;;
        -s|--silent)
            # claude -p prints only the final assistant message; nothing to strip.
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
            if [[ -n "${2:-}" && ! "$2" =~ ^- ]]; then
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
        echo "ERROR: Prompt file not found: $PROMPT_FILE" >&2
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
            run_cmd claude --model "$MODEL" $PERM --resume "$PROMPT"
        else
            run_cmd claude --model "$MODEL" $PERM --resume
        fi
        ;;
    continue)
        run_cmd claude --model "$MODEL" $PERM --continue
        ;;
    interactive)
        if [ -z "$PROMPT" ]; then
            echo "ERROR: Prompt required for interactive mode" >&2
            usage >&2
            exit 1
        fi
        run_cmd claude --model "$MODEL" $PERM "${ADD_DIRS[@]}" "$PROMPT"
        ;;
    prompt)
        if [ -z "$PROMPT" ]; then
            echo "ERROR: Prompt required" >&2
            usage >&2
            exit 1
        fi
        # Headless (--print) dispatch: guard child stdin so an unattended
        # background run can never hang on a child reading the inherited
        # stdin (PRD 00040 hang class). Interactive/resume/continue modes
        # keep stdin - they need the TTY.
        run_cmd claude --print --model "$MODEL" $PERM "${ADD_DIRS[@]}" "$PROMPT" < /dev/null
        ;;
esac
