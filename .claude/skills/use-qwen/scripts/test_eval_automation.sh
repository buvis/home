#!/usr/bin/env bash
# Test harness for run-eval.sh and promote-default.sh (macOS bash 3.2
# compatible). Stubs `pi`/`mise`, runs the shared mock-llama-server.py, and
# overrides QWEN_APPROVED_REGISTRY/QWEN_SKILL_MD/QWEN_INTEGRATION_MD/
# QWEN_TEST_SH so neither script ever touches the real production files.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
RUN_EVAL_SH="$SCRIPT_DIR/run-eval.sh"
PROMOTE_SH="$SCRIPT_DIR/promote-default.sh"
QWEN_RUN_SH="$SCRIPT_DIR/qwen-run.sh"

PASS_COUNT=0
FAIL_COUNT=0
PASS() { echo "PASS: $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
FAIL() { echo "FAIL: $1 -- $2"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

_DIRS=()
SERVER_PID=""
cleanup() {
    [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null
    local d
    for d in "${_DIRS[@]+"${_DIRS[@]}"}"; do
        rm -rf "$d"
    done
}
trap cleanup EXIT

WORK=$(mktemp -d)
_DIRS+=("$WORK")

# ── stub `pi` and `mise` on PATH (same contract as test_qwen_run.sh) ─────────
STUBDIR="$WORK/stub"
mkdir -p "$STUBDIR"
cat > "$STUBDIR/pi" <<'STUB'
#!/bin/bash
echo "stub-pi-ran"
STUB
chmod +x "$STUBDIR/pi"
cat > "$STUBDIR/mise" <<'STUB'
#!/bin/bash
if [ "${1:-}" = "env" ]; then echo "export PATH='/var/empty'"; fi
exit 0
STUB
chmod +x "$STUBDIR/mise"

# ── mock llama-server (always healthy) ────────────────────────────────────────
MODE_FILE="$WORK/mode"
echo "ok" > "$MODE_FILE"
PORT=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
python3 "$SCRIPT_DIR/mock-llama-server.py" "$PORT" "$MODE_FILE" "mock-candidate" &
SERVER_PID=$!
i=0
until curl -sf --max-time 1 "http://127.0.0.1:$PORT/v1/models" > /dev/null 2>&1; do
    i=$((i + 1))
    [ "$i" -ge 50 ] && { echo "FATAL: mock server did not start"; exit 1; }
    sleep 0.1
done

CFGDIR="$WORK/agent"
mkdir -p "$CFGDIR"
cat > "$CFGDIR/models.json" <<EOF
{"providers": {"regprov": {"baseUrl": "http://127.0.0.1:$PORT/v1", "api": "openai-completions", "apiKey": "llamacpp", "models": [{"id": "mock-candidate"}]}}}
EOF

# ── task fixtures: 6 trivial prompt files ─────────────────────────────────────
for n in 1 2 3 4 5 6; do
    echo "task $n prompt" > "$WORK/prompt$n.txt"
done

run_eval() {
    PI_CODING_AGENT_DIR="$CFGDIR" QWEN_APPROVED_REGISTRY="$WORK/registry.txt" \
        PATH="$STUBDIR:$PATH" bash "$RUN_EVAL_SH" "$@" < /dev/null
}

# ══ T1: 5/6 pass -> verdict PASS, evidence log written, no auto-commit ═══════
printf '%s\t%s\n' "$WORK/prompt1.txt" "true" > "$WORK/tasks5.tsv"
printf '%s\t%s\n' "$WORK/prompt2.txt" "true" >> "$WORK/tasks5.tsv"
printf '%s\t%s\n' "$WORK/prompt3.txt" "true" >> "$WORK/tasks5.tsv"
printf '%s\t%s\n' "$WORK/prompt4.txt" "true" >> "$WORK/tasks5.tsv"
printf '%s\t%s\n' "$WORK/prompt5.txt" "true" >> "$WORK/tasks5.tsv"
printf '%s\t%s\n' "$WORK/prompt6.txt" "false" >> "$WORK/tasks5.tsv"
: > "$WORK/registry.txt"
OUT=$(run_eval -P regprov -m mock-candidate --tasks "$WORK/tasks5.tsv" --out "$WORK/ev1.md" 2>&1)
RC=$?
if [ "$RC" -eq 0 ]; then
    PASS "5/6 gate-passing exits 0 (PASS verdict)"
else
    FAIL "5/6 gate-passing exits 0 (PASS verdict)" "rc=$RC; output: $OUT"
fi
if grep -q "Score: 5/6" "$WORK/ev1.md" && grep -q "Verdict: PASS" "$WORK/ev1.md"; then
    PASS "evidence log records the 5/6 score and PASS verdict"
else
    FAIL "evidence log records the 5/6 score and PASS verdict" "$(cat "$WORK/ev1.md" 2>/dev/null || echo MISSING)"
fi
if [ ! -s "$WORK/registry.txt" ]; then
    PASS "without --commit, the registry is left untouched even on a PASS verdict"
else
    FAIL "without --commit, the registry is left untouched even on a PASS verdict" "registry: $(cat "$WORK/registry.txt")"
fi

# ══ T2: same 5/6 fixture with --commit -> appends exactly once ═══════════════
: > "$WORK/registry.txt"
OUT=$(run_eval -P regprov -m mock-candidate --tasks "$WORK/tasks5.tsv" --out "$WORK/ev2.md" --commit 2>&1)
RC=$?
if [ "$RC" -eq 0 ] && grep -qFx "mock-candidate" "$WORK/registry.txt"; then
    PASS "--commit on a PASS verdict appends the candidate id to the registry"
else
    FAIL "--commit on a PASS verdict appends the candidate id to the registry" "rc=$RC; registry: $(cat "$WORK/registry.txt" 2>/dev/null)"
fi
run_eval -P regprov -m mock-candidate --tasks "$WORK/tasks5.tsv" --out "$WORK/ev2b.md" --commit > /dev/null 2>&1
COUNT_AFTER=$(grep -cFx "mock-candidate" "$WORK/registry.txt")
if [ "$COUNT_AFTER" = "1" ]; then
    PASS "re-running --commit for an already-registered id does not duplicate it"
else
    FAIL "re-running --commit for an already-registered id does not duplicate it" "count=$COUNT_AFTER"
fi

# ══ T3: 4/6 pass -> verdict FAIL, never appended even with --commit ══════════
printf '%s\t%s\n' "$WORK/prompt1.txt" "true" > "$WORK/tasks4.tsv"
printf '%s\t%s\n' "$WORK/prompt2.txt" "true" >> "$WORK/tasks4.tsv"
printf '%s\t%s\n' "$WORK/prompt3.txt" "true" >> "$WORK/tasks4.tsv"
printf '%s\t%s\n' "$WORK/prompt4.txt" "true" >> "$WORK/tasks4.tsv"
printf '%s\t%s\n' "$WORK/prompt5.txt" "false" >> "$WORK/tasks4.tsv"
printf '%s\t%s\n' "$WORK/prompt6.txt" "false" >> "$WORK/tasks4.tsv"
: > "$WORK/registry.txt"
OUT=$(run_eval -P regprov -m mock-candidate --tasks "$WORK/tasks4.tsv" --out "$WORK/ev3.md" --commit 2>&1)
RC=$?
if [ "$RC" -ne 0 ]; then
    PASS "4/6 gate-passing exits nonzero (FAIL verdict)"
else
    FAIL "4/6 gate-passing exits nonzero (FAIL verdict)" "rc=0; output: $OUT"
fi
if [ ! -s "$WORK/registry.txt" ]; then
    PASS "a FAIL verdict never appends to the registry, even with --commit"
else
    FAIL "a FAIL verdict never appends to the registry, even with --commit" "registry: $(cat "$WORK/registry.txt")"
fi

# ══ T4: manifest without exactly 6 tasks is a usage error ════════════════════
printf '%s\t%s\n' "$WORK/prompt1.txt" "true" > "$WORK/tasks-short.tsv"
OUT=$(run_eval -P regprov -m mock-candidate --tasks "$WORK/tasks-short.tsv" --out "$WORK/ev4.md" 2>&1)
RC=$?
if [ "$RC" -eq 2 ]; then
    PASS "a manifest with fewer than 6 tasks is refused as a usage error (exit 2)"
else
    FAIL "a manifest with fewer than 6 tasks is refused as a usage error (exit 2)" "rc=$RC; output: $OUT"
fi

# ══ T5: a candidate id the live server doesn't serve is refused upfront,
# before a single task dispatches (never silently scored against whatever
# model actually IS loaded there) ═════════════════════════════════════════
: > "$WORK/registry.txt"
OUT=$(run_eval -P regprov -m wrong-candidate-id --tasks "$WORK/tasks5.tsv" --out "$WORK/ev5.md" 2>&1)
RC=$?
if [ "$RC" -eq 2 ]; then
    PASS "a candidate id the live server does not serve is refused upfront (exit 2)"
else
    FAIL "a candidate id the live server does not serve is refused upfront (exit 2)" "rc=$RC; output: $OUT"
fi
case "$OUT" in
    *"is not being served by provider"*) PASS "the refusal names why: the id is not being served by that provider" ;;
    *) FAIL "the refusal names why: the id is not being served by that provider" "output: $OUT" ;;
esac
if [ ! -f "$WORK/ev5.md" ]; then
    PASS "no evidence log is written when the upfront check refuses (no task ever ran)"
else
    FAIL "no evidence log is written when the upfront check refuses (no task ever ran)" "$(cat "$WORK/ev5.md")"
fi

# ══════════════════════════════════════════════════════════════════════════
# promote-default.sh fixtures: throwaway copies of the 3 tied files + registry
# ══════════════════════════════════════════════════════════════════════════
PROMO="$WORK/promo"
mkdir -p "$PROMO"
cat > "$PROMO/SKILL.md" <<'EOF'
Intro line. The helper script defaults to `old-candidate-id` and exposes `-m`.

## Model Selection

- **Default: `old-name` (Q4).** Old rationale text about old candidate.
- Other bullet untouched.
EOF
cat > "$PROMO/qwen-integration.md" <<'EOF'
The helper defaults to `old-candidate-id`; `-m` overrides it.
EOF
cat > "$PROMO/test_qwen_run.sh" <<'EOF'
#!/bin/bash
SHIPPED_DEFAULT_ID="old-candidate-id"
echo "fake test suite ran"
exit 0
EOF
cat > "$PROMO/registry.txt" <<'EOF'
old-candidate-id
# Qualified 2026-07-14: 6-task agentic eval, 5/6 passed, tasks drawn from
# manifest.tsv (see evidence: ev.md). Served via llama.cpp.
new-candidate-id
EOF

promote() {
    QWEN_SKILL_MD="$PROMO/SKILL.md" QWEN_INTEGRATION_MD="$PROMO/qwen-integration.md" \
        QWEN_TEST_SH="$PROMO/test_qwen_run.sh" QWEN_APPROVED_REGISTRY="$PROMO/registry.txt" \
        QWEN_DEFAULT_MODEL_FILE="$PROMO/default-model.txt" \
        bash "$PROMOTE_SH" "$@"
}

# ══ T6: promoting an unregistered id is refused, nothing changed ═════════════
BEFORE="$(cat "$PROMO/SKILL.md")"
OUT=$(promote never-qualified-id 2>&1)
RC=$?
AFTER="$(cat "$PROMO/SKILL.md")"
if [ "$RC" -ne 0 ]; then
    PASS "promoting an id absent from the registry is refused"
else
    FAIL "promoting an id absent from the registry is refused" "rc=0; output: $OUT"
fi
if [ "$BEFORE" = "$AFTER" ]; then
    PASS "a refused promotion leaves SKILL.md untouched"
else
    FAIL "a refused promotion leaves SKILL.md untouched" "SKILL.md changed despite refusal"
fi

# ══ T7: promoting the qualified id updates all 3 files + regenerates the bullet
OUT=$(promote new-candidate-id 2>&1)
RC=$?
if [ "$RC" -eq 0 ]; then
    PASS "promoting a registry-qualified id succeeds"
else
    FAIL "promoting a registry-qualified id succeeds" "rc=$RC; output: $OUT"
fi
if grep -q "new-candidate-id" "$PROMO/SKILL.md" && ! grep -q "old-candidate-id" "$PROMO/SKILL.md"; then
    PASS "SKILL.md's literal id mentions are swapped to the new candidate"
else
    FAIL "SKILL.md's literal id mentions are swapped to the new candidate" "$(cat "$PROMO/SKILL.md")"
fi
if grep -q "new-candidate-id" "$PROMO/qwen-integration.md"; then
    PASS "qwen-integration.md's default line is swapped to the new candidate"
else
    FAIL "qwen-integration.md's default line is swapped to the new candidate" "$(cat "$PROMO/qwen-integration.md")"
fi
if grep -q 'SHIPPED_DEFAULT_ID="new-candidate-id"' "$PROMO/test_qwen_run.sh"; then
    PASS "test_qwen_run.sh's SHIPPED_DEFAULT_ID is swapped to the new candidate"
else
    FAIL "test_qwen_run.sh's SHIPPED_DEFAULT_ID is swapped to the new candidate" "$(cat "$PROMO/test_qwen_run.sh")"
fi
if grep -q "Qualified 2026-07-14 (5/6 agentic eval" "$PROMO/SKILL.md"; then
    PASS "the Default bullet is regenerated fact-only from the registry's qualification comment"
else
    FAIL "the Default bullet is regenerated fact-only from the registry's qualification comment" "$(cat "$PROMO/SKILL.md")"
fi
if grep -q "Old rationale text about old candidate" "$PROMO/SKILL.md"; then
    FAIL "the OLD candidate's narrative rationale is not carried over onto the new candidate" "old rationale still present"
else
    PASS "the OLD candidate's narrative rationale is not carried over onto the new candidate"
fi
if grep -q "Other bullet untouched" "$PROMO/SKILL.md"; then
    PASS "unrelated SKILL.md content is left untouched"
else
    FAIL "unrelated SKILL.md content is left untouched" "$(cat "$PROMO/SKILL.md")"
fi
if grep -qFx "new-candidate-id" "$PROMO/default-model.txt" 2>/dev/null; then
    PASS "promotion writes the resolution-level default-model.txt"
else
    FAIL "promotion writes the resolution-level default-model.txt" "content: $(cat "$PROMO/default-model.txt" 2>/dev/null || echo MISSING)"
fi

# ══ T8: re-promoting the same (now-default) id is a no-op ════════════════════
OUT=$(promote new-candidate-id 2>&1)
RC=$?
if [ "$RC" -eq 0 ] && printf '%s' "$OUT" | grep -q "already the documented default"; then
    PASS "re-promoting the already-default id is a no-op"
else
    FAIL "re-promoting the already-default id is a no-op" "rc=$RC; output: $OUT"
fi

# ══ T9: a failing regression suite rolls back all 3 files ════════════════════
cat > "$PROMO/SKILL.md" <<'EOF'
The helper script defaults to `new-candidate-id` and exposes `-m`.

## Model Selection

- **Default: `new-name`.** Some rationale.
EOF
cat > "$PROMO/qwen-integration.md" <<'EOF'
The helper defaults to `new-candidate-id`; `-m` overrides it.
EOF
cat > "$PROMO/test_qwen_run.sh" <<'EOF'
#!/bin/bash
SHIPPED_DEFAULT_ID="new-candidate-id"
exit 1
EOF
cat > "$PROMO/registry.txt" <<'EOF'
new-candidate-id
# Qualified 2026-07-14: 6-task agentic eval, 5/6 passed.
another-candidate-id
EOF
BEFORE_SKILL="$(cat "$PROMO/SKILL.md")"
BEFORE_TEST="$(cat "$PROMO/test_qwen_run.sh")"
BEFORE_DEFAULT="$(cat "$PROMO/default-model.txt" 2>/dev/null)"
OUT=$(promote another-candidate-id 2>&1)
RC=$?
AFTER_SKILL="$(cat "$PROMO/SKILL.md")"
AFTER_TEST="$(cat "$PROMO/test_qwen_run.sh")"
AFTER_DEFAULT="$(cat "$PROMO/default-model.txt" 2>/dev/null)"
if [ "$RC" -ne 0 ]; then
    PASS "a failing post-promotion regression suite is reported as a failure"
else
    FAIL "a failing post-promotion regression suite is reported as a failure" "rc=0; output: $OUT"
fi
if [ "$BEFORE_SKILL" = "$AFTER_SKILL" ] && [ "$BEFORE_TEST" = "$AFTER_TEST" ] && [ "$BEFORE_DEFAULT" = "$AFTER_DEFAULT" ]; then
    PASS "a failing regression suite rolls back all 4 files to their pre-promotion state"
else
    FAIL "a failing regression suite rolls back all 4 files to their pre-promotion state" "SKILL.md, test_qwen_run.sh, or default-model.txt was left modified"
fi

# ── summary ───────────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASS_COUNT passed, $FAIL_COUNT failed"
[ "$FAIL_COUNT" -eq 0 ] || exit 1
