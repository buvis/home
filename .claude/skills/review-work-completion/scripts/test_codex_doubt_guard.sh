#!/usr/bin/env bash
# test_codex_doubt_guard.sh — codex doubt-roster guard predicate (PRD 00077)
#
# Rule under test: when a PRD's tasks include ANY codex-implemented attempt,
# the doubt lens must not be codex alone — the resolved doubt reviewer is
# forced to `fable` (Eve joins Bob as a fifth lens). The guard's single
# documented home is a jq predicate that lives in
# ~/.claude/skills/review-work-completion/SKILL.md:
#
#   any(state.tasks[]?.attempts[]?.implementor == "codex")
#
# This suite EXTRACTS that predicate text from SKILL.md rather than
# hardcoding its own copy — a copy would only prove jq works, not that the
# documented rule and the real rule stayed in sync. If someone edits the
# expression in SKILL.md later, this suite catches the drift instead of it
# surfacing live in a review cycle.
#
# It is RED today by design: SKILL.md does not yet carry the predicate
# (the implementor writes that prose separately), so extraction must fail
# loud rather than skip silently.
#
# Run: bash ~/.claude/skills/review-work-completion/scripts/test_codex_doubt_guard.sh
set -u

SKILL_MD="/Users/bob/.claude/skills/review-work-completion/SKILL.md"
CHECK_SCRIPT="/Users/bob/.claude/skills/review-work-completion/scripts/check_review_file.py"

# ── assert helpers (house style: plain bash, no framework, exit 1 on fail) ───
PASS() { echo "PASS: $1"; }
FAIL() { echo "FAIL: $1 - $2"; exit 1; }

# ── extract the predicate from SKILL.md (never hardcode it) ─────────────────
# The predicate's line carries all three markers at once: "implementor",
# "codex", and the "any(" construct. Filter down to that line, then pull the
# any(...) expression itself back out of whatever prose surrounds it.
candidate_lines=$(rg -n 'implementor' "$SKILL_MD" 2>/dev/null | rg 'codex' | rg 'any\(')

if [ -z "$candidate_lines" ]; then
  FAIL "predicate must exist in SKILL.md" "predicate not found in SKILL.md - the guard's documented home moved or the rule was deleted"
fi

first_line=$(printf '%s\n' "$candidate_lines" | head -n1 | sed 's/^[0-9]*://')
predicate=$(printf '%s\n' "$first_line" | rg -o 'any\([^)]*\)' | head -n1)

if [ -z "$predicate" ]; then
  FAIL "any(...) expression isolated from the candidate line" "found a line naming the guard but could not isolate the any(...) expression from: $first_line"
fi

PASS "predicate extracted from SKILL.md: $predicate"

# ── jq harness ────────────────────────────────────────────────────────────
# any(condition) is any(.[]; condition): it iterates the CURRENT input's
# elements and re-evaluates condition once per element, using that element
# as the new ".". The predicate's own "state.tasks[]..." reference must
# stay the ROOT document across every iteration, not whatever "." any() is
# iterating over — so "state" is bound to $root, captured before any()
# runs. This is plumbing that defines what "state" means; it does not
# rewrite or supplement the guard's own logic.
run_predicate() {
  jq ". as \$root | def state: \$root; ${predicate}" "$1"
}

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# Fixture A and Fixture B differ ONLY in implementor values — same task
# count (3), same attempts-per-task (1, 2, 1), same keys throughout — so a
# pass proves the predicate keys specifically on "implementor", not on
# shape or on "any attempt existing at all".
cat >"$TMP/fixture-a-codex-present.json" <<'JSON'
{
  "tasks": [
    {"id": "T1", "attempts": [{"implementor": "claude"}]},
    {"id": "T2", "attempts": [{"implementor": "qwen"}, {"implementor": "codex"}]},
    {"id": "T3", "attempts": [{"implementor": "claude"}]}
  ]
}
JSON

