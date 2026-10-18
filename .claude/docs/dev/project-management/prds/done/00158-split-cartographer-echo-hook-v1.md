---
default_model: opus
---

# Split the Cartographer Echo Hook

Source: PRD 00157 review (2026-09-01), Bob's R12/R13 findings, decision D -
`~/.claude/dev/local/reviews/00157-review-findings.md` (link-ok: review
satellite, GC'd with 00157; the findings are restated below).

## Problem

`hooks/cartographer-echo.py` is 1126 lines against the 800-line file target and
carries three functions over the 50-line function target: `handle()` 163,
`search_candidates_batch()` 89, `build_deny_envelope()` 55. Its test file
`hooks/tests/test_cartographer_echo.py` is 1948 lines with two test functions
over 50 (`test_audit_every_event_has_required_keys` 58,
`test_single_edit_dispatch_spawns_git_rev_parse_once` 54). All of this predates
PRD 00157; that review accepted the debt but required it tracked.

The hook is a live PreToolUse enforcement gate. `hooks/dispatch.py` loads it
fresh on every Edit, Write, MultiEdit and Bash call and blocks (exit 2) whenever
the file or a module it imports fails to load. An in-place edit that leaves the
entry file unimportable therefore locks the editing session out of Edit, Write
and Bash at once, with no way to run the suite or revert. The split must be
behavior-preserving, staged, and every write to the live file proven importable
before it lands.

## Solution

Extract four modules along the existing `# --- ... ---` section comments, one
per task, suite-green after each: rationalization catalog, ripgrep candidate
search, Bash bypass detection, and symbol extraction plus match scoring. Each
section's constants and tests move with it, and test patch targets follow the
code. Then carve the three over-limit functions into helpers under 50 lines and
split the two over-limit test functions. The hyphenated entry file keeps its
name and stays the `dispatch.py` route target; it imports the new modules
eagerly at module scope, the way it already imports `_lib_cartographer`, so a
broken helper fails closed at load rather than fail-open inside `handle()`.
Every write to the entry file goes through a staged copy that passed an import
smoke test (protocol under Tasks).

## Requirements

### Must have
- Four new snake_case modules under `hooks/`, importable by bare name like
  `_lib_cartographer`: `_echo_catalog.py`, `_echo_search.py`, `_echo_bash.py`,
  `_echo_symbols.py`, each owning one section of today's entry file (module
  blocks below). A constant moves with the section that uses it; a constant two
  sections share stays in the entry file.
- Eager module-scope imports in the entry file (`from _echo_catalog import ...`
  at the top, beside `import _lib_cartographer as lib`). No lazy imports inside
  `handle()`: the hook is fail-closed by design.
- Stage-and-smoke protocol for every write to `hooks/cartographer-echo.py`
  (spelled out under Tasks). The live entry file is never edited in place.
- Public contract unchanged: `handle(data)`, `main()`, `run(payload)` keep
  their signatures and behavior; deny envelope bytes, audit event shapes and the
  two-attempt gate are identical; `dispatch.py` ROUTES is untouched;
  `hooks/tests/test_handler_run_parity.py` and `hooks/tests/test_dispatch.py`
  are not modified.
- Size scope, no waivers: every file in the echo family (`hooks/cartographer-echo.py`,
  `hooks/_echo_*.py`, `hooks/tests/test_cartographer_echo.py`,
  `hooks/tests/test_echo_*.py`) is at most 800 lines and every function in
  them at most 50 lines, pinned by `hooks/tests/test_echo_layout.py`.
- Full hooks suite green (zero failures) after every task, using the command
  under Tasks.

### Nice to have
- A one-line module docstring on each `_echo_*.py` naming the section it came
  from.

## Implementation

### Module: _echo_catalog
- **Location**: `hooks/_echo_catalog.py`; tests `hooks/tests/test_echo_catalog.py`
- **Responsibility**: the rationalization half of `# --- two-attempt deny gate ---`
  (today L728-802): parse `rules-library/rationalizations.md` once per process,
  pick the entry whose trigger terms match a duplicate symbol.
- **Exports**: `_load_rationalizations()`, `_pick_rationalization(symbols)`,
  `_RATIONALIZATIONS_PATH`, `_RATIONALIZATIONS_CACHE` (tests patch these on
  this module, not on the entry)

