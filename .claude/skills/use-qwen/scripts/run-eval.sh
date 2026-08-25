#!/bin/bash
# Automates references/eval-runbook.md steps 2, 3 and 5 (dispatch each task,
# verify against the REAL gate, and on a passing verdict append the candidate
# to approved-models.txt). Step 1 - picking 6 single-file, test-gated, backend
# tasks from dev/local/prds/done/ - stays manual: which tasks are eligible
# needs cross-repo judgment this script should not guess at.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
QWEN_RUN_SH="$SCRIPT_DIR/qwen-run.sh"
REGISTRY="${QWEN_APPROVED_REGISTRY:-$SCRIPT_DIR/approved-models.txt}"
CLAUDE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

PROVIDER=""
MODEL=""
TASKS_FILE=""
OUT_FILE=""
COMMIT=""

usage() {
    echo "Usage: $0 -P PROVIDER -m MODEL --tasks FILE [--commit] [--out FILE]"
    echo ""
    echo "Automates eval-runbook.md steps 2/3/5 for a qualification candidate:"
    echo "dispatches each task, verifies against the REAL gate (never the model's"
    echo "self-report), scores, and writes a full evidence log. Picking the 6"
    echo "tasks (step 1) stays manual - see references/eval-runbook.md."
    echo ""
    echo "  -P, --provider NAME  Candidate's provider - PINNED, not auto-detected"
    echo "                       (eval-runbook.md: the model field alone does not"
    echo "                       choose which server answers)"
    echo "  -m, --model MODEL    Candidate model id"
    echo "      --tasks FILE     TSV manifest, one task per line:"
    echo "                       <prompt-file><TAB><verify-shell-command>"
    echo "                       Must contain exactly 6 task lines (# comments"
    echo "                       and blank lines ignored) - the runbook's bar."
    echo "      --commit         Append to $REGISTRY on a PASS verdict. This is"
    echo "                       an affirmation, not a verifier: read every"
    echo "                       transcript in the evidence log FIRST and confirm"
    echo "                       zero false success claims yourself - the script"
    echo "                       only checks the real gate's exit code."
    echo "      --out FILE       Evidence log path (default: dev/local/audit-results/"
    echo "                       qwen-eval-<model-slug>-<date>.md)"
    echo "  -h, --help           Show this help"
}

while [[ $# -gt 0 ]]; do
    case $1 in
        -P|--provider) PROVIDER="$2"; shift 2 ;;
        -m|--model) MODEL="$2"; shift 2 ;;
        --tasks) TASKS_FILE="$2"; shift 2 ;;
        --commit) COMMIT="1"; shift ;;
        --out) OUT_FILE="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

[ -z "$PROVIDER" ] && { echo "ERROR: -P/--provider is required." >&2; exit 2; }
[ -z "$MODEL" ] && { echo "ERROR: -m/--model is required." >&2; exit 2; }
[ -z "$TASKS_FILE" ] && { echo "ERROR: --tasks FILE is required." >&2; exit 2; }
[ -f "$TASKS_FILE" ] || { echo "ERROR: tasks file not found: $TASKS_FILE" >&2; exit 2; }
for tool in jq curl; do
    command -v "$tool" &>/dev/null || { echo "ERROR: '$tool' required." >&2; exit 2; }
done

TASKS=()
while IFS=$'\t' read -r prompt_file verify_cmd; do
    [ -z "${prompt_file:-}" ] && continue
    case "$prompt_file" in \#*) continue ;; esac
    if [ -z "${verify_cmd:-}" ]; then
        echo "ERROR: malformed line in $TASKS_FILE (missing verify command): $prompt_file" >&2
        exit 2
    fi
    [ -f "$prompt_file" ] || { echo "ERROR: prompt file not found: $prompt_file" >&2; exit 2; }
    TASKS+=("$prompt_file"$'\t'"$verify_cmd")
done < "$TASKS_FILE"

if [ "${#TASKS[@]}" -ne 6 ]; then
    echo "ERROR: --tasks must list exactly 6 tasks (found ${#TASKS[@]}) - eval-runbook.md's bar is a 6-task eval." >&2
    exit 2
fi

# Verify -P/-m is actually live BEFORE spending a single dispatch. -P and -m
# are always forced below, so qwen-run.sh's own "Using provider/model" line
# would otherwise just echo back whatever was requested - it never re-checks
# that the live server really serves that id when both are forced. Skipping
# this would reproduce exactly the false-evidence risk eval-runbook.md warns
# about: llama.cpp serves whatever it has loaded regardless of the requested
# model field, so a typo'd id would silently score a completely different
# model and attribute the evidence to this candidate.
MODELS_JSON="${PI_CODING_AGENT_DIR:-$HOME/.pi/agent}/models.json"
BASE_URL="$(jq -r --arg p "$PROVIDER" '.providers[$p].baseUrl // empty' "$MODELS_JSON" 2>/dev/null)"
if [ -z "$BASE_URL" ]; then
    echo "ERROR: provider '$PROVIDER' not found in $MODELS_JSON." >&2
    exit 2
fi
LIVE_IDS="$(curl -sf --max-time 5 "$BASE_URL/models" < /dev/null 2>/dev/null | jq -r '.data[].id' 2>/dev/null)"
if [ -z "$LIVE_IDS" ]; then
    echo "ERROR: no server responding at $BASE_URL (provider $PROVIDER). Start llama-server first." >&2
    exit 2
