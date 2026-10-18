---
consensus_engine: shadow
---

# Autopilot sessions have no write fence: any subagent can Edit any path on disk

Source: autopilot batch 202608180438 incident, 2026-08-18 (PRD `00124-key-svelte-each-blocks-by-index-v1.md`, pause_reason `sub_skill_fail` in `dev/local/autopilot/state.json`). Tess (task 1 test-author) was handed the unanchored path `debrief-meeting/app/smoke.test.js`, failed to resolve it, swept the filesystem (`rg --files` cannot see into dot-directories, so the real file under `~/.claude/` was invisible), and edited the only visible suffix-match: `/Users/bob/bim/inbox/dmz/debrief-meeting/debrief-meeting/app/smoke.test.js` — a copy inside the user's zettelkasten vault, which an external sync daemon auto-committed (d537954f2) and pushed to gitlab.com/buvis/zettelkasten.

## Overview

### Problem Statement

Warden filters Bash commands only. The Write, Edit, and NotebookEdit tools are auto-accepted in headless autopilot sessions and carry no path restriction, so any subagent that resolves a path creatively can modify any file the user can — including files in foreign repos that external daemons publish. Two prompt-level defenses existed at incident time and both failed: the Tess template's own instruction ("if a file you need is not listed, stop and report it as a blocker — do not run broad rg sweeps") was ignored under helpful pressure, and the dispatch carried a relative path in the first place.

The proximate cause is fixed (2026-08-18, same session as this PRD): `render_prompt.py --require-file/--require-parent` now blocks any dispatch whose target paths are relative or dangling (exit 7), and SKILL.md § Dispatch-target preflight mandates absolute paths in dispatch prose. That kills this bug, not the class: any future dispatch shape, retry prompt, or deslop/reviewer agent that touches files still has unrestricted Write/Edit.

### Target Users

The autopilot loop (`autoclaude` / `/run-autopilot`) and every Agent-tool subagent it dispatches (Tess, Ivan, Devon, deslop). Indirectly: every foreign repo on the machine that a sync daemon can publish from.

### Success Metrics

- In an autopilot session, a Write/Edit/NotebookEdit whose target lies outside the allowed write scope is denied before execution, with a message naming the path and the scope.
- Replaying the incident (an Edit targeting `/Users/bob/bim/...` from an autopilot session) is blocked; the same Edit targeting `~/.claude/skills/debrief-meeting/app/smoke.test.js` passes.
- Interactive (non-autopilot) sessions are untouched — the fence arms only when the autopilot marker is present.
- A regression test per rule: out-of-scope denied, in-scope allowed, marker-absent pass-through.

## Functional Decomposition

### Capability: write-scope fence (PreToolUse hook)

- **Description**: a PreToolUse hook on Write, Edit, and NotebookEdit that denies targets outside the allowed scope when the session is an autopilot session.
- **Inputs**: the tool input's `file_path` (resolved via `os.path.realpath` — symlinks must not pierce the fence); an autopilot marker; the allowed scope.
- **Outputs**: exit 2 with a one-line stderr reason on denial (memory `reference_hook_permission_decision`: exit-2 block, never `permissionDecision`); exit 0 otherwise.
- **Behavior — allowed scope**: the session's primary working directory (the repo the batch runs in, e.g. `~/.claude`), the session scratchpad, and `/tmp`/`$TMPDIR`. The git work-tree is deliberately NOT the scope: for the buvis home repo the work-tree is all of `$HOME`, which would make the fence vacuous — the incident path `~/bim/...` is inside that work-tree.
- **Behavior — arming**: keyed on an environment marker the autoclaude wrapper already exports to the headless session (e.g. `_AUTOPILOT_TRACON_CHILD=1`; confirm the exact variable in design — it must reach the hook's environment, and nested helper CLIs don't inherit hooks/env anyway, see Risks). No marker → exit 0 unconditionally.
- **Behavior — failure mode**: a hook crash must not fail open silently (backlog PRD `00130-hook-gates-fail-open-silently-v1.md` is the umbrella for that class; this hook ships with whatever convention 00130 lands, or a logged fail-open until then).

Accepted option: one small Python hook (per `rules/claude-tooling.md`: Python, never bash), armed by env marker, scoped as above.

Rejected alternative: extend warden. Rejected — warden's contract is Bash command filtering; Write/Edit gating is a different tool surface with different inputs, and warden's ask-mode deadlocks unattended sessions (memory `project_warden_unattended_deadlock_fix`) so its interaction model doesn't fit a headless fence.

