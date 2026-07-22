#!/usr/bin/env bash
# test_autoclaude_build_model.sh — sonnet-first build routing for the `autoclaude`
# loop (~/.config/bash/plugins/development.plugin.bash).
#
# Unit under test:
#   _autopilot_build_model <state.json> <prds_dir> <loop_metrics.jsonl> <ledger.json> <deferred_dir>
#
# Contract this suite pins:
#   * prints EXACTLY ONE line on stdout — "claude-opus-4-8" or "claude-sonnet-5"
#     — and NOTHING on stderr (the wrapper's stderr is the operator's log);
#   * ALWAYS exits 0 (a missing state.json is not fatal);
#   * target PRD = lowest 00XXX- basename in <prds_dir>/wip/, else in
#     <prds_dir>/backlog/ — never state.prd, which still names the FINISHED PRD
#     between PRDs;
#   * opus when ANY of: (1) target frontmatter default_model: opus,
#     (2) state.replan_count > 0, (3a) state.stall_reason != null,
#     (3b) a type:"stall" item naming the target in the 2 NEWEST
#     <deferred_dir>/*-deferred.json files, (4) state.cap_rotations non-empty,
#     (5) a <ledger.json> key equal to the target, (6) a <loop_metrics.jsonl>
#     line with .prd == target and .phase_launched == "build";
#     signals 2/3a/4 fire ONLY when state.prd == target.
#   * the launch line the wrapper builds carries the routed --model, the
#     _AUTOPILOT_MODEL_BUILD kill-switch still wins, and the review/done
#     branches are untouched.
#
# Red-first: `_autopilot_build_model` does not exist yet, so every scenario here
# fails (rc 127) until it is implemented. Two e2e rows are ALSO red against the
# current wrapper by design: a signal-free build launches Opus today, and the
# bootstrap (no state.json) launch falls into the wrapper's `*)` case arm.
#
# Everything runs in mktemp sandboxes; the plugin is sourced READ-ONLY and no
# real `claude` process is ever launched.
#
# Run: bash ~/.claude/skills/run-autopilot/scripts/test_autoclaude_build_model.sh
set -u

# ── source the plugin (stubs silence the bash-it bootstrap calls) ─────────────
cite() { :; }
about-plugin() { :; }
source ~/.config/bash/plugins/development.plugin.bash

# ── assert helpers ────────────────────────────────────────────────────────────
PASS() { echo "PASS: $1"; }
FAIL() { echo "FAIL: $1 — $2"; exit 1; }

# ── cleanup registry ──────────────────────────────────────────────────────────
_PIDS=()
_DIRS=()
cleanup() {
  local p d
  for p in "${_PIDS[@]+"${_PIDS[@]}"}"; do kill -KILL "$p" 2>/dev/null || true; done
  for d in "${_DIRS[@]+"${_DIRS[@]}"}"; do rm -rf "$d"; done
}
trap cleanup EXIT

# =============================================================================
# Unit fixtures + assertion
# =============================================================================

# init_box <dir> — a PRD lifecycle root + the three sidecar inputs. Every box
# starts signal-free: empty metrics, an empty ledger object, an empty deferred
# dir. Scenarios add exactly the one signal they are about.
init_box() {
  local d="$1"
  mkdir -p "$d/prds/wip" "$d/prds/backlog" "$d/prds/done" "$d/prds/hold" "$d/deferred"
  : >"$d/loop-metrics.jsonl"
  printf '{}\n' >"$d/ledger.json"
}

# write_prd <path> [<default_model>] — minimal PRD fixture. With no second arg
# the file has NO frontmatter block at all (the common case).
write_prd() {
  local path="$1" dm="${2-}"
  : >"$path"
  if [ -n "$dm" ]; then
    printf -- '---\ncatchup: skip\nrework_cap: 3\ndefault_model: %s\ndesign: skip\n---\n' "$dm" >>"$path"
  fi
  printf '\n# %s\n\n## Problem\n\nFixture PRD for the build-model routing suite.\n' "${path##*/}" >>"$path"
}

# write_prd_fm <path> <frontmatter-body> — like write_prd, but the frontmatter
# body is arbitrary text (any lines, any whitespace, any quoting) instead of
# the fixed catchup/rework_cap/default_model/design block. Used by the signal-1
# malformed-frontmatter rows below, which need exact control over spacing and
# quoting; write_prd itself is left untouched so the existing rows are
# unaffected.
write_prd_fm() {
  local path="$1" body="$2"
  : >"$path"
  printf -- '---\n%s\n---\n' "$body" >>"$path"
  printf '\n# %s\n\n## Problem\n\nFixture PRD for the build-model routing suite.\n' "${path##*/}" >>"$path"
}

_ASSERT_N=0
ASSERT_TMP=$(mktemp -d); _DIRS+=("$ASSERT_TMP")

# assert_model <label> <expected> <state> <prds_dir> <metrics> <ledger> <deferred_dir>
# Runs the helper in a subshell (the wrapper targets a normal interactive shell,
# so `set -u` is off there) and pins all three observable facts: exit 0, one
# single line on stdout, and that line's exact text.
assert_model() {
  local label="$1" expected="$2"
  shift 2
  _ASSERT_N=$((_ASSERT_N + 1))
  local of="$ASSERT_TMP/out.$_ASSERT_N" ef="$ASSERT_TMP/err.$_ASSERT_N" rc lines got
  ( set +u; _autopilot_build_model "$@" ) >"$of" 2>"$ef"
  rc=$?
  [ "$rc" -eq 0 ] \
    || FAIL "$label: exits 0" "rc=$rc (127 = _autopilot_build_model not defined in development.plugin.bash); stderr=$(cat "$ef")"
  # Silence on stderr is part of the contract: the wrapper runs this on every
  # launch and its stderr is the operator's log, so a jq/`ls` complaint about a
  # missing state.json or an empty deferred dir must never leak out.
  [ ! -s "$ef" ] || FAIL "$label: writes nothing to stderr" "stderr: $(cat "$ef")"
  lines=$(awk 'END{print NR}' "$of")
  [ "$lines" -eq 1 ] \
    || FAIL "$label: prints exactly one line on stdout" "got $lines line(s): $(cat "$of")"
  got=$(cat "$of")
  [ "$got" = "$expected" ] || FAIL "$label: prints $expected" "got '$got'"
  PASS "$label -> $expected"
}

# =============================================================================
# Scenario 1 — a routine PRD with no difficulty evidence runs on Sonnet.
# The ledger deliberately holds a DIFFERENT PRD's key: signal 5 is keyed on the
# target, not on "the ledger is non-empty".
# The state fields are present and EXPLICITLY ZERO — replan_count 0,
# cap_rotations [], stall_reason null — which is what a real cleared state.json
# looks like. Presence-testing (has("replan_count") …) routes every session to
# Opus and fails here, which is the whole regression this PRD exists to stop.
# =============================================================================
B1=$(mktemp -d); _DIRS+=("$B1"); init_box "$B1"
P1="00021-rotate-session-logs-v1.md"
write_prd "$B1/prds/wip/$P1"
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260701-a"}}\n' "$P1" >"$B1/state.json"
printf '{"00097-unrelated-rescue-v1.md":{"status":"approved"}}\n' >"$B1/ledger.json"
assert_model "no signals: a clean routine PRD" "claude-sonnet-5" \
  "$B1/state.json" "$B1/prds" "$B1/loop-metrics.jsonl" "$B1/ledger.json" "$B1/deferred"

