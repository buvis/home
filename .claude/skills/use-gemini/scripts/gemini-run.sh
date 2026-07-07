#!/bin/bash
# Run Gemini for code analysis/editing.
#
# Backend: prefers the GitHub Copilot CLI (serves Gemini 3.1 Pro Preview, which
# the native Gemini CLI cannot), falls back to the native `gemini` CLI when
# copilot is absent. Override with GEMINI_BACKEND=copilot|gemini.
#
# Copilot billing note: every call spends Copilot AI credits (multiplier set by
# the model). The native gemini backend bills your Google/Gemini account with no
# Copilot multiplier. Per policy, Gemini-via-Copilot is allowed (Claude does not
# provide Gemini); only models Claude serves must stay off Copilot.

set -eo pipefail

# Ensure mise-managed tools (copilot/gemini, plus build/test tools they invoke)
# are on PATH. Matches codex-run.sh / sonnet-run.sh.
if command -v mise &>/dev/null; then
    PATH="$(mise env -s bash 2>/dev/null | sed -n "s/^export PATH='\\(.*\\)'/\\1/p"):$PATH"
fi

resolve_bin() {
    # $1 = tool name; echoes path or empty
    local p
    p="$(command -v "$1" 2>/dev/null || true)"
    if [ -z "$p" ] && command -v mise &>/dev/null; then
        p="$(mise which "$1" 2>/dev/null || true)"
    fi
    echo "$p"
}

# Backend selection. copilot preferred (it is the only backend that serves the
# gemini-3.1-pro-preview model); native gemini is the fallback.
BACKEND="${GEMINI_BACKEND:-}"
COPILOT_BIN="$(resolve_bin copilot)"
GEMINI_BIN="$(resolve_bin gemini)"
if [ -z "$BACKEND" ]; then
    if [ -n "$COPILOT_BIN" ]; then
        BACKEND="copilot"
    elif [ -n "$GEMINI_BIN" ]; then
        BACKEND="gemini"
    fi
fi
if [ "$BACKEND" = "copilot" ] && [ -z "$COPILOT_BIN" ]; then
    echo "ERROR: GEMINI_BACKEND=copilot but the copilot CLI was not found." >&2
    exit 1
fi
if [ "$BACKEND" = "gemini" ] && [ -z "$GEMINI_BIN" ]; then
    echo "ERROR: GEMINI_BACKEND=gemini but the gemini CLI was not found." >&2
    exit 1
fi
if [ -z "$BACKEND" ]; then
    echo "ERROR: neither 'copilot' nor 'gemini' CLI found." >&2
    echo "Install one (e.g. 'mise use -g npm:@github/copilot' or 'mise use -g npm:@google/gemini-cli') and retry." >&2
    exit 1
fi

# Copilot default model. gemini-3.1-pro-preview = "Gemini 3.1 Pro (Preview)".
# Override with -m. The native gemini backend keeps the CLI default unless -m.
DEFAULT_COPILOT_MODEL="gemini-3.1-pro-preview"

MODEL=""          # empty = backend default
MODE="prompt"     # prompt, interactive, resume, continue
APPROVAL=""       # auto_edit | yolo (intent; mapped per backend)
RAW_DIRS=()
PROMPT=""
PROMPT_FILE=""
OUTPUT_FILE=""
RESUME_ID=""
SILENT=""

usage() {
    echo "Usage: $0 [options] [prompt]"
    echo ""
    echo "Backend: $BACKEND (copilot preferred, gemini fallback)."
    echo "copilot default model: $DEFAULT_COPILOT_MODEL. Override backend with GEMINI_BACKEND=copilot|gemini."
    echo ""
    echo "Options:"
    echo "  -m, --model MODEL      Override model (copilot default: $DEFAULT_COPILOT_MODEL)"
    echo "  -i, --interactive      Interactive mode with initial prompt"
    echo "  -a, --allow-tools      Auto-approve edit tools"
    echo "  -y, --yolo             Auto-approve all tools"
    echo "  -s, --silent           Quiet output (copilot only; gemini -p is already clean)"
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
    echo "  GEMINI_BACKEND=gemini $0 -f /tmp/prompt.txt   # use native Gemini CLI"
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
            SILENT="1"
            shift
            ;;
        -d|--dir)
            RAW_DIRS+=("$2")
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

