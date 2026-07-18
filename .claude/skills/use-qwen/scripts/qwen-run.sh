#!/bin/bash
# Run a local Qwen model (served by llama.cpp) through the pi coding agent.

set -eo pipefail

# Ensure mise-managed tools (like pi) are on PATH.
if command -v mise &>/dev/null; then
    PATH="$(mise env -s bash < /dev/null 2>/dev/null | sed -n "s/^export PATH='\\(.*\\)'/\\1/p"):$PATH"
fi

# Local model served by llama.cpp - free to run, no API cost.
# qwen3-coder-30b-a3b cleared a 6-task agentic Rust eval on llama.cpp; the same
# model over Ollama failed (Ollama's qwen3coder tool-call XML parser mangles
# large edits). Serve via llama.cpp/LlamaBarn with `--jinja`.
#
# Provider/model are auto-detected from pi's config (~/.pi/agent/models.json):
# every provider is probed in ascending port order and the first one with a
# live server wins; the model id comes from that server's /v1/models listing,
# preferring the promoted default (scripts/default-model.txt, written by
# promote-default.sh) when the server lists it - multi-model servers
# (LlamaBarn) list every downloaded model, so listing order alone would pin
# dispatches to whatever happens to sit at .data[0]. Override with --provider
# and/or -m. A config entry is NOT proof a server is up, so we
# probe rather than trust the lowest port blindly. And a /v1/models listing is
# NOT proof the worker can serve — LlamaBarn-style servers enumerate models
# straight from config and spawn the inference worker lazily on the first
# completion (the 2026-06-19 "false healthy" incident: models 200, completion
# 500). The deciding health signal is therefore a real 1-token completion
# probe, run before ANY pi dispatch; the listing is only a fast pre-check.
# Mirrors the preflight contract in
# ~/.claude/skills/work/references/qwen-integration.md (outcomes: pi_missing /
# endpoint_unreachable / model_id_missing / completion_failed; model_id_missing
# fires only under --approved-only).
MODELS_JSON="${PI_CODING_AGENT_DIR:-$HOME/.pi/agent}/models.json"
REGISTRY="$(dirname "$0")/approved-models.txt"
MODEL=""             # empty = take whatever the live server reports
PROVIDER=""          # empty = auto-detect lowest live port
MODE="prompt"        # prompt, interactive, resume, continue, preflight, register
OUTPUT_MODE="text"   # text or json (pi --mode)
READ_ONLY=""
APPROVED_ONLY=""     # empty = registry not consulted (today's behavior)
PROMPT=""
PROMPT_FILE=""
OUTPUT_FILE=""
MODEL_NAME=""        # optional --name for --register-model (default: probed id)

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
    echo "  -m, --model MODEL    Force model id (default: the promoted default in"
    echo "                       scripts/default-model.txt when the live server lists"
    echo "                       it, else the first id the server reports)"
    echo "      --approved-only  Restrict provider/model resolution to ids listed in"
    echo "                       $REGISTRY (refuses/skips unapproved live ids)"
    echo "  -i, --interactive    Interactive mode with initial prompt"
    echo "  -R, --read-only      Restrict to read-only tools (no file edits)"
    echo "  -j, --json           Emit a structured JSON event stream (pi --mode json)"
    echo "  -s, --silent         Accepted for compatibility (no-op; pi output is already clean)"
    echo "      --preflight      Probe only: resolve provider/model and require a real"
    echo "                       1-token completion. Exit 0 = healthy; nonzero names the"
    echo "                       failing check (pi_missing/endpoint_unreachable/"
    echo "                       model_id_missing/completion_failed). model_id_missing"
    echo "                       fires only with --approved-only."
    echo "      --register-model Requires -P/--provider. Probes that provider's live"
    echo "                       /v1/models for the real id + context window and upserts"
    echo "                       it into \$MODELS_JSON (by id - re-running updates, never"
    echo "                       duplicates). Pass -m to pick one id when the server"
    echo "                       lists several (LlamaBarn lists every downloaded model)."
    echo "                       Never derives the id from a filename or naming"
    echo "                       convention. Does not create providers or touch the"
    echo "                       approved registry (see references/eval-runbook.md)."
    echo "      --name NAME      Friendly display name for --register-model (default:"
    echo "                       the probed model id)."
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
    echo "  $0 --register-model -P llamacpp8001            # add whatever :8001 is serving"
    echo "  $0 --register-model -P llamacpp -m <live-id>   # multi-model server: pick one"
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
        --approved-only)
            APPROVED_ONLY="1"
            shift
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
        -s|--silent)
            # Accepted for flag parity with codex/gemini/sonnet; pi's -p
            # output is already clean, so there is nothing to strip.
            shift
            ;;
        --preflight)
            MODE="preflight"
            shift
            ;;
        --register-model)
            MODE="register"
            shift
            ;;
        --name)
            MODEL_NAME="$2"
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
        echo "ERROR: Prompt file not found: $PROMPT_FILE" >&2
        exit 1
    fi
    PROMPT=$(cat "$PROMPT_FILE")