# =============================================================================
# Scenario 2 — PRD-to-PRD launch. state.json still describes the PRD that just
# finished (now in done/): its replan, its stall, its rotation, its metrics line,
# its ledger key, its deferred stall. NONE of that may promote the fresh PRD
# waiting in backlog/. The finished PRD even carries default_model: opus, so any
# implementation that resolves the target from state.prd routes Opus and fails.
# =============================================================================
B2=$(mktemp -d); _DIRS+=("$B2"); init_box "$B2"
P2_DONE="00034-purge-orphan-worktrees-v1.md"
P2_NEXT="00035-stamp-release-notes-v1.md"
write_prd "$B2/prds/done/$P2_DONE" opus
write_prd "$B2/prds/backlog/$P2_NEXT"
printf '{"prd":"%s","next_phase":"build","replan_count":1,"cap_rotations":[{"task_id":"task-2","cycle":1}],"stall_reason":{"stalled":"oversized_task","detail":"task-2 kept overflowing"},"batch":{"id":"20260701-b"}}\n' \
  "$P2_DONE" >"$B2/state.json"
printf '{"ts_start":1751000000,"ts_end":1751003600,"prd":"%s","batch":"20260701-b","phase_launched":"build","phase_end":"review","signal":"continue","model":"claude-opus-4-8"}\n' \
  "$P2_DONE" >"$B2/loop-metrics.jsonl"
printf '{"%s":{"status":"consumed","batch_id":"20260701-b"}}\n' "$P2_DONE" >"$B2/ledger.json"
printf '{"batch_id":"20260701-b","items":[{"type":"stall","site":"escalation_exhausted","prd":"%s","detail":"ladder exhausted"}]}\n' \
  "$P2_DONE" >"$B2/deferred/20260701-b-deferred.json"
assert_model "PRD-to-PRD launch: the finished PRD's scratch never promotes the next PRD" "claude-sonnet-5" \
  "$B2/state.json" "$B2/prds" "$B2/loop-metrics.jsonl" "$B2/ledger.json" "$B2/deferred"

# =============================================================================
# Scenario 2b — the .prd guard, with BOTH PRDs in wip/. state.json carries a
# replan, a stall and a rotation, but they belong to the HIGHER-numbered sibling
# it names, not to the target. "The target is in wip/, so the scratch is its
# own" is a fake guard: it routes Opus here. The sibling also pins
# default_model: opus, so resolving the target from state.prd fails too.
# =============================================================================
B2B=$(mktemp -d); _DIRS+=("$B2B"); init_box "$B2B"
P2B_TARGET="00037-trim-the-boot-scan-v1.md"
P2B_SIBLING="00039-cache-the-catchup-capsule-v1.md"
write_prd "$B2B/prds/wip/$P2B_TARGET"
write_prd "$B2B/prds/wip/$P2B_SIBLING" opus
printf '{"prd":"%s","next_phase":"build","replan_count":2,"cap_rotations":[{"task_id":"task-5","cycle":1}],"stall_reason":{"stalled":"oversized_task","detail":"the sibling PRD overflowed"},"batch":{"id":"20260701-c"}}\n' \
  "$P2B_SIBLING" >"$B2B/state.json"
assert_model "the .prd guard: a wip/ sibling's replan, stall and rotation never promote the target" "claude-sonnet-5" \
  "$B2B/state.json" "$B2B/prds" "$B2B/loop-metrics.jsonl" "$B2B/ledger.json" "$B2B/deferred"

# =============================================================================
# Scenario 3 — target resolution: the LOWEST wip/ PRD wins, even when backlog/
# holds a lower number and wip/ holds a higher one. Only the lowest wip/ PRD
# carries default_model: opus, so "lowest overall" and "highest in wip" both
# route Sonnet and fail here.
# =============================================================================
B3=$(mktemp -d); _DIRS+=("$B3"); init_box "$B3"
write_prd "$B3/prds/wip/00048-rehome-the-cache-dir-v1.md" opus
write_prd "$B3/prds/wip/00061-split-render-stream-v1.md" sonnet
write_prd "$B3/prds/backlog/00012-fix-the-banner-typo-v1.md" sonnet
printf '{"next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260702-c"}}\n' >"$B3/state.json"
assert_model "target resolution: lowest wip/ PRD wins over backlog/ and over higher wip/ numbers" "claude-opus-4-8" \
  "$B3/state.json" "$B3/prds" "$B3/loop-metrics.jsonl" "$B3/ledger.json" "$B3/deferred"

# =============================================================================
# Scenario 4 — nothing selectable: wip/ and backlog/ are empty. done/ and hold/
# hold opus-frontmatter PRDs, which are NOT candidates.
# =============================================================================
B4=$(mktemp -d); _DIRS+=("$B4"); init_box "$B4"
P4_DONE="00071-ship-the-marketplace-v1.md"
write_prd "$B4/prds/done/$P4_DONE" opus
write_prd "$B4/prds/hold/00072-park-the-design-gate-v1.md" opus
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260702-d"}}\n' \
  "$P4_DONE" >"$B4/state.json"
assert_model "no PRD in wip/ or backlog/: done/ and hold/ are not candidates" "claude-sonnet-5" \
  "$B4/state.json" "$B4/prds" "$B4/loop-metrics.jsonl" "$B4/ledger.json" "$B4/deferred"

# =============================================================================
# Scenario 5 (signal 1) — the PRD author pinned Opus in frontmatter.
# =============================================================================
B5=$(mktemp -d); _DIRS+=("$B5"); init_box "$B5"
P5="00007-emit-the-batch-summary-v1.md"
write_prd "$B5/prds/wip/$P5" opus
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260703-e"}}\n' \
  "$P5" >"$B5/state.json"
assert_model "signal 1: frontmatter default_model: opus" "claude-opus-4-8" \
  "$B5/state.json" "$B5/prds" "$B5/loop-metrics.jsonl" "$B5/ledger.json" "$B5/deferred"

# =============================================================================
# Scenario 6 (signal 1 negative) — frontmatter says sonnet. The BODY quotes
# "default_model: opus" as an example (PRDs about model routing really do), so a
# whole-file grep routes Opus and fails: only the frontmatter block counts.
# =============================================================================
B6=$(mktemp -d); _DIRS+=("$B6"); init_box "$B6"
P6="00082-tune-the-echo-stopwords-v1.md"
write_prd "$B6/prds/wip/$P6" sonnet
printf '\n## Notes\n\nThe routing table example below is body prose, not frontmatter:\n\n    default_model: opus\n' \
  >>"$B6/prds/wip/$P6"
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260703-f"}}\n' \
  "$P6" >"$B6/state.json"
