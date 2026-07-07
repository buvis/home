---
name: design-solution
description: Use when turning a PRD into a reviewed design doc (the HOW) before planning tasks - architecture fit, exact interfaces, reuse, alternatives, then an autonomous adversarial review. Triggers on "design solution", "design this PRD".
argument-hint: "<prd-path>"
---

# Design Solution

Turn a PRD (the WHAT) into a reviewed implementation design doc (the HOW): module
placement, exact interfaces, data flow, reuse of existing code, and alternatives
weighed - then critique the draft with an autonomous adversarial reviewer before
handing it to `/plan-tasks`.

This skill runs **unattended** inside the autopilot build gate. It never asks the
user anything. It is **state-agnostic**: it prints the design doc path on success
and exits non-zero when unresolved cardinal sins or blockers remain; the caller
records the path.

It **never edits the PRD**. The design refines the PRD; acceptance criteria stay
PRD-owned.

## Inputs

- **PRD path** (argument). If omitted, auto-select the single PRD in
  `dev/local/prds/wip/`. Error and stop if `wip/` holds zero or 2+ PRDs
  ("ambiguous - pass the PRD path explicitly").
- **Architecture context**, loaded when present (skip silently if absent):
  - the cartographer atlas for this repo
    (`~/.claude/cartographer/projects/<hash>/atlas.md`)
  - `dev/local/project-capsule.md`
  - `AGENTS.md` / `agent_docs/`

## Output

`dev/local/designs/<prd-stem>-design.md`, where `<prd-stem>` is the PRD filename
minus its `.md` extension. Create `dev/local/designs/` if missing - it is a
durable artifact dir, like `dev/local/reviews/`.

## Workflow

### 1. Resolve the PRD and load context

Resolve the PRD path per Inputs. Read the PRD in full. Load the architecture
context files that exist. Identify the capabilities and features the PRD asks for
- these drive the reuse sweep and the interface design.

### 2. Reuse sweep (before designing any new code)

Grep the codebase for existing helpers and patterns that already do what the PRD
needs, per the synonym sets in `~/.claude/rules/rationalizations.md`
("Synonyms-to-grep"). For each capability:

- Search **both** the verb and the noun synonyms (e.g. `format` / `render` /
  `serialize` AND `date` / `timestamp`).
- If a search returns nothing, re-run it with a term you know is present to prove
  the pattern works before concluding the helper is absent.

Record findings in `## Reuse inventory`: one entry per existing helper as
**(path + how to use it)**, or, when nothing exists, an explicit
`nothing found, greps tried: ...` line naming the searches you ran.

### 3. Write the design doc

Write `dev/local/designs/<prd-stem>-design.md` with **exactly these nine
sections, these headings, in this order**:

1. `## Architecture fit` - the target layers/modules this work lands in, drawn
   from the atlas / capsule.
2. `## Module placement` - which changes are new files vs edits to existing
   files, with paths.
3. `## Interfaces & contracts` - the exact signatures, types, enum values, field
   names, file/hook kinds, and thresholds. Write these **verbatim-ready**:
   `/plan-tasks` copies them byte-for-byte into task `Contract` sections, so name
   every symbol exactly.
4. `## Data flow` - how data moves through the changed components.
5. `## Reuse inventory` - from step 2.
6. `## Alternatives considered` - 2-3 design options, the chosen one, and why.
7. `## Risks & edge cases`.
8. `## Test strategy outline`.
9. `## Review log` - start empty; the review loop (step 4) fills it.

Keep `## Interfaces & contracts` precise enough that a planner who never reads the
PRD could copy a contract verbatim and be correct.

### 4. Autonomous adversarial review (up to 3 dispatches)

Critique the draft with reviewers, then fix what they find. The review runs a
**cross-model** loop: dispatch 1 is a fresh Claude subagent, dispatch 2 is a
**mandatory codex** reviewer (a rival model catches the echo-chamber defects the
authoring model cannot see in itself), and dispatch 3 is a conditional codex
verification pass. Ceiling: **3 dispatches**.

**Each dispatch** sends the reviewer ONE self-contained prompt containing:

- the current draft design doc, and
- a short summary of the PRD (the problem + the capabilities), and
- the **severity taxonomy**:
  - the cardinal-sins list, inlined by reading
    `~/.claude/skills/review-design-doc/references/cardinal-sins.md` at dispatch
    time (read it and paste its content into the prompt - do **not** copy the
    list into this skill file; that file is the single source of truth), plus
  - three-line definitions of the other severities:
    - **Blocking** - a defect that makes the design wrong or unbuildable as
      written; must be fixed before planning.
    - **Non-blocking** - a real concern that does not block planning; record it,
      do not fix it now.
    - **Question** - an ambiguity a competent reader could misread; record it, do
      not fix it now.
  - the calibration rule: **not everything is a blocker** - overflagging dilutes
    signal.