fi

if ! command -v pi &>/dev/null; then
    echo "ERROR: preflight failed (pi_missing): 'pi' not found on PATH. Install via mise, then run 'mise reshim'." >&2
    exit 1
fi

for tool in jq curl; do
    command -v "$tool" &>/dev/null || { echo "ERROR: '$tool' required for provider auto-detect." >&2; exit 1; }
done
if [ ! -f "$MODELS_JSON" ]; then
    echo "ERROR: preflight failed (endpoint_unreachable): pi model config not found: $MODELS_JSON" >&2
    exit 1
fi
if [ -n "$APPROVED_ONLY" ] && [ ! -f "$REGISTRY" ]; then
    echo "ERROR: preflight failed (model_id_missing): approved-models registry not found at $REGISTRY (--approved-only requires it)." >&2
    exit 1
fi

# Ask a provider's llama-server for the id it's actually serving (empty if down).
# Fast pre-check only — a listing is never the deciding health signal.
# The trailing `|| true` keeps a dead server from tripping set -e/pipefail
# inside the command substitution (which used to kill the script silently
# before the endpoint_unreachable error could be printed).
probe_model() { curl -sf --max-time 2 "$1/models" < /dev/null 2>/dev/null | jq -r '.data[0].id // empty' 2>/dev/null || true; }

# Full list of ids a provider's /v1/models currently serves (one per line,
# empty if down). Used only under --approved-only, where an approved id may
# sit at any position in the listing, not just [0].
probe_models() { curl -sf --max-time 2 "$1/models" < /dev/null 2>/dev/null | jq -r '.data[].id' 2>/dev/null || true; }

# Look up a provider's baseUrl from the config (empty if the provider is absent).
provider_base_url() { jq -r --arg p "$1" '.providers[$p].baseUrl // empty' "$MODELS_JSON" < /dev/null; }

# --approved-only: true if $1 exactly matches a registry line once that line's
# leading/trailing whitespace is trimmed (`read` does this trimming itself
# under the default IFS). The registry can contain blank lines
# (formatting/section breaks), so the empty string is rejected explicitly
# instead of letting a trimmed blank line exact-match it. A plain string
# compare (not grep) means a `-`-prefixed model id is never at risk of being
# parsed as an option.
is_approved() {
    [ -n "$1" ] || return 1
    local line
    while read -r line; do
        [ "$line" = "$1" ] && return 0
    done < "$REGISTRY" 2>/dev/null
    return 1
}

# Promoted default (scripts/default-model.txt, written by promote-default.sh):
# first non-comment, non-blank line. File absent = no preference, resolution
# behaves as before (single-model servers never notice the difference).
DEFAULT_FILE="$(dirname "$0")/default-model.txt"
DEFAULT_MODEL=""
if [ -f "$DEFAULT_FILE" ]; then
    while IFS= read -r _dline; do
        case "$_dline" in ''|\#*) continue ;; esac
        DEFAULT_MODEL="$_dline"
        break
    done < "$DEFAULT_FILE"
fi

# Pick the dispatch id from a newline-separated live listing: the promoted
# default when the listing carries it (and, under --approved-only, it is
# approved), else the first (plain) / first approved (--approved-only) id.
# Echoes empty when nothing qualifies.
pick_id() {
    local id
    if [ -n "$DEFAULT_MODEL" ] && grep -qFx -- "$DEFAULT_MODEL" <<< "$1"; then
        if [ -z "$APPROVED_ONLY" ] || is_approved "$DEFAULT_MODEL"; then
            printf '%s\n' "$DEFAULT_MODEL"
            return 0
        fi
    fi
    if [ -n "$APPROVED_ONLY" ]; then
        while IFS= read -r id; do
            is_approved "$id" && { printf '%s\n' "$id"; return 0; }
        done <<< "$1"
        return 0
    fi
    printf '%s\n' "$1" | head -n1
}