assert_model "signal 1 negative: frontmatter default_model: sonnet (body mention ignored)" "claude-sonnet-5" \
  "$B6/state.json" "$B6/prds" "$B6/loop-metrics.jsonl" "$B6/ledger.json" "$B6/deferred"

# =============================================================================
# Scenario 6b (signal 1 boundary) — the PRD has NO frontmatter block at all and
# its body quotes "default_model: opus". Scenario 6 can be passed by taking the
# FIRST default_model: line anywhere in the file (frontmatter happens to come
# first there); here there is no frontmatter to find, so that shortcut routes
# Opus and fails. Only a real `---` block parse survives both rows.
# =============================================================================
B6B=$(mktemp -d); _DIRS+=("$B6B"); init_box "$B6B"
P6B="00019-widen-the-qwen-gate-v1.md"
write_prd "$B6B/prds/wip/$P6B"
printf '\nThis PRD has no frontmatter. The line below is body prose:\n\n    default_model: opus\n' \
  >>"$B6B/prds/wip/$P6B"
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260703-fb"}}\n' \
  "$P6B" >"$B6B/state.json"
assert_model "signal 1 boundary: no frontmatter block, body quotes default_model: opus" "claude-sonnet-5" \
  "$B6B/state.json" "$B6B/prds" "$B6B/loop-metrics.jsonl" "$B6B/ledger.json" "$B6B/deferred"

# =============================================================================
# Scenario 6c (signal 1 MUST fire) — no space after the colon.
# =============================================================================
B6C=$(mktemp -d); _DIRS+=("$B6C"); init_box "$B6C"
P6C="00101-omit-the-colon-space-v1.md"
write_prd_fm "$B6C/prds/wip/$P6C" $'catchup: skip\ndefault_model:opus\ndesign: skip'
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260703-fc"}}\n' \
  "$P6C" >"$B6C/state.json"
assert_model "signal 1 MUST fire: default_model:opus (no space after colon)" "claude-opus-4-8" \
  "$B6C/state.json" "$B6C/prds" "$B6C/loop-metrics.jsonl" "$B6C/ledger.json" "$B6C/deferred"

# =============================================================================
# Scenario 6d (signal 1 MUST fire) — whitespace around both the key and the
# value: leading indentation, extra spaces either side of the colon, and
# trailing spaces after the value.
# =============================================================================
B6D=$(mktemp -d); _DIRS+=("$B6D"); init_box "$B6D"
P6D="00102-pad-the-frontmatter-whitespace-v1.md"
write_prd_fm "$B6D/prds/wip/$P6D" $'catchup: skip\n  default_model  :  opus  \ndesign: skip'
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260703-fd"}}\n' \
  "$P6D" >"$B6D/state.json"
assert_model "signal 1 MUST fire: leading/trailing whitespace around key and value" "claude-opus-4-8" \
  "$B6D/state.json" "$B6D/prds" "$B6D/loop-metrics.jsonl" "$B6D/ledger.json" "$B6D/deferred"

# =============================================================================
# Scenario 6e (signal 1 MUST fire) — YAML double-quoted value. /plan-tasks does
# a real YAML parse and applies its opus floor for this form; this row pins the
# two consumers to agree.
# =============================================================================
B6E=$(mktemp -d); _DIRS+=("$B6E"); init_box "$B6E"
P6E="00103-double-quote-the-opus-value-v1.md"
write_prd_fm "$B6E/prds/wip/$P6E" $'catchup: skip\ndefault_model: "opus"\ndesign: skip'
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260703-fe"}}\n' \
  "$P6E" >"$B6E/state.json"
assert_model "signal 1 MUST fire: default_model: \"opus\" (double-quoted)" "claude-opus-4-8" \
  "$B6E/state.json" "$B6E/prds" "$B6E/loop-metrics.jsonl" "$B6E/ledger.json" "$B6E/deferred"

# =============================================================================
# Scenario 6f (signal 1 MUST fire) — YAML single-quoted value. Same rationale
# as 6e, the other quote style.
# =============================================================================
B6F=$(mktemp -d); _DIRS+=("$B6F"); init_box "$B6F"
P6F="00104-single-quote-the-opus-value-v1.md"
write_prd_fm "$B6F/prds/wip/$P6F" $'catchup: skip\ndefault_model: \'opus\'\ndesign: skip'
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260703-ff"}}\n' \
  "$P6F" >"$B6F/state.json"
assert_model "signal 1 MUST fire: default_model: 'opus' (single-quoted)" "claude-opus-4-8" \
  "$B6F/state.json" "$B6F/prds" "$B6F/loop-metrics.jsonl" "$B6F/ledger.json" "$B6F/deferred"

# =============================================================================
# Scenario 6g (signal 1 MUST NOT fire) — a letter suffix on the value. A bare
# substring test treats "opus" as a prefix match and wrongly promotes.
# =============================================================================
B6G=$(mktemp -d); _DIRS+=("$B6G"); init_box "$B6G"
P6G="00105-suffix-opus-with-a-letter-v1.md"
write_prd_fm "$B6G/prds/wip/$P6G" $'catchup: skip\ndefault_model: opusX\ndesign: skip'
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260703-fg"}}\n' \
  "$P6G" >"$B6G/state.json"
assert_model "signal 1 MUST NOT fire: default_model: opusX (letter suffix)" "claude-sonnet-5" \
  "$B6G/state.json" "$B6G/prds" "$B6G/loop-metrics.jsonl" "$B6G/ledger.json" "$B6G/deferred"

# =============================================================================
# Scenario 6h (signal 1 MUST NOT fire) — a hyphenated-word suffix on the value.
# =============================================================================
B6H=$(mktemp -d); _DIRS+=("$B6H"); init_box "$B6H"
P6H="00106-suffix-opus-with-a-word-v1.md"
write_prd_fm "$B6H/prds/wip/$P6H" $'catchup: skip\ndefault_model: opus-extra\ndesign: skip'
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260703-fh"}}\n' \
  "$P6H" >"$B6H/state.json"
assert_model "signal 1 MUST NOT fire: default_model: opus-extra (word suffix)" "claude-sonnet-5" \
  "$B6H/state.json" "$B6H/prds" "$B6H/loop-metrics.jsonl" "$B6H/ledger.json" "$B6H/deferred"

# =============================================================================
# Scenario 6i (signal 1 MUST NOT fire) — a different letter suffix on the
# value, so a fix that only special-cases "X" cannot pass by accident.
# =============================================================================
B6I=$(mktemp -d); _DIRS+=("$B6I"); init_box "$B6I"
P6I="00107-suffix-opus-with-a-trailing-y-v1.md"
write_prd_fm "$B6I/prds/wip/$P6I" $'catchup: skip\ndefault_model: opusy\ndesign: skip'
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260703-fi"}}\n' \
  "$P6I" >"$B6I/state.json"