cat >"$TMP/fixture-b-no-codex.json" <<'JSON'
{
  "tasks": [
    {"id": "T1", "attempts": [{"implementor": "claude"}]},
    {"id": "T2", "attempts": [{"implementor": "qwen"}, {"implementor": "gemini"}]},
    {"id": "T3", "attempts": [{"implementor": "claude"}]}
  ]
}
JSON

# Real state files exhibit both absence shapes the "?" optional-iteration
# chain exists for: a task present with no attempts[] key at all, and a
# state object with no tasks[] key at all. A predicate that crashed on
# either instead of returning false would be a real bug.
cat >"$TMP/fixture-c-task-no-attempts.json" <<'JSON'
{
  "tasks": [
    {"id": "T1"},
    {"id": "T2", "attempts": [{"implementor": "claude"}]}
  ]
}
JSON

cat >"$TMP/fixture-d-no-tasks-key.json" <<'JSON'
{"prd": "00001-x.md"}
JSON

# ── coverage 1: a codex attempt anywhere in the plan trips the guard ────────
out=$(run_predicate "$TMP/fixture-a-codex-present.json")
rc=$?
[ "$rc" -eq 0 ] || FAIL "codex present: jq exits clean (no crash)" "jq exited $rc, output: $out"
[ "$out" = "true" ] || FAIL "a codex attempt anywhere in the plan trips the guard" "got '$out', expected 'true'"
PASS "a codex attempt anywhere in the plan trips the guard (mixed with claude/qwen attempts)"

# ── coverage 2: an all-non-codex plan never trips the guard ─────────────────
out=$(run_predicate "$TMP/fixture-b-no-codex.json")
rc=$?
[ "$rc" -eq 0 ] || FAIL "no codex: jq exits clean (no crash)" "jq exited $rc, output: $out"
[ "$out" = "false" ] || FAIL "an all-non-codex plan (claude/qwen/gemini) never trips the guard" "got '$out', expected 'false'"
PASS "an all-non-codex plan (claude/qwen/gemini) never trips the guard"

# ── coverage 3: a task missing attempts[] entirely is "no codex", not a crash ─
out=$(run_predicate "$TMP/fixture-c-task-no-attempts.json")
rc=$?
[ "$rc" -eq 0 ] || FAIL "task with no attempts[] key: jq must exit 0, not error, on the optional ? chain" "jq exited $rc, output: $out"
[ "$out" = "false" ] || FAIL "a task with no attempts[] key at all reads as no codex" "got '$out', expected 'false'"
PASS "a task with no attempts[] key at all reads as no codex, and jq exits 0 rather than erroring"

# ── coverage 4: a state with no tasks[] at all is "no codex", not a crash ───
out=$(run_predicate "$TMP/fixture-d-no-tasks-key.json")
rc=$?
[ "$rc" -eq 0 ] || FAIL "state with no tasks[] key: jq must exit 0, not error, on the optional ? chain" "jq exited $rc, output: $out"
[ "$out" = "false" ] || FAIL "a state with no tasks[] key at all reads as no codex" "got '$out', expected 'false'"
PASS "a state with no tasks[] key at all reads as no codex, and jq exits 0 rather than erroring"

# ── coverage 5/6: the rendered audit line, extracted from its prose home ────
# check_review_file.py enforces (or soon will enforce) the exact grammar
# documented in prose at SKILL.md:250 for the codex_rung_guard audit line.
# That grammar has two literal forms — the "fired (N ...)" form and the
# "not fired" form — both quoted in backticks on the same prose line. This
# coverage EXTRACTS both forms from that prose rather than hardcoding or
# computing them, for the same reason as the predicate extraction above: a
# hardcoded copy would only prove the gate's regex is internally consistent,
# never that it agrees with the documented rule — which is the one failure
# this coverage exists to catch for a grammar whose only home is prose. If
# the prose moves, is reworded, or is deleted, extraction fails loud below
# rather than the suite silently asserting its own arithmetic against
# itself.
guard_line=$(rg -n 'codex_rung_guard: fired' "$SKILL_MD" 2>/dev/null | rg 'codex_rung_guard: not fired')