# The deciding health signal: a real 1-token completion against the served
# model (max_tokens=1). Exercises the lazy worker spawn that /v1/models never
# does. 120s ceiling covers a cold model load (~18.5 GB GGUF) and doubles as a
# warm-up for the dispatch that follows — the load is not wasted.
probe_completion() {
    curl -sf --max-time 120 -X POST "$1/chat/completions" \
        -H 'Content-Type: application/json' \
        -d "{\"model\": \"$2\", \"messages\": [{\"role\": \"user\", \"content\": \"ping\"}], \"max_tokens\": 1, \"stream\": false}" \
        < /dev/null > /dev/null 2>&1
}

# --register-model: probes -P's live /v1/models and upserts the reported id
# into MODELS_JSON (keyed by id, so re-running updates in place rather than
# duplicating). Never derives the id or contextWindow from a filename or
# naming convention - a real id (unsloth/Qwen3.6-27B-MTP) turned out not to
# match the org/repo-GGUF:quant pattern every prior entry happened to share.
# Requires -P: this adds a model to an already-configured provider, it does
# not create providers (baseUrl/api/apiKey/compat are choices this script
# should not guess). With -m, registers that id from the live list - multi-
# model servers (LlamaBarn) list every downloaded model, so .data[0] is not
# necessarily the one just added. Does not touch approved-models.txt - see
# references/eval-runbook.md before trusting a newly-registered id.
if [ "$MODE" = "register" ]; then
    if [ -z "$PROVIDER" ]; then
        echo "ERROR: --register-model requires -P/--provider (which provider's server did you just start?)." >&2
        exit 1
    fi
    BASE_URL="$(provider_base_url "$PROVIDER")"
    if [ -z "$BASE_URL" ]; then
        echo "ERROR: provider '$PROVIDER' not found in $MODELS_JSON. Add its baseUrl/api/apiKey block manually first - --register-model only adds models to an existing provider." >&2
        exit 1
    fi
    RESP="$(curl -sf --max-time 5 "$BASE_URL/models" < /dev/null 2>/dev/null || true)"
    if [ -n "$MODEL" ]; then
        NEW_ID="$(jq -r --arg id "$MODEL" '[.data[]? | select(.id == $id)][0].id // empty' <<< "$RESP" 2>/dev/null)"
        if [ -z "$NEW_ID" ] && [ -n "$RESP" ]; then
            echo "ERROR: server at $BASE_URL does not list '$MODEL' in /v1/models. Live ids: $(jq -r '[.data[]?.id] | join(", ")' <<< "$RESP" 2>/dev/null)" >&2
            exit 1
        fi
    else
        NEW_ID="$(jq -r '.data[0].id // empty' <<< "$RESP" 2>/dev/null)"
    fi
    if [ -z "$NEW_ID" ]; then
        echo "ERROR: preflight failed (endpoint_unreachable): no server responding at $BASE_URL (provider $PROVIDER). Start llama-server first." >&2
        exit 1
    fi
    CTX="$(jq -r --arg id "$NEW_ID" '[.data[]? | select(.id == $id)][0].meta.n_ctx // 131072' <<< "$RESP" 2>/dev/null)"
    NAME="${MODEL_NAME:-$NEW_ID}"
    TMP_JSON="$(mktemp)"
    jq --arg p "$PROVIDER" --arg id "$NEW_ID" --arg name "$NAME" --argjson ctx "$CTX" '
        .providers[$p].models = ((.providers[$p].models // []) | map(select(.id != $id))
            + [{id: $id, name: $name, input: ["text"], contextWindow: $ctx, maxTokens: 32768,
                cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0}}])
    ' "$MODELS_JSON" > "$TMP_JSON" && mv "$TMP_JSON" "$MODELS_JSON"
    echo "Registered '$NEW_ID' (contextWindow=$CTX) into provider '$PROVIDER' in $MODELS_JSON." >&2
    # Alias tripwire (2026-07-19 incident): the approved registry is quant-exact
    # (org/repo-GGUF:quant), so a served id with no ':<quant>' tag - the
    # signature of a llama-server --alias - can be registered and evaled but
    # will never match a registry entry approved under the real -hf id.
    case "$NEW_ID" in
        *:*) ;;
        *) echo "WARNING: '$NEW_ID' carries no ':<quant>' tag. If this server was started with --alias, drop the alias and re-register: an aliased id forks the id namespace and --approved-only will silently skip this provider." >&2 ;;
    esac
    if probe_completion "$BASE_URL" "$NEW_ID"; then
        echo "Verified: 1-token completion succeeded. Not yet approved - run references/eval-runbook.md before using --approved-only." >&2
        exit 0
    else
        echo "WARNING: registered, but the 1-token completion probe failed (worker spawn issue?). Entry is saved; fix the backend, then re-check with --preflight." >&2
        exit 1
    fi
