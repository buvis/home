---
catchup: skip
design: skip
---

# Close the chores the autopilot extraction orphaned

Source: backlog review of the plugin repo, 2026-08-26 (`~/git/src/github.com/buvis/claude-autopilot/dev/local/audit-results/backlog-review-2026-08-26.md`, decisions D1 and D2). When the autopilot pack moved to `buvis/claude-autopilot` on 2026-08-25, three items in its PRDs targeted files that stayed here; the plugin's batch cannot write outside its own repo, so they come home. Numbering note: this repo's scan allocates 00146; the plugin repo already carries a 00146 of its own (cap-out deferrals). Same name, different repos.

## Problem

1. `dev/local/prds/done/00120-migrate-task-tracking-to-statectl-v1.md` line 169 accepts Phase 1 with "same rg sweep over `skills/work/` = 0 hits", which `check_build_overhead.py` and its test falsify (they name the retired tools on purpose) while the Success Metric (instruction text = 0) holds. Historical now that the skill tree moved, but a reader grounding against it gets a false failure.
2. `skills/audit-qwen/scripts/audit_qwen.py:229` counts `reports/*state*archived*.json` as its archived-state input and `:452-453` admits nothing writes such files. The plugin's PRD 00143 makes `complete-prd` append one JSONL row per attempt to `<repo>/dev/local/autopilot/ledger/attempts.jsonl`, shaped `{"batch_id", "prd", "task_id", "task_name", "task_model", "qwen_eligible", "recorded_at", "attempt": <verbatim attempt object>}`. Nothing reads it.
3. `hooks/tests/` has no test-author-facing contract for `hooks/_common.py` and `dispatch.py`. Tess (the plugin's test author) was briefed to drive a "marker checked before stdin" test through `_common.capture_main`, which installs its own `sys.stdin`, so the test could not fail against the old code; only the orchestrator reading the module caught it. The plugin's PRD 00141 makes `/work` hand Tess `<dir>/tests/HARNESS_CONTRACT.md` whenever a task touches `<dir>/`; this repo has to write the file for `hooks/`.

## Solution

Three independent edits in this repo, each with its own check: qualify the 00120 sweep; teach audit-qwen to read the attempt ledger (absent file = today's zero, no dependency on the plugin release); write the hooks harness contract and bind it to the live module with a completeness test.

## Requirements

### Must have
- 00120 Phase-1 bullet (line 169): the sweep reads "same rg sweep over `skills/work/`, excluding `skills/work/scripts/check_build_overhead.py` and its test, = 0 hits". Premise: the bullet still reads as an unqualified sweep; re-check before editing and skip if already qualified.
- `audit_qwen.py`: `read_attempt_ledger(path) -> list[dict]` parses `<repo>/dev/local/autopilot/ledger/attempts.jsonl` (absent -> `[]`; a malformed line is skipped loud on stderr, never fatal); the per-repo record's `archived` count becomes the ledger row count and the per-batch implementor/gate histograms read `attempt` objects from the ledger in addition to live state; the `:452-453` note about the unwritten glob is replaced by the ledger sentence. No premise on the plugin release: the reader targets the row shape 00143 froze.
- `hooks/tests/HARNESS_CONTRACT.md`: one entry per public name in `hooks/_common.py` (names not starting with `_`: today `read_input`, `block`, `allow`, `log_path`, `secret_path`, `resolve_toplevel`, `append_jsonl_row`, `parse_transcript_entries`, `HandlerTimeout`, `capture_main`) with signature and the observable behavior a test can rely on: `read_input` returns `{}` on empty, malformed or non-dict stdin and lets any other exception from `sys.stdin.read()` propagate; `allow()` raises `SystemExit(0)`; `block(reason)` prints `reason` to stderr then raises `SystemExit(2)`; `capture_main(fn, payload)` installs `io.StringIO(json.dumps(payload))` as `sys.stdin` and fresh `StringIO`s as stdout/stderr, restores all in `finally`, maps `SystemExit` codes and returns `(code, stdout, stderr)` - so a test that must patch `sys.stdin` calls the handler's `main()` directly; `HandlerTimeout` is a `BaseException` no handler may catch. Plus two dispatcher facts: `dispatch.py` imports each handler fresh per invocation and calls `run(payload)` under a SIGALRM cap; a timed-out `kind="enforcement"` route denies.
- `hooks/tests/test_harness_contract.py`: `test_every_public_helper_is_documented` introspects `hooks/_common.py` at test time and asserts every public name appears in the contract; `test_capture_main_replaces_stdin`, `test_read_input_returns_empty_dict_on_malformed_input`, `test_block_exits_two_with_reason_on_stderr` bind the three load-bearing claims to the live module.

### Nice to have
- A one-line pointer to the contract in `hooks/AGENTS.md` or the hooks README, whichever exists.

## Implementation

### Module: prd-00120-wording
- **Location**: `dev/local/prds/done/00120-migrate-task-tracking-to-statectl-v1.md`
- **Responsibility**: the qualified sweep.
- **Exports**: none (prose)

### Module: audit-qwen-ledger-reader
- **Location**: `skills/audit-qwen/scripts/audit_qwen.py`, `skills/audit-qwen/scripts/test_audit_qwen.py`
- **Responsibility**: read the attempt ledger as the archived input.
- **Exports**: `read_attempt_ledger(path) -> list[dict]`

### Module: hooks-harness-contract
- **Location**: `hooks/tests/HARNESS_CONTRACT.md`, `hooks/tests/test_harness_contract.py`
- **Responsibility**: the test-author-facing `_common.py` / `dispatch.py` contract and its binding to the live module.
- **Exports**: the four test functions named above

### Dependencies
- prd-00120-wording: No dependencies (foundation)
- hooks-harness-contract: No dependencies (foundation)
- audit-qwen-ledger-reader: No dependencies (foundation)

## Tasks

### Phase 0: Foundation
- [ ] Qualify 00120's Phase-1 sweep (premise re-checked first) - `rg -n "check_build_overhead" dev/local/prds/done/00120-migrate-task-tracking-to-statectl-v1.md` hits the qualified bullet.
- [ ] `HARNESS_CONTRACT.md` and `test_harness_contract.py` - `uv run --with pytest --with tree-sitter-language-pack pytest hooks/tests/test_harness_contract.py -q` green; removing any one public-name entry flips `test_every_public_helper_is_documented` red (spot-check once, restore).

### Phase 1: Core
- [ ] Ledger reader in audit-qwen (depends on: Phase 0) - `uv run --with pytest pytest skills/audit-qwen/scripts/test_audit_qwen.py -q` green; a fixture ledger with three rows renders non-zero implementor counts and `archived: 3`; an absent ledger renders exactly today's output.

## Success Criteria

- `test_harness_contract.py` goes red when a public helper is added to `_common.py` without a contract entry.
- audit-qwen's report card renders from a ledger fixture with the live state empty; no `*state*archived*.json` glob remains in `audit_qwen.py`.
- 00120's Phase-1 bullet no longer contradicts its own Success Metric.