assert_model "signal 1 MUST NOT fire: default_model: opusy (any suffix)" "claude-sonnet-5" \
  "$B6I/state.json" "$B6I/prds" "$B6I/loop-metrics.jsonl" "$B6I/ledger.json" "$B6I/deferred"

# =============================================================================
# Scenario 6j (signal 1 MUST NOT fire) — a commented-out line, no leading
# whitespace before the "#".
# =============================================================================
B6J=$(mktemp -d); _DIRS+=("$B6J"); init_box "$B6J"
P6J="00108-comment-out-the-opus-line-v1.md"
write_prd_fm "$B6J/prds/wip/$P6J" $'catchup: skip\n# default_model: opus\ndesign: skip'
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260703-fj"}}\n' \
  "$P6J" >"$B6J/state.json"
assert_model "signal 1 MUST NOT fire: # default_model: opus (commented, no indent)" "claude-sonnet-5" \
  "$B6J/state.json" "$B6J/prds" "$B6J/loop-metrics.jsonl" "$B6J/ledger.json" "$B6J/deferred"

# =============================================================================
# Scenario 6k (signal 1 MUST NOT fire) — a commented-out line, WITH leading
# whitespace before the "#".
# =============================================================================
B6K=$(mktemp -d); _DIRS+=("$B6K"); init_box "$B6K"
P6K="00109-indent-the-commented-opus-line-v1.md"
write_prd_fm "$B6K/prds/wip/$P6K" $'catchup: skip\n  # default_model: opus\ndesign: skip'
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260703-fk"}}\n' \
  "$P6K" >"$B6K/state.json"
assert_model "signal 1 MUST NOT fire: # default_model: opus (commented, indented)" "claude-sonnet-5" \
  "$B6K/state.json" "$B6K/prds" "$B6K/loop-metrics.jsonl" "$B6K/ledger.json" "$B6K/deferred"

# =============================================================================
# Scenario 6l (signal 1 MUST NOT fire) — a trailing comment appended to a
# DIFFERENT key's line. There is no real default_model key in this block at
# all.
# =============================================================================
B6L=$(mktemp -d); _DIRS+=("$B6L"); init_box "$B6L"
P6L="00110-trail-a-comment-on-another-key-v1.md"
write_prd_fm "$B6L/prds/wip/$P6L" $'catchup: skip # default_model: opus\ndesign: skip'
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260703-fl"}}\n' \
  "$P6L" >"$B6L/state.json"
assert_model "signal 1 MUST NOT fire: catchup: skip # default_model: opus (trailing comment on another key)" "claude-sonnet-5" \
  "$B6L/state.json" "$B6L/prds" "$B6L/loop-metrics.jsonl" "$B6L/ledger.json" "$B6L/deferred"

# =============================================================================
# Scenario 6m (signal 1 MUST NOT fire) — mismatched quotes around the value. A
# fix that strips a leading/trailing quote character without checking they
# match must not treat this as "opus".
# =============================================================================
B6M=$(mktemp -d); _DIRS+=("$B6M"); init_box "$B6M"
P6M="00111-mismatch-the-opus-quotes-v1.md"
write_prd_fm "$B6M/prds/wip/$P6M" $'catchup: skip\ndefault_model: "opus\'\ndesign: skip'
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260703-fm"}}\n' \
  "$P6M" >"$B6M/state.json"
assert_model "signal 1 MUST NOT fire: default_model: \"opus' (mismatched quotes)" "claude-sonnet-5" \
  "$B6M/state.json" "$B6M/prds" "$B6M/loop-metrics.jsonl" "$B6M/ledger.json" "$B6M/deferred"

# =============================================================================
# Scenario 6n (signal 1 MUST NOT fire) — a legitimate non-opus default_model
# line shares the block with a commented-out opus decoy. A check that ignores
# the block's other lines (or matches on the block as one blob rather than the
# actual key) fails here.
# =============================================================================
B6N=$(mktemp -d); _DIRS+=("$B6N"); init_box "$B6N"
P6N="00112-hide-opus-behind-a-real-sonnet-line-v1.md"
write_prd_fm "$B6N/prds/wip/$P6N" $'catchup: skip\ndefault_model: sonnet\n# default_model: opus\ndesign: skip'
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260703-fn"}}\n' \
  "$P6N" >"$B6N/state.json"
assert_model "signal 1 MUST NOT fire: real default_model: sonnet alongside a commented opus decoy" "claude-sonnet-5" \
  "$B6N/state.json" "$B6N/prds" "$B6N/loop-metrics.jsonl" "$B6N/ledger.json" "$B6N/deferred"

# =============================================================================
# Scenario 7 (signal 2) — the PRD was replanned at least once. The other two
# state signals are explicitly zero, so only replan_count can be doing the work.
# =============================================================================
B7=$(mktemp -d); _DIRS+=("$B7"); init_box "$B7"
P7="00015-cap-the-review-cycles-v1.md"
write_prd "$B7/prds/wip/$P7"
printf '{"prd":"%s","next_phase":"build","replan_count":1,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260704-g"}}\n' \
  "$P7" >"$B7/state.json"
assert_model "signal 2: replan_count > 0 for the target PRD" "claude-opus-4-8" \
  "$B7/state.json" "$B7/prds" "$B7/loop-metrics.jsonl" "$B7/ledger.json" "$B7/deferred"

# =============================================================================
# Scenario 8 (signal 3a) — a live abort signal is sitting in state.json.
# =============================================================================
B8=$(mktemp -d); _DIRS+=("$B8"); init_box "$B8"
P8="00023-guard-the-park-loop-v1.md"
write_prd "$B8/prds/wip/$P8"
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":{"stalled":"escalation_exhausted","detail":"ladder exhausted at opus"},"batch":{"id":"20260704-h"}}\n' \
  "$P8" >"$B8/state.json"
assert_model "signal 3a: stall_reason present for the target PRD" "claude-opus-4-8" \
  "$B8/state.json" "$B8/prds" "$B8/loop-metrics.jsonl" "$B8/ledger.json" "$B8/deferred"

# =============================================================================
# Scenario 9 (signal 3b) — a durable stall for this PRD in a PRIOR batch's
# deferred log. state.json is clean, so this is the only evidence. The stall
# sits in the 2nd-newest file BY FILENAME: reading only the newest file routes
# Sonnet and fails.
# The mtimes are set to DISAGREE with the filename sort — the stall file is the
# oldest on disk — so an mtime-ordered window drops it and routes Sonnet too.
# The contract is a filename sort; batch ids are minted in order, but a `.bak`
# restore or a late append rewrites mtimes.
# =============================================================================
B9=$(mktemp -d); _DIRS+=("$B9"); init_box "$B9"
P9="00044-tier-the-work-pipeline-v1.md"
write_prd "$B9/prds/wip/$P9"
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260705-i"}}\n' \
  "$P9" >"$B9/state.json"
printf '{"batch_id":"202605120000","items":[{"type":"deferred-finding","prd":"00040-hoist-the-banner-v1.md","issue":"x"}]}\n' \
  >"$B9/deferred/202605120000-deferred.json"