The reviewer returns findings only; it **never edits files**. Each finding has
the shape:

```
{severity: cardinal-sin|blocker|non-blocker|question, title, evidence, suggested_fix}
```

**Dispatch sequence:**

1. **Dispatch 1 - Claude** (fresh subagent). Fix every cardinal sin and blocker
   in the doc.
2. **Dispatch 2 - codex** (mandatory, cross-model). It **always runs,
   even when dispatch 1 found zero blockers** - that clean-dispatch-1 case is
   exactly where a second, rival-model opinion matters most. Fix every cardinal
   sin and blocker.
   Run codex as a **direct background Bash command** (never a Task subagent - a
   subagent that shells out to a CLI hangs), absolute paths:
   ```
   Bash tool (run_in_background: true):
     ~/.claude/skills/use-codex/scripts/codex-run.sh -f "{codex_prompt_file_abs}" -o "{abs_repo_path}/dev/local/tmp/design-codex-output-{id}.txt"
   ```
   codex is **read-only** by default (no `-a`/`-y` -> `--sandbox read-only`) and
   never edits files; the prompt is self-contained (the same package the Claude
   reviewer gets), so no `-d`. When the background command completes, read the
   `-o` output file for codex's findings.
3. **Dispatch 3 - codex verification** (conditional). Runs **only if dispatch 2
   found cardinal sins or blockers**; a fresh codex call is acceptable. Open
   cardinal sins/blockers remaining after it terminate the review non-zero (step 5).

**Claude fallback on codex outage.** If codex is unavailable - `codex-run.sh`
missing/non-executable, it exits non-zero, the timed wait ceiling trips, or its
output is unparseable as findings - degrade that dispatch to a fresh Claude
reviewer subagent (identical prompt). Append, loudly, `dispatch <n>: codex
unavailable, Claude fallback` before its summary line, and use the reviewer token
`claude-fallback` in that line. **Never PAUSE on a codex outage** - the review
completes unattended either way (mirrors Phase 8's codex-with-Claude fallback).
The fallback rule applies to every codex dispatch (2 and 3).

**After each dispatch:**

- Fix **every** cardinal sin and blocker by editing the design doc, then proceed
  to the next dispatch (up to the 3-dispatch ceiling).
- Append every non-blocker and question to `## Review log` (do **not** fix them).
- Append a one-line summary of the dispatch to `## Review log`, in this **exact
  pinned format** (one line per dispatch, so the run-autopilot Phase 1.5 execution
  gate can match it with a single fixed pattern):
  ```
  dispatch <n> (<claude|codex|claude-fallback>): cardinal-sin <c>, blocker <b>, non-blocker <nb>, question <q>
  ```
  `<n>` is the dispatch number; `<c>/<b>/<nb>/<q>` are per-severity integer
  counts; the reviewer identity token is exactly one of `claude`, `codex`,
  `claude-fallback` (dispatch 1 -> `claude`; dispatch 2 -> `codex` or
  `claude-fallback`; dispatch 3 -> `codex` or `claude-fallback`).

Dispatch each reviewer with the **Subagent Watchdog** discipline if you have it
(background dispatch + timed wait); a hung reviewer must not block an unattended
run.

### 5. Terminate

- **All cardinal sins and blockers resolved** (or none found): print the design
  doc path and the exit report, exit 0.
- **A cardinal sin or blocker is still open after dispatch 3**: print the design
  doc path, list every open cardinal-sin / blocker finding, print the exit
  report, and **exit non-zero**. The caller (autopilot) treats this as a
  sub-skill failure and PAUSEs; a manual run surfaces the open findings to the
  user.

## Exit report (always printed)

```
design-solution: <prd-stem>
  doc: dev/local/designs/<prd-stem>-design.md
  reviewer dispatches: <n>/3
  findings: cardinal-sin <c>, blocker <b>, non-blocker <nb>, question <q>
  open cardinal sins/blockers: <none, or a list>
  result: ok | failed (open cardinal sins/blockers)
```

The exit report always lists the iteration count (reviewer dispatches) and the
per-severity finding counts.

## Notes

- One reviewer dispatch per loop iteration; never two in flight at once.
- The skill writes only the design doc (and creates `dev/local/designs/`). It
  never edits the PRD, the task list, or autopilot state.
- Downstream blind review and doubt review stay PRD-only by design; this design
  doc feeds `/plan-tasks` and the work-completion review, not the spec-only
  surfaces.