### Module: _echo_search
- **Location**: `hooks/_echo_search.py`; tests `hooks/tests/test_echo_search.py`
- **Responsibility**: `# --- ripgrep candidate search ---` (today L402-606): rg
  resolution, batched candidate search, stopword filter, project-root
  resolution, with `_STOPWORDS` and the `_RG_*` constants.
- **Exports**: `_resolve_rg()`, `search_candidates_batch(symbols, root, target_file)`,
  `search_candidates(symbol, root, target_file)`, `filter_stopwords(symbols, file_path)`,
  `_resolve_project_root(file_path)`, `is_test_file_path(path)` (moved here: the
  stopword filter is its only non-entry consumer; amended 2026-09-03)

### Module: _echo_bash
- **Location**: `hooks/_echo_bash.py`; tests `hooks/tests/test_echo_bash.py`
- **Responsibility**: `# --- Bash bypass pattern detection ---` (today L607-716).
- **Exports**: `detect_bash_bypass(command, cwd)`, `_find_redirect_targets(command)`,
  `_BASH_PATTERNS`, `_BASH_SOURCE_EXTENSIONS`, `is_claude_settings_path(path)` (moved
  here: `_check_target` is its only non-entry consumer; amended 2026-09-03)

### Module: _echo_symbols
- **Location**: `hooks/_echo_symbols.py`; tests `hooks/tests/test_echo_symbols.py`
- **Responsibility**: `# --- content reconstruction & symbol extraction ---` and
  `# --- match scoring ---` (today L185-401), with `_SYMBOL_KINDS`,
  `_LANG_BY_EXT` and the scoring constants.
- **Exports**: `extract_content(tool_name, tool_input)`, `extract_symbols(content, ext)`,
  `score_match(symbol, candidate)`, `decide(symbols, candidate_groups)`, `_defined_name(snippet)`,
  `file_extension(path)`, `has_supported_extension(path)` (moved here with
  `_LANG_BY_EXT`; amended 2026-09-03)

### Module: cartographer-echo (entry)
- **Location**: `hooks/cartographer-echo.py` (name unchanged); tests
  `hooks/tests/test_cartographer_echo.py`
- **Responsibility**: skip evaluation, `handle()` carved into per-tool helpers
  (Bash path, Edit/Write path, two-attempt gate), `deny_key`,
  `build_deny_envelope`, audit emission, `main()`/`run()`.
- **Exports**: `handle(data)`, `main()`, `run(payload)`, `build_deny_envelope(matches)`,
  `deny_key(file_path, symbols)`, `evaluate_skip(tool_name, tool_input)`,
  `audit_event(...)` - signatures unchanged

### Module: test_echo_layout
- **Location**: `hooks/tests/test_echo_layout.py`
- **Responsibility**: pin the family's size targets with an `ast` walk.
- **Exports**: none (test)

### Dependencies
- _echo_catalog: No dependencies (foundation)
- _echo_bash: No dependencies (foundation)
- _echo_search: Depends on [_echo_symbols] (`_defined_name`, for definition-first
  ranking; the coupling predates the split, so search was extracted after symbols)
- _echo_symbols: Depends on [`_lib_cartographer`] (existing; tree-sitter wrapper, audit)
- cartographer-echo: Depends on [_echo_catalog, _echo_search, _echo_bash, _echo_symbols]
- test_echo_layout: Depends on [cartographer-echo] (written last)

Amended 2026-09-03 (review 1, decision 1): the Exports lists and the
`_echo_search` dependency above were corrected to the shipped module graph
after all four reviewers flagged the drift. Placement rule the build applied
for helpers this PRD did not name: a helper moves with its only non-entry
consumer and the entry imports it back, because the hyphenated entry file
cannot be imported by bare name, so a helper module can never import a
predicate from it. Details: `dev/local/tmp/00158/build-record.md`.

## Tasks

Stage-and-smoke protocol, for every task that changes `hooks/cartographer-echo.py`:

1. Land the new module and its test file first (new files; nothing imports
   them yet, so a slip there cannot block the gate). Echo denies the first
   Write of moved code as a duplicate of the live file; the retry passes by
   design.
2. Write the entry file's full new content to
   `dev/local/tmp/00158/cartographer-echo.py` (same first-Write deny, same retry).
3. Smoke-import the staged copy with `hooks/` on `sys.path`:
   `python3 -c "import importlib.util as u, sys; sys.path.insert(0, '/Users/bob/.claude/hooks'); s = u.spec_from_file_location('m', 'dev/local/tmp/00158/cartographer-echo.py'); m = u.module_from_spec(s); s.loader.exec_module(m); assert callable(m.run) and callable(m.handle)"`
   must exit 0.