printf '{"batch_id":"202606180000","items":[{"type":"deferred_decision","prd":"00041-thin-the-prefix-v1.md","issue":"y"},{"type":"stall","site":"wrapper_died","prd":"%s","detail":"died after 1 retry"}]}\n' \
  "$P9" >"$B9/deferred/202606180000-deferred.json"
printf '{"batch_id":"202607040000","items":[{"type":"doubt","prd":"00043-fold-the-metrics-v1.md","issue":"z"}]}\n' \
  >"$B9/deferred/202607040000-deferred.json"
# mtime order (newest first): 202605120000, 202607040000, 202606180000 — the
# exact inverse of what the filename sort says about the stall file.
touch -t 202601010000 "$B9/deferred/202606180000-deferred.json"
touch -t 202607220300 "$B9/deferred/202607040000-deferred.json"
touch -t 202607220600 "$B9/deferred/202605120000-deferred.json"
assert_model "signal 3b: a prior-batch stall naming the target (2 newest deferred files by filename)" "claude-opus-4-8" \
  "$B9/state.json" "$B9/prds" "$B9/loop-metrics.jsonl" "$B9/ledger.json" "$B9/deferred"

# =============================================================================
# Scenario 10 (signal 3b negative) — inside the 2-newest window the only stall
# names a different PRD, and the target's own entry is not a stall. The target's
# stall exists only in the 3rd-newest file, outside the window, so scanning the
# whole deferred dir routes Opus and fails — and that out-of-window file is the
# NEWEST on disk, so an mtime-ordered window pulls it in and fails too.
# =============================================================================
B10=$(mktemp -d); _DIRS+=("$B10"); init_box "$B10"
P10="00052-fold-metrics-into-the-ledger-v1.md"
write_prd "$B10/prds/wip/$P10"
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260705-j"}}\n' \
  "$P10" >"$B10/state.json"
printf '{"batch_id":"202604010000","items":[{"type":"stall","site":"design_gate","prd":"%s","detail":"old batch, outside the 2-file window"}]}\n' \
  "$P10" >"$B10/deferred/202604010000-deferred.json"
printf '{"batch_id":"202605020000","items":[{"type":"stall","site":"clarification","prd":"00050-name-the-plugins-v1.md","detail":"other PRD"}]}\n' \
  >"$B10/deferred/202605020000-deferred.json"
printf '{"batch_id":"202606030000","items":[{"type":"deferred-finding","prd":"%s","issue":"not a stall"}]}\n' \
  "$P10" >"$B10/deferred/202606030000-deferred.json"
# mtime order (newest first): 202604010000, 202606030000, 202605020000 — the
# out-of-window file holding the target's stall is the freshest on disk.
touch -t 202607220600 "$B10/deferred/202604010000-deferred.json"
touch -t 202601010000 "$B10/deferred/202605020000-deferred.json"
touch -t 202601020000 "$B10/deferred/202606030000-deferred.json"
assert_model "signal 3b negative: no stall for the target in the 2 newest deferred files" "claude-sonnet-5" \
  "$B10/state.json" "$B10/prds" "$B10/loop-metrics.jsonl" "$B10/ledger.json" "$B10/deferred"

# =============================================================================
# Scenario 10b (signal 3b negative, per-item) — the NEWEST deferred file holds
# both a stall (for another PRD) and an entry naming the target (not a stall).
# Matching per FILE ("this file has a stall and mentions the target") routes
# Opus; the type and the prd must match on the SAME item.
# =============================================================================
B10B=$(mktemp -d); _DIRS+=("$B10B"); init_box "$B10B"
P10B="00058-stamp-the-work-start-sha-v1.md"
write_prd "$B10B/prds/wip/$P10B"
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260705-jb"}}\n' \
  "$P10B" >"$B10B/state.json"
printf '{"batch_id":"202606100000","items":[]}\n' >"$B10B/deferred/202606100000-deferred.json"
printf '{"batch_id":"202607150000","items":[{"type":"stall","site":"design_gate","prd":"00057-gate-the-design-doc-v1.md","detail":"a different PRD stalled"},{"type":"deferred-finding","prd":"%s","issue":"target named, but not as a stall"}]}\n' \
  "$P10B" >"$B10B/deferred/202607150000-deferred.json"
assert_model "signal 3b negative: same file, but the stall and the target name are different items" "claude-sonnet-5" \
  "$B10B/state.json" "$B10B/prds" "$B10B/loop-metrics.jsonl" "$B10B/ledger.json" "$B10B/deferred"

# =============================================================================
# Scenario 11 (signal 4) — a context-cap rotation already fired on this PRD.
# =============================================================================
B11=$(mktemp -d); _DIRS+=("$B11"); init_box "$B11"
P11="00056-rotate-on-the-context-cap-v1.md"
write_prd "$B11/prds/wip/$P11"
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[{"task_id":"task-7","cycle":2}],"stall_reason":null,"batch":{"id":"20260706-k"}}\n' \
  "$P11" >"$B11/state.json"
assert_model "signal 4: a cap rotation already fired on the target PRD" "claude-opus-4-8" \
  "$B11/state.json" "$B11/prds" "$B11/loop-metrics.jsonl" "$B11/ledger.json" "$B11/deferred"

# =============================================================================
# Scenario 12 (signal 5) — the rescue ledger already holds a key for this PRD.
# Status is "rejected": ANY status counts, and a foreign key alongside it must
# not be mistaken for the target's.
# =============================================================================
B12=$(mktemp -d); _DIRS+=("$B12"); init_box "$B12"
P12="00076-rescue-the-ladder-with-fable-v1.md"
write_prd "$B12/prds/wip/$P12"
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260706-l"}}\n' \
  "$P12" >"$B12/state.json"
printf '{"00075-gate-on-memory-pressure-v1.md":{"status":"approved"},"%s":{"status":"rejected","decided_at":"2026-07-21T10:00:00Z"}}\n' \
  "$P12" >"$B12/ledger.json"
assert_model "signal 5: a rescue-ledger key for the target PRD (any status)" "claude-opus-4-8" \
  "$B12/state.json" "$B12/prds" "$B12/loop-metrics.jsonl" "$B12/ledger.json" "$B12/deferred"

# =============================================================================
# Scenario 12b (signal 5 negative) — the target's name appears in the ledger
# only as a VALUE inside another PRD's entry. Signal 5 is a KEY lookup, so a
# substring scan of the file routes Opus and fails.
# =============================================================================
B12B=$(mktemp -d); _DIRS+=("$B12B"); init_box "$B12B"
P12B="00081-prevent-the-defect-class-v1.md"
write_prd "$B12B/prds/wip/$P12B"
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260706-lb"}}\n' \
  "$P12B" >"$B12B/state.json"
printf '{"00080-diagnose-the-frictions-v1.md":{"status":"approved","supersedes":"%s"}}\n' \
  "$P12B" >"$B12B/ledger.json"
assert_model "signal 5 negative: the target appears only as a value, never as a ledger key" "claude-sonnet-5" \
  "$B12B/state.json" "$B12B/prds" "$B12B/loop-metrics.jsonl" "$B12B/ledger.json" "$B12B/deferred"