fi

# --approved-only with an explicit -m: refuse up front, before any provider
# probing, if the forced id is not in the registry.
if [ -n "$APPROVED_ONLY" ] && [ -n "$MODEL" ] && ! is_approved "$MODEL"; then
    echo "ERROR: preflight failed (model_id_missing): '$MODEL' is not in the approved registry ($REGISTRY)." >&2
    exit 1
fi

if [ -n "$PROVIDER" ]; then
    BASE_URL="$(provider_base_url "$PROVIDER")"
    if [ -z "$BASE_URL" ]; then
        echo "ERROR: preflight failed (endpoint_unreachable): provider '$PROVIDER' not found in $MODELS_JSON" >&2
        exit 1
    fi
    if [ -z "$MODEL" ]; then
        if [ -n "$APPROVED_ONLY" ]; then
            # Scan every id this provider serves (promoted default first, then
            # the first approved one), not just .data[0].id (same defect/fix
            # as the auto-detect branch). Stashed in SELECTED_IDS so the
            # post-resolution gate below reuses it instead of probing this
            # same URL a second time.
            SELECTED_IDS="$(probe_models "$BASE_URL")"
            [ -z "$SELECTED_IDS" ] && { echo "ERROR: preflight failed (endpoint_unreachable): no server responding at $BASE_URL (provider $PROVIDER). Start llama-server or pass -m." >&2; exit 1; }
            MODEL="$(pick_id "$SELECTED_IDS")"
        else
            MODEL="$(pick_id "$(probe_models "$BASE_URL")")"
            [ -z "$MODEL" ] && { echo "ERROR: preflight failed (endpoint_unreachable): no server responding at $BASE_URL (provider $PROVIDER). Start llama-server or pass -m." >&2; exit 1; }
        fi
    fi