Rejected alternative: per-task allowlist (deny anything not in the task's Contract `FILE_PATHS`). Rejected for v1 — it needs the hook to read live task state from `state.json` mid-dispatch, couples the fence to the work skill's state schema, and breaks legitimate incidental writes (scratch files, `dev/local/tmp` dispatch files). The directory fence catches the incident class at a fraction of the coupling.

### Capability: home of the hook

- **Description**: decide where the hook lives and registers.
- **Behavior**: design-phase decision between the aegis plugin (already hosts tool-policy hooks; versioned; but a plugin PRD is inert until released AND installed — memory `feedback_plugin_prd_not_done_until_released`) and `~/.claude/hooks/` + `settings.json` registration (live immediately, buvis-tracked). Lean local-first, promote to aegis later if it proves out.

## Structural Decomposition

- New hook script (location per design: `~/.claude/hooks/` or aegis `hooks/`) + its test file.
- `settings.json` (or aegis `hooks.json`) — PreToolUse registration for Write/Edit/NotebookEdit.
- `autoclaude` wrapper (`development.plugin.bash` / `cli/loop.py`) — only if no existing exported marker survives into the hook environment; otherwise untouched.

## Implementation Phases

### Phase 1: fence hook + registration + tests

1. Confirm which autopilot marker variable is visible to hook processes in a real headless session (probe, don't assume).
2. Implement the hook: realpath the target, test against scope, exit 2 + reason on breach, exit 0 otherwise; unconditional exit 0 without the marker.
3. Register for Write, Edit, NotebookEdit.
4. Tests, incident-shaped: fixture invocations of the hook with (a) `/Users/bob/bim/...` target + marker → denied, (b) in-repo target + marker → allowed, (c) any target, no marker → allowed, (d) a symlink from inside scope pointing outside → denied.

*Acceptance:* a live autopilot smoke session (or a faithful env-replica invocation) shows the denial fire on an out-of-scope Edit and normal task writes proceed.

## Test Strategy

Regression tests bind to the incident: the exact vault path from batch 202608180438 must be denied under the marker. The pass-through case binds to the real repo path Tess should have edited. Hook tests run standalone (the hook reads stdin JSON like every other PreToolUse hook; fixtures are JSON payloads, no live session needed) — plus the one live smoke check in Phase 1 acceptance.

## Risks

- **Helper-script implementors bypass Claude hooks entirely.** `use-codex`/`use-gemini`/`use-qwen` dispatch external CLIs; nested CLIs don't inherit hooks (memory `project_autopilot_era_lessons`). Codex runs `--sandbox workspace-write` (its own fence); gemini/qwen have none. This PRD fences Claude-side tools only and names that residual gap — closing it is separate work.
- **Scope too tight breaks legitimate writes.** Tasks writing to the scratchpad, `dev/local/tmp`, or `$TMPDIR` must stay allowed; the test suite must include every write location the work skill's own machinery uses (dispatch files, state probes, review scratch files).
- **Marker plumbing.** If no wrapper-exported variable reaches hook processes, the wrapper needs a one-line export, and settings-level env is session-only (memory `project_autopilot_network_death_fix`) — verify in the real launch path, not locally.
- **Fail-open silence.** Until 00130 lands its convention, a crashing fence hook silently allows everything; Phase 1 must at least log the crash.

## Decision Log

### 2026-08-24 — Phase 1 acceptance: live smoke through `cli.runner.spawn()` (task 3)

Spawn call: `runner.spawn("claude-sonnet-5[1m]", "low", 600, autopilot_dir=dev/local/tmp/00136-smoke-autopilot, env=<os.environ minus _AUTOPILOT_WRITE_SCOPE and _AUTOPILOT_WRITE_SCOPE_EXTRA>, prompt=<two-step file-tools-only smoke>)`, invoked from cwd `/Users/bob/.claude` via the throwaway driver `dev/local/tmp/00136-run-smoke.py` — so `LAUNCH_ENV` supplied `CLAUDE_UNATTENDED=1` itself and the whole runner → Popen → claude → hook-subprocess chain ran end to end (design § Test strategy, per review finding C2: a bare `claude -p` with the marker hand-exported proves nothing about LAUNCH_ENV).

All four assertions held:

1. `SpawnResult`: `returncode=0`, `cap_fired=False` (9s session, 4 turns, $0.21).
2. In-scope write proceeded: `dev/local/tmp/00136-smoke-inscope.txt` created with content `in-scope ok`.
3. Out-of-scope Edit denied BY THE FENCE (not a generic permission denial). Verbatim from `dev/local/tmp/00136-smoke-autopilot/last-session.log`:
   `BLOCKED: autopilot write-scope fence: '/Users/bob/00136-fence-probe.txt' is outside the allowed scope ('/Users/bob/.claude', '/Users/bob/.local/tmp/claude-dev', '/private/var/folders/m6/1mnc9pdn28d5vdxy4hxyr1m40000gn/T', '/private/tmp'). Write inside the session's repo, its dev/local, or a temp dir; add a root via _AUTOPILOT_WRITE_SCOPE_EXTRA, or set _AUTOPILOT_WRITE_SCOPE=off to disarm.`
   The listed roots are exactly the contract's roots 1-4 for a `~/.claude`-rooted session (repo, dev/local realpath, TMPDIR, /tmp realpath).
4. The probe file `/Users/bob/00136-fence-probe.txt` still contained `AAA` afterwards (Edit never executed).

Deliberate deviation, per the task plan: the live out-of-scope target was a fresh `$HOME`-root probe file, NOT the incident vault path `/Users/bob/bim/...` — a broken fence editing the live vault would recreate the incident (external sync daemon auto-commits and pushes), while the probe has zero blast radius. The exact vault path's denial is bound by the standalone regression test (`test_denies_incident_vault_path_under_marker`, byte-for-byte reason assertion) and its inherited-env subprocess twin; this smoke binds the deny/allow pair through the real launch chain. Success metric 2's two halves are therefore covered as: vault-path block → unit tests; real-launch-chain block + in-repo pass-through → this smoke.

Evidence artifacts kept for review: `dev/local/tmp/00136-run-smoke.py` (driver), `dev/local/tmp/00136-smoke-autopilot/last-session.log` (3 occurrences of the BLOCKED line: hook stderr + the model's verbatim echo), `dev/local/tmp/00136-smoke-inscope.txt`. The probe file was moved out of `$HOME` root to `dev/local/tmp/00136-fence-probe-removed.txt` after evidence capture.

### 2026-08-25 — Review cycle 1 decisions (review file `dev/local/reviews/00136-…-review-1.md`)

Four reviewers + a non-gating `review-fanout` shadow; 14 consolidated findings, none CRITICAL/HIGH. Rework queued as tasks 4 (rule-mandated: a 57-line test function and `test_handler_run_parity.py` crossing 800 lines) and 5 (design/docstring reword of the root-floor reachability claim; durable home for the `_AUTOPILOT_WRITE_SCOPE_EXTRA` export in AGENTS.md § Toolchain and run-autopilot § Entry Points; marker check before `read_input()`; `expanduser` on extra roots).

Accepted residuals (known limitations, not fixed):

- **Auto-memory writes are outside the scope.** `~/.claude/projects` is a symlink into the cellar repo, so a harness auto-memory Write/Edit from an armed batch is denied (loud, recoverable; the reason names the path). Workaround if a batch ever hits it: add the cellar path via `_AUTOPILOT_WRITE_SCOPE_EXTRA`. Deliberately not added as a default root: it would widen scope into a git-tracked transcript archive.
- **Check-then-act window.** The target is realpath'd at hook time, not re-verified at write time; a symlink swapped in between could escape. Same class as the design's hardlink note: the threat model is a confused agent, not an adversary.
- **Fail-closed text is reachable only via a `dev/local -> $HOME` symlink**, never from a plain `cwd=$HOME` (root 2 survives the floor as a descendant). The deny still holds via the ordinary breach reason; task 5 rewords the design to match.
- Refuted during review: Blake's claim that `last-session.log` was missing (file present, 31,400 bytes, 3 BLOCKED lines). Settled by the design review (B4, D1), surfaced for visibility: the kill switch `_AUTOPILOT_WRITE_SCOPE=off` and the widening knob `_AUTOPILOT_WRITE_SCOPE_EXTRA` are deliberate operator controls not named in this PRD's spec.

### 2026-08-25 — Tail sweep: MultiEdit matcher coverage is deliberate

The registered `dispatch.py` matcher (`Edit|Write|MultiEdit|NotebookEdit`) covers `MultiEdit`, a tool not named anywhere in this PRD's Overview, Behavior, or Phase 1 step 3 ("Register for Write, Edit, NotebookEdit"). This is beyond the PRD's literal enumeration but deliberate, not scope creep: a MultiEdit payload carries its write targets in `edits[].file_path` (which `_targets()` already reads), so leaving the tool unfenced would preserve an unguarded write path for the exact incident class this PRD targets. The matcher must not be narrowed. Binding test: `test_denies_out_of_scope_file_path_inside_multiedit_edits`.