# =============================================================================
# Scenario 13 (signal 6) — this PRD already burned a build session. Its line is
# the FIRST of the file, with another PRD's line after it, so reading only the
# last line of loop-metrics.jsonl routes Sonnet and fails.
# =============================================================================
B13=$(mktemp -d); _DIRS+=("$B13"); init_box "$B13"
P13="00029-record-the-attempt-log-v1.md"
write_prd "$B13/prds/wip/$P13"
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260707-m"}}\n' \
  "$P13" >"$B13/state.json"
{
  printf '{"ts_start":1751100000,"ts_end":1751104000,"prd":"%s","batch":"20260707-m","phase_launched":"build","phase_end":"build","signal":"continue","model":"claude-sonnet-5"}\n' "$P13"
  printf '{"ts_start":1751110000,"ts_end":1751112000,"prd":"00028-name-the-worktrees-v1.md","batch":"20260707-m","phase_launched":"build","phase_end":"review","signal":"continue","model":"claude-sonnet-5"}\n'
} >"$B13/loop-metrics.jsonl"
assert_model "signal 6: a prior build session for the target PRD" "claude-opus-4-8" \
  "$B13/state.json" "$B13/prds" "$B13/loop-metrics.jsonl" "$B13/ledger.json" "$B13/deferred"

# =============================================================================
# Scenario 14 (signal 6 negative) — the only build line belongs to another PRD,
# and the target's own line is a review launch. Both halves of the match matter.
# =============================================================================
B14=$(mktemp -d); _DIRS+=("$B14"); init_box "$B14"
P14="00063-decommission-the-dashboard-v1.md"
write_prd "$B14/prds/wip/$P14"
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260707-n"}}\n' \
  "$P14" >"$B14/state.json"
{
  printf '{"ts_start":1751200000,"ts_end":1751203000,"prd":"00062-port-the-visuals-v1.md","batch":"20260707-n","phase_launched":"build","phase_end":"review","signal":"continue","model":"claude-sonnet-5"}\n'
  printf '{"ts_start":1751210000,"ts_end":1751213000,"prd":"%s","batch":"20260707-n","phase_launched":"review","phase_end":"build","signal":"continue","model":"claude-opus-4-8"}\n' "$P14"
} >"$B14/loop-metrics.jsonl"
assert_model "signal 6 negative: another PRD's build line and the target's review line" "claude-sonnet-5" \
  "$B14/state.json" "$B14/prds" "$B14/loop-metrics.jsonl" "$B14/ledger.json" "$B14/deferred"

# =============================================================================
# Scenario 13b (signal 6, GC-survival) — purge-devlocal trashes autopilot/**
# past 14 days, taking the primary loop-metrics.jsonl with it. The GC-exempt
# ledger/ mirror (written back to back with the primary on every append)
# survives with the target's prior build line. Reading only the primary loses
# the repeat-build signal on every idle-past-14-days repo; the mirror must be
# consulted too.
# =============================================================================
B13B=$(mktemp -d); _DIRS+=("$B13B"); init_box "$B13B"
P13B="00113-survive-the-metrics-gc-v1.md"
write_prd "$B13B/prds/wip/$P13B"
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260708-o"}}\n' \
  "$P13B" >"$B13B/state.json"
rm -f "$B13B/loop-metrics.jsonl"
mkdir -p "$B13B/ledger"
printf '{"ts_start":1751300000,"ts_end":1751303000,"prd":"%s","batch":"20260708-o","phase_launched":"build","phase_end":"review","signal":"continue","model":"claude-sonnet-5"}\n' \
  "$P13B" >"$B13B/ledger/loop-metrics.jsonl"
assert_model "signal 6 GC-survival: primary loop-metrics.jsonl gone, ledger/ mirror holds the build line" "claude-opus-4-8" \
  "$B13B/state.json" "$B13B/prds" "$B13B/loop-metrics.jsonl" "$B13B/ledger.json" "$B13B/deferred"

# =============================================================================
# Scenario 13c (signal 6, GC-survival — primary recreated empty) — the primary
# loop-metrics.jsonl exists again (a fresh, empty file — e.g. the wrapper's
# next best-effort append target after a GC) but carries no lines. An empty
# file is NOT the same as an absent one: a fix that only special-cases
# "absent" misses this far more common post-GC-recreate shape.
# =============================================================================
B13C=$(mktemp -d); _DIRS+=("$B13C"); init_box "$B13C"
P13C="00114-recreate-the-metrics-file-empty-v1.md"
write_prd "$B13C/prds/wip/$P13C"
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260708-p"}}\n' \
  "$P13C" >"$B13C/state.json"
mkdir -p "$B13C/ledger"
printf '{"ts_start":1751310000,"ts_end":1751313000,"prd":"%s","batch":"20260708-p","phase_launched":"build","phase_end":"review","signal":"continue","model":"claude-sonnet-5"}\n' \
  "$P13C" >"$B13C/ledger/loop-metrics.jsonl"
assert_model "signal 6 GC-survival: primary present but empty, ledger/ mirror holds the build line" "claude-opus-4-8" \
  "$B13C/state.json" "$B13C/prds" "$B13C/loop-metrics.jsonl" "$B13C/ledger.json" "$B13C/deferred"

# =============================================================================
# Scenario 14b (signal 6 negative, widened source not loosened match) — both
# the primary and the mirror exist. The primary's only line is ANOTHER PRD's
# build launch; the mirror's only line is the TARGET's own launch, but as a
# REVIEW, not a build. Neither source names the target with phase_launched ==
# "build", so this must stay Sonnet — proving the fix widened where signal 6
# reads from, not what it matches.
# =============================================================================
B14B=$(mktemp -d); _DIRS+=("$B14B"); init_box "$B14B"
P14B="00115-widen-the-source-not-the-match-v1.md"
write_prd "$B14B/prds/wip/$P14B"
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260708-q"}}\n' \
  "$P14B" >"$B14B/state.json"
printf '{"ts_start":1751320000,"ts_end":1751323000,"prd":"00097-a-different-prd-v1.md","batch":"20260708-q","phase_launched":"build","phase_end":"review","signal":"continue","model":"claude-sonnet-5"}\n' \
  >"$B14B/loop-metrics.jsonl"
mkdir -p "$B14B/ledger"
printf '{"ts_start":1751321000,"ts_end":1751324000,"prd":"%s","batch":"20260708-q","phase_launched":"review","phase_end":"build","signal":"continue","model":"claude-opus-4-8"}\n' \
  "$P14B" >"$B14B/ledger/loop-metrics.jsonl"
assert_model "signal 6 negative: primary names another PRD's build, mirror names the target's review" "claude-sonnet-5" \
  "$B14B/state.json" "$B14B/prds" "$B14B/loop-metrics.jsonl" "$B14B/ledger.json" "$B14B/deferred"