else
    # Probe every provider in ascending port order; first live one wins.
    # With --approved-only, a live provider serving an unapproved id is
    # skipped (not treated as a match) so probing continues to the next port.
    # A forced -m (MODEL already set) narrows this further: a provider only
    # qualifies if it actually serves THAT id, not merely some approved id.
    BASE_URL=""
    SAW_UNAPPROVED_LIVE=""
    while IFS=$'\t' read -r _port name base_url; do
        [ -z "$base_url" ] && continue
        if [ -n "$APPROVED_ONLY" ]; then
            served=""
            ids="$(probe_models "$base_url")"
            if [ -n "$ids" ]; then
                if [ -n "$MODEL" ]; then
                    grep -qFx -- "$MODEL" <<< "$ids" && served="$MODEL"
                else
                    served="$(pick_id "$ids")"
                fi
            fi
            if [ -z "$served" ]; then
                if [ -n "$ids" ]; then
                    SAW_UNAPPROVED_LIVE="1"
                    # Loud skip (2026-07-19 incident): a server launched with
                    # --alias served an unapproved id and every dispatch fell
                    # through to the next port for days with zero trace. Only
                    # the all-ids-unapproved case warns; a forced -m simply not
                    # being served here is normal probing, not an anomaly.
                    [ -z "$MODEL" ] && echo "WARNING: provider '$name' ($base_url) is live but serves no approved id ($(tr '\n' ' ' <<< "$ids")); skipping it. The registry ($REGISTRY) is quant-exact - if this server was started with --alias, drop the alias so it serves its real -hf id." >&2
                fi
                continue
            fi
        else
            served="$(pick_id "$(probe_models "$base_url")")"
            [ -z "$served" ] && continue
        fi
        PROVIDER="$name"
        BASE_URL="$base_url"
        [ -z "$MODEL" ] && MODEL="$served"
        [ -n "$APPROVED_ONLY" ] && SELECTED_IDS="$ids"
        break
    done < <(jq -r '
        .providers | to_entries[]
        | [ ((.value.baseUrl // "") | capture(":(?<p>[0-9]+)").p // "0" | tonumber),
            .key, (.value.baseUrl // "") ] | @tsv
    ' "$MODELS_JSON" < /dev/null | sort -n)
    if [ -z "$PROVIDER" ]; then
        if [ -n "$APPROVED_ONLY" ] && [ -n "$SAW_UNAPPROVED_LIVE" ]; then
            if [ -n "$MODEL" ]; then
                # MODEL was forced by -m and passed the front-gate registry
                # check, so it IS approved — it is simply not live anywhere.
                # Other approved ids may well be live; naming THIS id (not a
                # blanket "no approved id is live" claim) keeps the refusal true.
                echo "ERROR: preflight failed (model_id_missing): forced model id '$MODEL' is not live on any provider in $MODELS_JSON (registry: $REGISTRY)." >&2
            else
                echo "ERROR: preflight failed (model_id_missing): no approved model id is live on any provider in $MODELS_JSON (registry: $REGISTRY)." >&2
            fi
        else
            echo "ERROR: preflight failed (endpoint_unreachable): no llama-server responding on any provider in $MODELS_JSON. Start one (e.g. llama-server ... --port 8080)." >&2
        fi
        exit 1
    fi
fi

# Post-resolution gate: the one invariant that must hold on EVERY resolution
# path under --approved-only, not just -P+-m — whatever MODEL was finally
# resolved must actually be served by the finally-selected provider. Reuses
# SELECTED_IDS from resolution above when a listing was already fetched for
# this provider, so it is probed at most once.
if [ -n "$APPROVED_ONLY" ]; then
    [ -z "${SELECTED_IDS+x}" ] && SELECTED_IDS="$(probe_models "$BASE_URL")"
    if [ -z "$SELECTED_IDS" ]; then
        echo "ERROR: preflight failed (endpoint_unreachable): no server responding at $BASE_URL (provider $PROVIDER). Start llama-server or pass -m." >&2
        exit 1
    fi
    if ! grep -qFx -- "$MODEL" <<< "$SELECTED_IDS"; then
        # By construction every resolution path above only ever settles on an
        # approved MODEL (front-gate check for a forced -m, is_approved
        # filtering for an auto-picked one) — so a mismatch here means the
        # provider just doesn't serve it, not that it is unapproved. Only a
        # forced-empty edge case (no served id was ever approved) leaves
        # MODEL genuinely absent from the registry; keep that wording for it.
        if is_approved "$MODEL"; then
            echo "ERROR: preflight failed (model_id_missing): '$MODEL' is approved but not served by provider '$PROVIDER' at $BASE_URL (registry: $REGISTRY)." >&2
        else
            echo "ERROR: preflight failed (model_id_missing): '$MODEL' at $BASE_URL (provider $PROVIDER) is not in the approved registry ($REGISTRY)." >&2
        fi
        exit 1
    fi
fi
echo "Using provider '$PROVIDER' model '$MODEL'" >&2

# Honest preflight gate: the listing above only picked a candidate; a real
# 1-token completion decides. Refuse BEFORE any pi dispatch so a broken worker
# spawn surfaces as a preflight failure, not a mid-run pi error.
if ! probe_completion "$BASE_URL" "$MODEL"; then
    echo "ERROR: preflight failed (completion_failed): '$MODEL' at $BASE_URL lists but cannot serve a 1-token completion (worker spawn failure?). Fix the backend (LlamaBarn: re-download the model runtime or reinstall), then verify with: curl ${BASE_URL}/chat/completions" >&2
    exit 1
fi

if [ "$MODE" = "preflight" ]; then
    echo "preflight: healthy (provider '$PROVIDER', model '$MODEL')"
    exit 0
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
            echo "ERROR: Prompt required for interactive mode" >&2
            usage >&2
            exit 1
        fi
        run_cmd pi "${ARGS[@]}" "$PROMPT"
        ;;
    prompt)
        if [ -z "$PROMPT" ]; then
            echo "ERROR: Prompt required" >&2
            usage >&2
            exit 1
        fi
        # Non-interactive dispatch: guard child stdin so an unattended batch
        # can never hang on a child reading the inherited stdin (PRD 00040
        # hang class). Interactive/resume modes keep stdin — they need the TTY.
        run_cmd pi "${ARGS[@]}" -p "$PROMPT" < /dev/null
        ;;
esac