fi
if ! grep -qFx -- "$MODEL" <<< "$LIVE_IDS"; then
    echo "ERROR: '$MODEL' is not being served by provider '$PROVIDER' at $BASE_URL (live ids: $(printf '%s' "$LIVE_IDS" | tr '\n' ' ')). Refusing before wasting a single task run." >&2
    exit 2
fi

MODEL_SLUG="$(printf '%s' "$MODEL" | tr -c 'A-Za-z0-9._-' '-')"
DATE_STR="$(date +%Y-%m-%d)"
: "${OUT_FILE:=$CLAUDE_DIR/dev/local/audit-results/qwen-eval-${MODEL_SLUG}-${DATE_STR}.md}"
mkdir -p "$(dirname "$OUT_FILE")"

{
    echo "# Qwen eval: $MODEL"
    echo ""
    echo "Provider: $PROVIDER | Run: $DATE_STR"
} > "$OUT_FILE"

PASS_N=0
TASK_N=0
DISCARD_SEEN=0

for entry in "${TASKS[@]}"; do
    TASK_N=$((TASK_N + 1))
    prompt_file="${entry%%$'\t'*}"
    verify_cmd="${entry#*$'\t'}"

    # eval-runbook.md #2: pin the provider, retry once on a mismatch or a
    # dispatch that never actually ran pi (preflight/completion failure) -
    # neither is evidence about the CANDIDATE, so neither is scored.
    attempt=1
    DISPATCH_OK=""
    OUT="" DISPATCH_RC=0 FIRST_LINE=""
    while [ "$attempt" -le 2 ]; do
        OUT="$(bash "$QWEN_RUN_SH" -P "$PROVIDER" -m "$MODEL" -f "$prompt_file" 2>&1)"
        DISPATCH_RC=$?
        FIRST_LINE="$(printf '%s\n' "$OUT" | head -n1)"
        if [ "$FIRST_LINE" = "Using provider '$PROVIDER' model '$MODEL'" ] && [ "$DISPATCH_RC" -eq 0 ]; then
            DISPATCH_OK="1"
            break
        fi
        attempt=$((attempt + 1))
    done

    GATE_PASS=""
    GATE_RC=""
    GATE_OUT=""
    SUSPECT=""
    if [ -n "$DISPATCH_OK" ]; then
        GATE_OUT="$(bash -c "$verify_cmd" 2>&1)"
        GATE_RC=$?
        [ "$GATE_RC" -eq 0 ] && GATE_PASS="1" && PASS_N=$((PASS_N + 1))
        if [ -z "$GATE_PASS" ] && printf '%s' "$OUT" | grep -qiE "all tests? pass|tests? passed|successfully completed|no failures|✓ *(all|done)"; then
            SUSPECT="1"
        fi
    else
        DISCARD_SEEN=1
    fi

    {
        echo ""
        echo "## Task $TASK_N: $prompt_file"
        echo ""
        echo "Verify: \`$verify_cmd\`"
        echo ""
        if [ -z "$DISPATCH_OK" ]; then
            echo "**DISCARDED** - dispatch never confirmed provider '$PROVIDER'/model '$MODEL' after 2 attempts (rc=$DISPATCH_RC, first line: \`$FIRST_LINE\`). Not scored; re-run this task once the backend is healthy."
        else
            echo "Gate exit code: $GATE_RC -> $([ -n "$GATE_PASS" ] && echo PASS || echo FAIL)"
            if [ -n "$SUSPECT" ]; then
                echo ""
                echo "**REVIEW**: gate failed, but the qwen transcript below contains success-claiming language - read it before trusting this candidate."
            fi
        fi
        echo ""
        echo '<details><summary>qwen-run.sh output</summary>'
        echo ""
        echo '```'
        echo "$OUT"
        echo '```'
        echo "</details>"
        if [ -n "$DISPATCH_OK" ]; then
            echo ""
            echo '<details><summary>verify command output</summary>'
            echo ""
            echo '```'
            echo "$GATE_OUT"
            echo '```'
            echo "</details>"
        fi
    } >> "$OUT_FILE"
done

VERDICT="FAIL"
if [ "$DISCARD_SEEN" -eq 0 ] && [ "$PASS_N" -ge 5 ]; then
    VERDICT="PASS"
fi

{
    echo ""
    echo "## Verdict"
    echo ""
    echo "Score: $PASS_N/6 gate-passing. Verdict: $VERDICT."
    echo ""
    echo "Zero-false-claims is NOT auto-verified above - read every transcript"
    echo "marked **REVIEW** (and ideally all of them) before trusting this verdict."
} >> "$OUT_FILE"

echo "Evidence: $OUT_FILE"
echo "Score: $PASS_N/6, verdict: $VERDICT"

if [ "$VERDICT" != "PASS" ]; then
    exit 1
fi

if [ -n "$COMMIT" ]; then
    if grep -qFx -- "$MODEL" "$REGISTRY"; then
        echo "'$MODEL' is already in $REGISTRY - nothing to append."
    else
        {
            echo ""
            echo "# Qualified $DATE_STR: 6-task agentic eval, $PASS_N/6 passed, tasks drawn from"
            echo "# $TASKS_FILE (see evidence: $OUT_FILE). Served via llama.cpp."
            echo "$MODEL"
        } >> "$REGISTRY"
        echo "Appended '$MODEL' to $REGISTRY."
    fi
else
    echo "Not committed - pass --commit (after reading the evidence log) to append to $REGISTRY."
fi