# =============================================================================
# Scenario 13d (signal 6, ordinary pre-GC path preserved) — the mirror does
# not exist at all (a batch predating the ledger/ mirror writer, or one that
# has never been through a GC). The primary alone carries the target's build
# line. Pins that adding the mirror as a second source did not disturb the
# original, still-common path.
# =============================================================================
B13D=$(mktemp -d); _DIRS+=("$B13D"); init_box "$B13D"
P13D="00116-keep-the-primary-only-path-v1.md"
write_prd "$B13D/prds/wip/$P13D"
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260708-r"}}\n' \
  "$P13D" >"$B13D/state.json"
printf '{"ts_start":1751330000,"ts_end":1751333000,"prd":"%s","batch":"20260708-r","phase_launched":"build","phase_end":"review","signal":"continue","model":"claude-sonnet-5"}\n' \
  "$P13D" >"$B13D/loop-metrics.jsonl"
assert_model "signal 6: mirror absent, primary alone carries the target's build line" "claude-opus-4-8" \
  "$B13D/state.json" "$B13D/prds" "$B13D/loop-metrics.jsonl" "$B13D/ledger.json" "$B13D/deferred"

# =============================================================================
# Scenario 14c (signal 6 negative, tail bound preserved on the mirror) — the
# primary is gone (GC'd) and the mirror alone has evidence, but the target's
# build line is the OLDEST line in a 206-line mirror: 205 newer filler lines
# for a different PRD follow it, so it falls outside the newest 200. Whatever
# 200-line bound applies to the primary must apply to the mirror too, or the
# mirror becomes an unbounded scan.
# =============================================================================
B14C=$(mktemp -d); _DIRS+=("$B14C"); init_box "$B14C"
P14C="00117-bound-the-mirror-tail-v1.md"
write_prd "$B14C/prds/wip/$P14C"
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260708-s"}}\n' \
  "$P14C" >"$B14C/state.json"
rm -f "$B14C/loop-metrics.jsonl"
mkdir -p "$B14C/ledger"
{
  printf '{"ts_start":1751340000,"ts_end":1751343000,"prd":"%s","batch":"20260708-s","phase_launched":"build","phase_end":"review","signal":"continue","model":"claude-sonnet-5"}\n' \
    "$P14C"
  for _n in $(seq 1 205); do
    printf '{"ts_start":%s,"ts_end":%s,"prd":"00098-fill-the-mirror-tail-v1.md","batch":"20260708-s","phase_launched":"review","phase_end":"build","signal":"continue","model":"claude-sonnet-5"}\n' \
      "$((1751340000 + _n))" "$((1751340100 + _n))"
  done
} >"$B14C/ledger/loop-metrics.jsonl"
assert_model "signal 6 negative: the mirror's 200-line tail bound is preserved (target's build line pushed out)" "claude-sonnet-5" \
  "$B14C/state.json" "$B14C/prds" "$B14C/loop-metrics.jsonl" "$B14C/ledger.json" "$B14C/deferred"

# =============================================================================
# Scenario 15 (degenerate) — no state.json at all (first launch of a batch).
# Signals 2/3a/4 simply do not fire; this must not be fatal.
# Two PRDs wait in backlog/ and only the HIGHER one pins Opus, so backlog
# selection that takes the highest (or any) 00XXX- basename fails here.
# =============================================================================
B15=$(mktemp -d); _DIRS+=("$B15"); init_box "$B15"
write_prd "$B15/prds/backlog/00003-register-the-running-loop-v1.md"
write_prd "$B15/prds/backlog/00009-escalate-the-model-ladder-v1.md" opus
assert_model "no state.json: the LOWEST backlog PRD is the target (not fatal)" "claude-sonnet-5" \
  "$B15/state.json" "$B15/prds" "$B15/loop-metrics.jsonl" "$B15/ledger.json" "$B15/deferred"

# =============================================================================
# Scenario 16 (degenerate + signal 1) — no state.json, and the LOWEST backlog
# PRD pins Opus while a higher sibling pins Sonnet: the state-independent
# signals still evaluate, and backlog ordering is pinned from the other side.
# =============================================================================
B16=$(mktemp -d); _DIRS+=("$B16"); init_box "$B16"
write_prd "$B16/prds/backlog/00004-pin-the-plugin-versions-v1.md" opus
write_prd "$B16/prds/backlog/00011-render-the-portfolio-brief-v1.md" sonnet
assert_model "no state.json: the lowest backlog PRD's frontmatter signal still evaluates" "claude-opus-4-8" \
  "$B16/state.json" "$B16/prds" "$B16/loop-metrics.jsonl" "$B16/ledger.json" "$B16/deferred"

# =============================================================================
# End-to-end: drive `autoclaude` and assert the launch line's --model
# =============================================================================

# Global stubs (win over external commands; defined AFTER the unit scenarios so
# those exercise the real interpreter). Never touch the real machine: no
# memory-pressure wait, no real notifications/purges, no tracon TUI, no real
# wall-clock sidecar.
export _AUTOPILOT_TRACON=0
sysctl() { echo 1; }                                   # no memory pressure
python3() {
  case "$*" in
    *_walk_up.py*)           printf '%s\n' "$AP_DIR" ;; # resolve ap dir -> sandbox
    *detect_usage_limit.py*) return 1 ;;                # not usage-limited
    *notify.py*)             : ;;                       # swallow notifications
    *purge_devlocal.py*)     : ;;                       # swallow the drained-path purge
    *)                       command python3 "$@" ;;    # real python3 (mtime, render_stream)
  esac
}
_autopilot_session_cap() { :; }                        # no real wall-clock sidecar

# Hermetic defaults: clear any model knobs inherited from the caller's
# environment so the e2e rows assert the true built-in routing. Scenario e2 sets
# its own value via a per-invocation command prefix, which overrides this unset
# for that call only.
unset _AUTOPILOT_MODEL_BUILD _AUTOPILOT_MODEL_REVIEW _AUTOPILOT_MODEL_DONE \
      _AUTOPILOT_FALLBACK_MODEL _AUTOPILOT_EFFORT_BUILD

# run_with_timeout <sandbox_dir> <timeout_secs> — runs `autoclaude` inside the
# sandbox (cwd + PATH pointed at its bin/ stub) under a safety kill, so a
# non-converging loop is force-killed rather than hanging the suite. Exit code
# lands in $RUN_RC; if the safety kill fired, <sandbox_dir>/.timeout-fired exists.
run_with_timeout() {
  local dir="$1" timeout="$2"
  (
    cd "$dir" || exit 90
    AP_DIR="$dir/dev/local/autopilot"
    _AUTOPILOT_LOOPS_DIR="$dir/loops"
    PATH="$dir/bin:$PATH"
    # This suite may itself run from inside an autoclaude loop, which exports
    # _AUTOPILOT_TRACON_CHILD and _AUTOPILOT_LOOP into every subshell and would
    # trip the sandboxed loop's pgrp self-guard. Strip both.
    unset _AUTOPILOT_TRACON_CHILD _AUTOPILOT_LOOP
    # The wrapper targets a normal interactive shell (no set -u).
    set +u
    autoclaude
  ) >"$dir/stdout.log" 2>"$dir/stderr.log" &
  local run_pid=$!
  ( sleep "$timeout"; touch "$dir/.timeout-fired"; kill -KILL "$run_pid" 2>/dev/null ) &
  local safety_pid=$!
  _PIDS+=("$run_pid" "$safety_pid")
  wait "$run_pid" 2>/dev/null
  RUN_RC=$?
  kill "$safety_pid" 2>/dev/null
  wait "$safety_pid" 2>/dev/null
}

