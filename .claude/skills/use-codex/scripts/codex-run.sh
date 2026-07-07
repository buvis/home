#!/bin/bash
# Run a Codex agent non-interactively. Prefers the native `codex` CLI;
# falls back to `copilot`. Every call is non-interactive: a fresh one-shot
# run by default, or a resumed codex session via --resume-thread (codex
# backend only). This helper feeds automated dispatch.

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
    echo "Runs are non-interactive. Each is a fresh one-shot run by default;"
    echo "--resume-thread continues a prior codex session (codex backend)."
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
    echo "  --resume-thread VALUE  Resume a codex thread (id or file whose first line is the id; codex only; requires -o)"
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
        --resume-thread)
            RESUME_VALUE="$2"
            RESUME_SET=1
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

if [ -n "${RESUME_SET:-}" ] && [ -z "${OUTPUT_FILE:-}" ]; then
    echo "ERROR: --resume-thread requires -o" >&2
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

# Resolves --resume-thread's VALUE to a codex resume id: if VALUE names a
# readable file, the id is that file's first line, stripped of surrounding
# whitespace; otherwise VALUE itself is the id.
resolve_resume_id() {
    local value="$1" first_line
    if [ -f "$value" ] && [ -r "$value" ]; then
        first_line=$(head -n 1 "$value")
        first_line="${first_line#"${first_line%%[![:space:]]*}"}"
        first_line="${first_line%"${first_line##*[![:space:]]}"}"
        printf '%s' "$first_line"
    else
        printf '%s' "$value"
    fi
}

# Finalizes a completed codex JSON-path run: when the run captured no
# thread.started, backfills EMIT_THREAD_FILE from fallback_id on a zero exit
# (else warns on the fresh path only; a failed resume attempt stays silent for
# run_codex_resume's single fallback warning), and on a zero exit cats
# OUTPUT_FILE to stdout for tee-parity.
# Split out of run_codex_json_path to keep it under the 50-line limit.
finalize_codex_json_run() {
    local codex_exit="$1" fallback_id="$2"

    if [ -n "${EMIT_THREAD_FILE:-}" ] && [ ! -s "$EMIT_THREAD_FILE" ]; then
        if [ "$codex_exit" -eq 0 ] && [ -n "$fallback_id" ]; then
            printf '%s' "$fallback_id" > "$EMIT_THREAD_FILE"
        elif [ -z "$fallback_id" ]; then
            # Fresh path (no resume): a missing thread.started genuinely means
            # the id was not captured, and no fallback follows.
            echo "WARNING: no thread.started event; thread id not captured" >&2
        fi
        # Failed resume attempt (fallback_id set, codex_exit != 0): stay silent.
        # run_codex_resume emits the single "resume failed; retrying fresh"
        # warning, and the fresh fallback re-attempts capture.
    fi

    if [ "$codex_exit" -eq 0 ]; then
        if [ -s "$OUTPUT_FILE" ]; then
            cat "$OUTPUT_FILE"
        else
            echo "WARNING: codex exited 0 but wrote no output" >&2
        fi
    fi
}

# Runs `"$@" --json --output-last-message "$OUTPUT_FILE" "$PROMPT" < /dev/null`
# and consumes codex's JSONL stream: captures the thread id (when
# EMIT_THREAD_FILE is set) from the thread.started event, prints a
# `codex-event: <type>` liveness marker per line to stderr, never leaks raw
# JSONL onto stdout, and on a zero exit cats OUTPUT_FILE to stdout for
# tee-parity. Returns codex's real exit code. Shared by the fresh and resume
# argv paths, which both need this identical JSON-stream handling.
#
# Optional leading `--fallback-id VALUE` flag: a resume's own thread id,
# unchanged by resume. If given and the run exits 0 with no thread.started
# captured, VALUE is written to EMIT_THREAD_FILE instead, and the "not
# captured" warning is suppressed (we did recover the id). Unused (and
# byte-identical to before) on the fresh path, which never passes it.
run_codex_json_path() {
    local fallback_id=""
    if [ "$1" = "--fallback-id" ]; then
        fallback_id="$2"
        shift 2
    fi

    if [ -n "${EMIT_THREAD_FILE:-}" ]; then
        # Truncate any stale capture first so a run with no thread.started
        # leaves no old id behind.
        : > "$EMIT_THREAD_FILE"
    fi

    local line type tid codex_exit
    set +e
    "$@" --json --output-last-message "$OUTPUT_FILE" "$PROMPT" < /dev/null | \
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
        if [ -n "${EMIT_THREAD_FILE:-}" ] && [ "$type" = "thread.started" ]; then
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

    finalize_codex_json_run "$codex_exit" "$fallback_id"

    return "$codex_exit"
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

    # Resolve --resume-thread (if given) to a usable resume id. Anything that
    # keeps resume from being viable (empty/unreadable id, or --add-dir -
    # which `codex exec resume` rejects) drops straight to the fresh JSON
    # path; resume is never attempted in those cases.
    local resume_id=""
    if [ -n "${RESUME_SET:-}" ]; then
        resume_id=$(resolve_resume_id "$RESUME_VALUE")
        if [ -z "$resume_id" ]; then
            echo "WARNING: --resume-thread id empty/unreadable; starting fresh session" >&2
        elif [ "${#ADD_DIRS[@]}" -gt 0 ]; then
            echo "WARNING: --add-dir is not supported on resume; starting fresh session" >&2
            resume_id=""
        fi
    fi

    if [ -z "${EMIT_THREAD_FILE:-}" ] && [ -z "${RESUME_SET:-}" ]; then
        run_cmd codex exec --skip-git-repo-check "${model[@]}" "${sandbox[@]}" "${ADD_DIRS[@]}" "$PROMPT" < /dev/null
        return
    fi

    if [ -n "$resume_id" ] && run_codex_resume "$resume_id" "${model[@]}"; then
        return 0
    fi

    run_codex_json_path codex exec --skip-git-repo-check "${model[@]}" "${sandbox[@]}" "${ADD_DIRS[@]}"
}

# Runs the resume attempt for run_codex(): resume argv (forced read-only via
# -c, since `codex exec resume` rejects -s/--sandbox), FIX-1 thread-id
# backfill via run_codex_json_path's --fallback-id, and the single bounded
# fallback warning on failure. Returns 0 on a successful resume; non-zero
# otherwise, signaling run_codex() to retry on the fresh JSON path.
run_codex_resume() {
    local resume_id="$1"
    shift
    local model=("$@")
    local resume_sandbox=(-c sandbox_mode=read-only)

    local rc=0
    run_codex_json_path --fallback-id "$resume_id" \
        codex exec resume "$resume_id" --skip-git-repo-check "${model[@]}" "${resume_sandbox[@]}" || rc=$?
    if [ "$rc" -eq 0 ]; then
        return 0
    fi
    # Bounded fallback: exactly one retry on the fresh JSON path, whose exit
    # code becomes codex-run.sh's own.
    echo "WARNING: codex resume failed (exit $rc); retrying with a fresh session" >&2
    return "$rc"
}

run_copilot() {
    if [ -n "${EMIT_THREAD_FILE:-}" ]; then
        echo "WARNING: --emit-thread-id requires the codex backend; running one-shot" >&2
    fi

    if [ -n "${RESUME_SET:-}" ]; then
        echo "WARNING: --resume-thread requires the codex backend; running one-shot" >&2
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