if [ -z "$guard_line" ]; then
  FAIL "codex_rung_guard rendered-line rule must exist in SKILL.md" "no line in SKILL.md carries both the fired and not-fired forms - the rule moved, was reworded apart, or was deleted"
fi

fired_form=$(printf '%s\n' "$guard_line" | rg -o '`codex_rung_guard: fired[^`]*`' | head -n1 | sed 's/^`//; s/`$//')
notfired_form=$(printf '%s\n' "$guard_line" | rg -o '`codex_rung_guard: not fired[^`]*`' | head -n1 | sed 's/^`//; s/`$//')

if [ -z "$fired_form" ]; then
  FAIL "fired form isolated from the prose rule" "found the guard's line but could not isolate the backtick-quoted fired form from: $guard_line"
fi
if [ -z "$notfired_form" ]; then
  FAIL "not-fired form isolated from the prose rule" "found the guard's line but could not isolate the backtick-quoted not-fired form from: $guard_line"
fi

PASS "rendered-line forms extracted from SKILL.md:250 - fired: '$fired_form', not fired: '$notfired_form'"

# ── build a concrete fired line from a fixture's real count ─────────────────
# The extracted fired form carries "N" as its documented count placeholder.
# Substitute the count of codex-implemented tasks in fixture A - computed
# the same way the guard itself selects tasks, never a separately guessed
# number - so the concrete line is a real instance of the documented
# grammar, not a fabricated string.
fixture_a_codex_task_count=$(jq '[.tasks[]? | select(any(.attempts[]?; .implementor == "codex"))] | length' "$TMP/fixture-a-codex-present.json")
concrete_fired_line=$(printf '%s' "$fired_form" | sed "s/(N /($fixture_a_codex_task_count /")

if [ "$concrete_fired_line" = "$fired_form" ]; then
  FAIL "fired form's count placeholder substituted" "expected the extracted fired form to contain a '(N ' count placeholder to substitute a real count into, got: $fired_form"
fi

# ── coverage 5: the gate accepts a correctly-formed fired line ──────────────
# check_review_file.py does not enforce this grammar yet (the implementor's
# regex ships separately, after this test), so this passes trivially today.
# It becomes load-bearing the moment that regex lands: shelling out to the
# real gate here is what binds prose to script, so if the implementor's
# regex ever disagrees with this prose-extracted fired form, this goes red.
review_fired="$TMP/review-fired.md"
cat >"$review_fired" <<REVIEW
Verdict: converged
Tests: none (docs-only)
$concrete_fired_line
REVIEW

python3 "$CHECK_SCRIPT" --review-file "$review_fired" >/dev/null 2>"$TMP/fired-stderr.txt"
rc=$?
[ "$rc" -eq 0 ] || FAIL "gate accepts a correctly-formed fired line" "check_review_file.py exited $rc against '$concrete_fired_line': $(cat "$TMP/fired-stderr.txt")"
PASS "gate accepts the fired line built from the prose-extracted form: '$concrete_fired_line' (meaningful once check_review_file.py enforces the grammar)"

# ── coverage 6: the gate accepts a correctly-formed not-fired line ──────────
# Same reasoning as coverage 5: trivial pass today, load-bearing once the
# gate's regex ships.
review_notfired="$TMP/review-notfired.md"
cat >"$review_notfired" <<REVIEW
Verdict: converged
Tests: none (docs-only)
$notfired_form
REVIEW

python3 "$CHECK_SCRIPT" --review-file "$review_notfired" >/dev/null 2>"$TMP/notfired-stderr.txt"
rc=$?
[ "$rc" -eq 0 ] || FAIL "gate accepts a correctly-formed not-fired line" "check_review_file.py exited $rc against '$notfired_form': $(cat "$TMP/notfired-stderr.txt")"
PASS "gate accepts the not-fired line extracted verbatim from prose: '$notfired_form' (meaningful once check_review_file.py enforces the grammar)"

echo ""
echo "All checks passed."
exit 0