# Build and run command
run_cmd() {
    if [ -n "$OUTPUT_FILE" ]; then
        "$@" 2>&1 | tee "$OUTPUT_FILE"
    else
        "$@"
    fi
}

run_copilot() {
    local model="${MODEL:-$DEFAULT_COPILOT_MODEL}"
    local dirs=()
    local d
    for d in "${RAW_DIRS[@]}"; do dirs+=(--add-dir "$d"); done
    [ -n "$SILENT" ] && dirs+=(-s)   # -s belongs to copilot; group with extras

    # Permission mapping. Copilot's non-interactive (-p / resume) mode REQUIRES
    # auto-approval or it blocks on a prompt; with no -a/-y we auto-approve reads
    # but deny the write tool to preserve read-only-review intent.
    local perms=()
    local noninteractive_perms=()
    if [ "$APPROVAL" = "yolo" ]; then
        perms=(--yolo); noninteractive_perms=(--yolo)
    elif [ "$APPROVAL" = "auto_edit" ]; then
        perms=(--allow-all-tools); noninteractive_perms=(--allow-all-tools)
    else
        noninteractive_perms=(--allow-all-tools --deny-tool=write)
    fi

    case $MODE in
        interactive)
            [ -z "$PROMPT" ] && { echo "ERROR: Prompt required for interactive mode" >&2; exit 1; }
            run_cmd "$COPILOT_BIN" --model "$model" "${perms[@]}" "${dirs[@]}" -i "$PROMPT"
            ;;
        continue)
            run_cmd "$COPILOT_BIN" --model "$model" "${noninteractive_perms[@]}" "${dirs[@]}" --continue
            ;;
        resume)
            local rflag=(--resume)
            [ -n "$RESUME_ID" ] && [ "$RESUME_ID" != "latest" ] && rflag=(--resume="$RESUME_ID")
            if [ -n "$PROMPT" ]; then
                run_cmd "$COPILOT_BIN" --model "$model" "${noninteractive_perms[@]}" "${dirs[@]}" "${rflag[@]}" -p "$PROMPT"
            else
                run_cmd "$COPILOT_BIN" --model "$model" "${noninteractive_perms[@]}" "${dirs[@]}" "${rflag[@]}"
            fi
            ;;
        prompt)
            [ -z "$PROMPT" ] && { echo "ERROR: Prompt required" >&2; exit 1; }
            run_cmd "$COPILOT_BIN" --model "$model" "${noninteractive_perms[@]}" "${dirs[@]}" -p "$PROMPT"
            ;;
    esac
}

run_gemini() {
    # Flags common to every invocation. --skip-trust avoids the workspace-trust
    # prompt blocking headless (-p) runs.
    local common=(--skip-trust)
    [ -n "$MODEL" ] && common+=(-m "$MODEL")
    case $APPROVAL in
        auto_edit) common+=(--approval-mode auto_edit) ;;
        yolo) common+=(--approval-mode yolo) ;;
    esac
    local d
    for d in "${RAW_DIRS[@]}"; do common+=(--include-directories "$d"); done

    case $MODE in
        resume)
            local id="${RESUME_ID:-latest}"
            if [ -n "$PROMPT" ]; then
                run_cmd "$GEMINI_BIN" "${common[@]}" --resume "$id" -p "$PROMPT"
            else
                run_cmd "$GEMINI_BIN" "${common[@]}" --resume "$id"
            fi
            ;;
        continue)
            run_cmd "$GEMINI_BIN" "${common[@]}" --resume latest
            ;;
        interactive)
            [ -z "$PROMPT" ] && { echo "ERROR: Prompt required for interactive mode" >&2; exit 1; }
            run_cmd "$GEMINI_BIN" "${common[@]}" -i "$PROMPT"
            ;;
        prompt)
            [ -z "$PROMPT" ] && { echo "ERROR: Prompt required" >&2; exit 1; }
            run_cmd "$GEMINI_BIN" "${common[@]}" -p "$PROMPT"
            ;;
    esac
}

if [ "$BACKEND" = "copilot" ]; then
    run_copilot
else
    run_gemini
fi