# init_e2e_box <sandbox_dir> — sandbox layout + a `claude` stub that RECORDS its
# own argv and then writes a TERMINAL state.json, so the wrapper's decision table
# takes signal=done after exactly one launch.
init_e2e_box() {
  local dir="$1"
  mkdir -p "$dir/dev/local/autopilot" "$dir/dev/local/prds/wip" "$dir/dev/local/prds/backlog" "$dir/bin"
  cat >"$dir/bin/claude" <<'EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")/.." && pwd)"
printf '%s\n' "$*" >>"$DIR/claude-argv"
printf '%s\n' '{"prd":"00099-drained-v1.md","next_phase":""}' >"$DIR/dev/local/autopilot/state.json"
echo '{"type":"result","subtype":"success","total_cost_usd":0.01,"usage":{"output_tokens":10}}'
exit 0
EOF
  chmod +x "$dir/bin/claude"
}

# assert_drained <sandbox_dir> <label> — the loop ran and converged; without this
# a --model assertion could pass on a loop that died before it mattered.
assert_drained() {
  local dir="$1" label="$2"
  [ -f "$dir/.timeout-fired" ] && FAIL "$label" "safety timeout — loop did not converge within 25s"
  [ "$RUN_RC" -eq 0 ] \
    || FAIL "$label: drained loop returns 0" "rc=$RUN_RC; stdout=$(cat "$dir/stdout.log" 2>/dev/null); stderr=$(cat "$dir/stderr.log" 2>/dev/null)"
  grep -q "Backlog drained" "$dir/stdout.log" \
    || FAIL "$label: prints Backlog drained" "$(cat "$dir/stdout.log" 2>/dev/null)"
}

# assert_launch_model <sandbox_dir> <label> <expected_model> [<forbidden_string>] [<expected_effort>]
assert_launch_model() {
  local dir="$1" label="$2" expected="$3" forbid="${4-}" effort="${5-}"
  local f="$dir/claude-argv" lines argv
  [ -f "$f" ] || FAIL "$label: a session was launched" "no argv recorded at $f"
  lines=$(awk 'END{print NR}' "$f")
  [ "$lines" -eq 1 ] || FAIL "$label: exactly one session launched" "got $lines launches: $(cat "$f")"
  argv=$(cat "$f")
  case "$argv" in
    *"--model $expected"*) : ;;
    *) FAIL "$label: launches with --model $expected" "argv: $argv" ;;
  esac
  if [ -n "$forbid" ]; then
    case "$argv" in
      *"$forbid"*) FAIL "$label: launch line must not mention $forbid" "argv: $argv" ;;
    esac
  fi
  # The branch's OTHER defaults must not move while the model is rerouted.
  if [ -n "$effort" ]; then
    case "$argv" in
      *"--effort $effort"*) : ;;
      *) FAIL "$label: launches with --effort $effort" "argv: $argv" ;;
    esac
  fi
  PASS "$label: launch line carries --model $expected${effort:+ --effort $effort}"
}

# ── e2e 1 — a signal-free build launch routes Sonnet ──────────────────────────
E1=$(mktemp -d); _DIRS+=("$E1"); init_e2e_box "$E1"
E1_PRD="00088-thin-the-boot-prefix-v1.md"
write_prd "$E1/dev/local/prds/wip/$E1_PRD"
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260708-e2e-build"}}\n' \
  "$E1_PRD" >"$E1/dev/local/autopilot/state.json"
run_with_timeout "$E1" 25
assert_drained "$E1" "e2e build (signal-free)"
assert_launch_model "$E1" "e2e build (signal-free)" "claude-sonnet-5" "claude-opus-4-8" "xhigh"

# ── e2e 2 — the _AUTOPILOT_MODEL_BUILD kill-switch wins over the routing ──────
E2=$(mktemp -d); _DIRS+=("$E2"); init_e2e_box "$E2"
write_prd "$E2/dev/local/prds/wip/$E1_PRD"
printf '{"prd":"%s","next_phase":"build","replan_count":0,"cap_rotations":[],"stall_reason":null,"batch":{"id":"20260708-e2e-build"}}\n' \
  "$E1_PRD" >"$E2/dev/local/autopilot/state.json"
_AUTOPILOT_MODEL_BUILD=claude-opus-4-8 run_with_timeout "$E2" 25
assert_drained "$E2" "e2e build (_AUTOPILOT_MODEL_BUILD kill-switch)"
assert_launch_model "$E2" "e2e build (_AUTOPILOT_MODEL_BUILD kill-switch)" "claude-opus-4-8" "" "xhigh"

# ── e2e 3 — bootstrap: no state.json, one signal-free PRD in backlog/ ─────────
E3=$(mktemp -d); _DIRS+=("$E3"); init_e2e_box "$E3"
write_prd "$E3/dev/local/prds/backlog/00090-bootstrap-the-first-launch-v1.md"
run_with_timeout "$E3" 25
assert_drained "$E3" "e2e bootstrap (no state.json)"
assert_launch_model "$E3" "e2e bootstrap (no state.json)" "claude-sonnet-5" "claude-opus-4-8"

# ── e2e 4 — the review branch is untouched ────────────────────────────────────
E4=$(mktemp -d); _DIRS+=("$E4"); init_e2e_box "$E4"
E4_PRD="00091-converge-the-review-loop-v1.md"
write_prd "$E4/dev/local/prds/wip/$E4_PRD"
printf '{"prd":"%s","next_phase":"review","batch":{"id":"20260708-e2e-review"}}\n' "$E4_PRD" \
  >"$E4/dev/local/autopilot/state.json"
run_with_timeout "$E4" 25
assert_drained "$E4" "e2e review branch"
assert_launch_model "$E4" "e2e review branch" "claude-opus-4-8"

# ── e2e 5 — the done branch is untouched ──────────────────────────────────────
E5=$(mktemp -d); _DIRS+=("$E5"); init_e2e_box "$E5"
E5_PRD="00092-render-the-batch-report-v1.md"
write_prd "$E5/dev/local/prds/wip/$E5_PRD"
printf '{"prd":"%s","next_phase":"done","batch":{"id":"20260708-e2e-done"}}\n' "$E5_PRD" \
  >"$E5/dev/local/autopilot/state.json"
run_with_timeout "$E5" 25
assert_drained "$E5" "e2e done branch"
assert_launch_model "$E5" "e2e done branch" "claude-sonnet-5" "claude-opus-4-8"

# =============================================================================
echo ""
echo "All checks passed."
exit 0