4. Land it: `cp dev/local/tmp/00158/cartographer-echo.py hooks/cartographer-echo.py`
   (a plain copy; never a redirect, `tee` or `sed -i`, which Echo denies).
5. Run the suite.

Suite command ("suite green" below means it exits 0 with zero failures):
`uv run --with pytest --with tree-sitter-language-pack pytest /Users/bob/.claude/hooks/tests -q -p no:cacheprovider`

### Phase 0: Extract
- [x] Extract `_echo_catalog.py` and `test_echo_catalog.py` (the 9 catalog tests
  move; their patch targets become `_echo_catalog._RATIONALIZATIONS_PATH` /
  `_RATIONALIZATIONS_CACHE`). Premise: `hooks/cartographer-echo.py` still
  defines `_load_rationalizations` and `_pick_rationalization` under
  `# --- two-attempt deny gate ---`. Acceptance: `rg -n "def _load_rationalizations|def _pick_rationalization" hooks/cartographer-echo.py`
  prints nothing; `rg -n "^from _echo_catalog import" hooks/cartographer-echo.py`
  hits; suite green.
- [x] Extract `_echo_search.py` and `test_echo_search.py`. Premise: the
  `# --- ripgrep candidate search ---` section is present. Acceptance:
  `rg -n "def search_candidates_batch|def _resolve_rg|def filter_stopwords" hooks/cartographer-echo.py`
  prints nothing; `rg -n "^from _echo_search import" hooks/cartographer-echo.py`
  hits; suite green.
- [x] Extract `_echo_bash.py` and `test_echo_bash.py`. Premise: the
  `# --- Bash bypass pattern detection ---` section is present. Acceptance:
  `rg -n "def detect_bash_bypass|^_BASH_PATTERNS" hooks/cartographer-echo.py`
  prints nothing; `rg -n "^from _echo_bash import" hooks/cartographer-echo.py`
  hits; suite green.
- [x] Extract `_echo_symbols.py` and `test_echo_symbols.py`. Premise: the
  `# --- content reconstruction & symbol extraction ---` and
  `# --- match scoring ---` sections are present. Acceptance:
  `rg -n "def extract_symbols|def score_match|def decide" hooks/cartographer-echo.py`
  prints nothing; `rg -n "^from _echo_symbols import" hooks/cartographer-echo.py`
  hits; suite green.

Exit criteria: `wc -l hooks/cartographer-echo.py` under 800; four `_echo_*.py`
modules and four `test_echo_*.py` files exist; suite green.

### Phase 1: Carve and pin
- [x] Carve `handle()` into per-tool helpers, `search_candidates_batch()` and
  `build_deny_envelope()` into helpers, and split the two over-limit test
  functions, all at most 50 lines, signatures of the exports above unchanged
  (depends on: Phase 0). If `hooks/tests/test_cartographer_echo.py` is still
  over 800 lines, split it by entry section (skip rules / handle paths /
  dispatch and parity / audit) into `test_echo_*.py` files. Acceptance: an
  `ast` walk over the echo family reports no function over 50 lines; `wc -l`
  reports no family file over 800; `git diff --stat` names neither
  `test_handler_run_parity.py` nor `test_dispatch.py`; suite green.
- [x] Add `hooks/tests/test_echo_layout.py` (depends on: Phase 0): for every
  file matching the family globs, assert at most 800 lines and, via `ast`, no
  `FunctionDef`/`AsyncFunctionDef` spanning more than 50 lines; assert the glob
  found at least five product files and five test files so an empty match
  cannot pass. Acceptance: `uv run --with pytest pytest /Users/bob/.claude/hooks/tests/test_echo_layout.py -q`
  passes; lowering the function limit to 10 in a scratch copy makes it fail.

Exit criteria: suite green; `test_echo_layout.py` passes.

## Success Criteria

- Every echo-family file at most 800 lines and every function at most 50
  lines, pinned by `hooks/tests/test_echo_layout.py` (zero waivers).
- Full hooks suite green after every task; `hooks/dispatch.py` ROUTES
  unchanged; `test_handler_run_parity.py` and `test_dispatch.py` untouched
  and green, proving the handler contract survived.
- The existing echo tests pass with only import paths and patch targets
  changed: deny envelope, audit event shapes and the two-attempt gate are
  byte-identical in behavior.
