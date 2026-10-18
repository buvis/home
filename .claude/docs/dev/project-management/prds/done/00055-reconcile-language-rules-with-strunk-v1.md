# Reconcile Language Rules With Strunk

> ## OUTCOME (2026-07-13): PREMISE FALSIFIED BY MEASUREMENT. THE DELETION LANDED ANYWAY, AND WAS REVERTED BY HAND 93 MINUTES LATER.
>
> **What actually happened, in order (from git, not from the narrative):**
>
> 1. The live probe (Test Strategy 4) ran and **failed for all 10 destination skills**.
> 2. The deletion commit `641045f20` landed at **14:02 anyway**, removing all 15 files, and was **pushed to `origin/master`**. The gate blocked nothing: "delete only after the probe passes" was prose, not a mechanism, and no tooling enforced it.
> 3. The files survived on disk only as **untracked restores sitting over a HEAD that had deleted them** — invisible in `git status` because the buvis repo sets `status.showUntrackedFiles=no`.
> 4. A human noticed and reverted with `e2952e3d0` at **15:35**. The tracked deletion had stood for ~93 minutes.
>
> **Process gap to fix (the real lesson):** the PRD's hard ordering constraint existed only as prose in this document. An irreversible delete gated on a probe needs a mechanical gate — a hook or a script that refuses the commit — or it will simply be executed by a confident implementor who believes the gate already passed.
>
> What the probe measured, each with a control:
>
> 1. **`paths:`-scoped rules ARE pushed and obeyed.** Canary test: a ruling planted in `rules/python/coding-style.md` ("every docstring must begin with ZEBRAFISH") was attached and obeyed by a fresh session writing Python. The rules tree is live, not dead weight.
> 2. **strunk skills are pulled, and almost never self-fire: 1 invocation in 30 runs** (10 destinations × 3 fresh headless sessions, realistic work prompts). Control: `check-python-compat` fired instantly on the explicit phrase "check python compat" — the mechanism works, but on **keywords**, not on **work**.
> 3. **Router files do not rescue it: 0/3.** A pointer file attaches and the model ignores it. Attachment is not invocation.
>
> **Rules are PUSHED (guaranteed); skills are PULLED (rarely). They are not interchangeable delivery mechanisms** — which is precisely what this PRD assumed. Deleting the 15 files would have silently stopped ~1026 lines of guidance from reaching the model during ordinary work.
>
> **What shipped anyway (and is kept):** **strunk v0.2.0** — released, tagged, pushed, marketplace-bumped, cache-installed, carrying all 70 migrated rulings (verified per-ruling against the released cache with fixed-string matching: 70/70 pins hit). Three genuinely new skills (`web-patterns`, `web-security`, `web-performance`) fill a framework-agnostic web lane strunk never had. Corrections to v0.2.0's docs and triggers landed on `master` afterwards and await a `v0.2.1` release (see Outstanding).
>
> **Net state of the rules tree:** `rules/{python,rust,web}/` (15 files) is **back on disk and pushed** (deleted by `641045f20`, restored by `e2952e3d0`, both now on `origin/master`). It was NOT "never touched". The restore was byte-identical; one later commit (`1a5cdbfec`) then deliberately dropped the Rust immutability bullet that contradicted the always-loaded global rule, so the tree is no longer byte-identical to its pre-deletion state — by intent. `sort-agent-setup` is untouched (correctly: the rules tree it cites still exists). Success metrics 1, 2 (as a *consolidation*), and 5 are NOT met, by decision.
>
> **The no-loss gate was weaker than it looked (found by the blind lens, cycle 3).** The 70/70 pin check passed — but the review then found rulings that had in fact been thinned in migration and were NOT covered by any pin: "never clone to satisfy the borrow checker *without understanding the root cause*", "reserve `unwrap()`/`expect()` for tests and truly unreachable states", and "iterator chains for transformations; *use loops for complex control flow*". All three are now restored (`1837514`, `380f14c`). **A pin list only proves the terms you thought to pin.** A future no-loss gate should pin qualifier clauses, not just headline terms.
>
> **One ruling was deliberately deleted from the rules tree** (`1a5cdbfec`): "Prefer returning new values over mutating in place" in `rules/rust/coding-style.md`. This looks like a violation of the "no ruling dropped as obsolete" non-goal, and it is a conscious exception: the migration had already ruled it superseded by the always-loaded `rules/coding-style.md` Rust clause ("trust the borrow checker … don't clone or rebuild data structures just to avoid `mut`"), and two reviewers independently flagged that the surviving rules tree was still *pushing* the contradicted ruling on every `.rs` Read.
>
> **Outstanding after the review (3 cycles, converged):**
>
> - **strunk v0.2.1 is not released.** The doc/trigger corrections are on `master` (`d413dd3`, `f4f2ec3`, `1837514`, `380f14c`) but unreleased: no `v0.2.1` tag, `plugin.json` still says `0.2.0`, and the installed plugin cache + the central `buvis/claude-plugins` marketplace still serve **v0.2.0, which carries the false "exactly one home" CHANGELOG claim, the false auto-trigger README promise, the missing web-lane file-edit triggers, and the thinned Rust rulings**. Run `dev/bin/release patch` in `claude-strunk` to publish the fixes. (The release is blocked in unattended sessions: it pushes over SSH and the 1Password signing agent is locked there.)
> - **`settings.json` default-model bump to `opus[1m]`** rode in on the reverted deletion commit and is on `origin/master`; the working tree has an uncommitted local change to that file. Owner's call — autopilot did not touch it.
> - **Nothing mechanizes the rules ↔ strunk parity** now that the content is deliberately duplicated. Drift has already started (each surface has had a fix the other did not). PRD 00064 is the structural answer.
>
> **Accepted consequence:** the content is now duplicated — rules tree (delivers) + strunk (portable, versioned). Drift risk is accepted until the follow-up lands.
>
> **Follow-up:** `00064-deliver-strunk-rulings-via-hook-v1.md` — a hook that injects the strunk skill content on matching file work, giving guaranteed delivery from a single source. That is the only way to consolidate without losing delivery.
>
> Full evidence: memory `project_rules_attach_skills_dont_fire`. Design doc: `dev/local/designs/00055-reconcile-language-rules-with-strunk-v1-design.md` (3 reviewer dispatches, 14 blockers fixed — the design was sound; the PRD's premise was not).

> Source: full-config audit 2026-07-10 (audit-authoring redundancy finding, corrected live: the harness attaches `rules/{python,rust,web}/*.md` on **Read** of a matching file — probed 2026-07-13 — so BOTH this tree and the strunk plugin skills fire on the same work).
> Target: `~/.claude/rules/{python,rust,web}/` (15 files, buvis-tracked), the **`claude-strunk` plugin source repo** (`~/git/src/github.com/buvis/claude-strunk`) + a marketplace release, and the `sort-agent-setup` skill.
> **Amended 2026-07-13** after the design phase escalated. The original "pick a winner per file, pointer-ize the loser" model was disproved by a per-file coverage audit: the overlap is **bullet-level, not file-level** (strunk `rust-patterns` rules borrow-don't-clone and `?`-over-`unwrap` but not the naming table, module layout, or `impl Into<String>`). Executing it would either destroy ~180 lines of guidance with no successor or require fragile bullet surgery across six files. User decision: **migrate rules-only content INTO strunk and delete the rules tree** — total consolidation, one home, nothing left to drift. The superseded design doc is archived at `dev/local/designs/00055-reconcile-language-rules-with-strunk-v0-superseded-design.md`; its **Coverage audit** table (which strunk section already carries which rules bullet, verified against strunk's real text) and its **Attachment probe** (rules attach on Read, not Write/create) are direct inputs to this amendment's migration map — read it, do not re-derive them.

## Overview

### Problem Statement

Language guidance exists twice with independent evolution:

- `~/.claude/rules/python/*` (4 files), `rules/rust/*` (5), `rules/web/*` (6) — 15 files, ~1026 lines, auto-attached by the harness on Read of a matching file, and cited as LIBRARY content by `sort-agent-setup` (SKILL.md:113-114).
- strunk plugin skills — `python-patterns`, `python-testing`, `rust-patterns`, `rust-testing`, `frontend-patterns`, `e2e-testing`, `apply-design-system` (283 lines) — invoked by the model on the same file-type work.

Both fire on a Python edit: the rules files inject AND the strunk skill triggers. They already disagree in depth and coverage (rules carry the Rust naming table and cargo command reference strunk lacks; strunk carries pinned rulings like `autospec=True` and `std::hint::black_box` rules lacks), and the overlap is per-bullet, so neither side can be dropped wholesale without loss. Double injection also spends context on redundant prose.

### Target Users

The solo operator who wants one authoritative answer per language topic and no silent divergence.

### Success Metrics

- `~/.claude/rules/{python,rust,web}/` no longer exists (or retains only path-scoped router files of ≤3 body lines — see Risks/attachment).
- **Zero content loss**: every non-duplicate ruling from the 15 deleted files is present in a released strunk skill. Verified per-ruling, not per-file (Test Strategy check 2).
- strunk is released to the marketplace and the local plugin cache carries the migrated content before any rules file is deleted.
- `sort-agent-setup`'s DAILY/LIBRARY table cites only paths that exist on disk.
- A matching-file edit surfaces exactly one source per (language × topic).

### Non-Goals

- Touching top-level `~/.claude/rules/*.md` (global, language-agnostic rules — the base layer all language guidance extends).
- Improving or expanding the guidance. Migration is **verbatim transfer**; text may be reordered or de-duplicated to fit skill format, but no new rulings are authored and no existing ruling is dropped as "obsolete".

(The original non-goals "no rewriting the guidance content" and "no changing strunk's trigger phrases" are **retired by this amendment** — migration necessarily moves content, and skills that absorb a new topic need triggers that fire on it.)

## Functional Decomposition

### Capability: Single-source language guidance in strunk

#### Feature: Migration map
- **Description**: for each of the 15 rules files, decide which strunk skill absorbs its content — an existing skill (as a new section) or a new skill — and pin the trigger that must fire on that content's work.
- **Inputs**: the 15 rules files; the 8 strunk skills' real text; the superseded design doc's Coverage audit (which strunk sections already carry which rules bullets).
- **Outputs**: a table in the design doc — every rules file appears exactly once, with a destination skill, a duplicate-bullet list (dropped, already ruled by the destination), a unique-bullet list (must survive), and the trigger phrase covering it.
- **Behavior**: topics with no strunk counterpart today (`python/security`, `rust/security`, `rust/platform`, `web/security`, `web/performance`, `web/coding-style`, `web/design`'s quality gate) need a home: prefer folding into an existing skill whose trigger already fires on that work over minting a new skill.

#### Feature: Strunk absorption + release
- **Description**: apply the map in the `claude-strunk` source repo, then release.
- **Inputs**: the migration map.
- **Outputs**: updated/new skills in `~/git/src/github.com/buvis/claude-strunk`; `create-skill` validator green on every touched skill; a marketplace release via `dev/bin/release minor` (memory `project_plugin_release_flow.md`); the local plugin cache carrying the new version.
- **Behavior**: never edit `~/.claude/plugins/cache/` directly — it is read-only and overwritten on update.

#### Feature: Rules-tree removal
- **Description**: delete `rules/{python,rust,web}/` and fix the one referrer.
- **Inputs**: a released strunk carrying the content (hard precondition).
- **Outputs**: the 15 files deleted in one buvis commit (absolute pathspecs; history preserves the bodies); `sort-agent-setup` SKILL.md rows updated.
- **Behavior**: deletion happens **only after** the release lands and the no-loss check passes. If the attachment probe (Test Strategy check 4) shows the model does not reliably invoke the destination skill on a matching edit, the affected language keeps ONE path-scoped router file of ≤3 body lines pointing at the strunk skills — content still lives only in strunk.

## Implementation Phases

### Phase 0: Build the migration map
**Tasks**:
- [ ] Produce the (rules file → destination skill) map with duplicate/unique bullet lists and trigger coverage (no deps). Acceptance: all 15 rules files appear exactly once; every unique bullet names its destination skill and section; every destination names the trigger that fires on that content's work.

### Phase 1: Absorb into strunk and release
**Tasks**:
- [ ] Apply the map in the `claude-strunk` source repo (depends on: Phase 0). Acceptance: `create-skill` validator green on every touched/new skill; for each unique bullet in the map, a grep for its pinned term hits the destination skill.
- [ ] Release strunk to the marketplace and update the local plugin cache (depends on: previous). Acceptance: the installed cache version matches the released version and contains the migrated content.

### Phase 2: Delete the rules tree
**Tasks**:
- [ ] Delete `rules/{python,rust,web}/` (or reduce to router files per the probe) and commit to buvis with absolute pathspecs (depends on: Phase 1). Acceptance: the no-loss check (Test Strategy 2) passes against the **released cache**, not the source repo, before the deletion commit.
- [ ] Update `sort-agent-setup` SKILL.md LIBRARY/DAILY rows and its ownership prose (depends on: Phase 1). Acceptance: `rg "rules/(python|rust|web)/" ~/.claude/skills/sort-agent-setup/SKILL.md` matches only paths that still exist on disk.

**Exit Criteria**: one home per topic (strunk); zero rulings lost; sort-agent-setup consistent; create-skill validator green.

## Test Strategy

No pytest surface (markdown + skill frontmatter). Verification is four deterministic checks:

1. **Validator**: `create-skill` validator green on every touched/new strunk skill and on `sort-agent-setup` (memory `feedback_skill_validation.md`).
2. **No-loss check (the gate)**: for every unique bullet in the migration map, grep its pinned term in the **released plugin cache** (not the source repo) and require a hit. Run before the deletion commit; a miss blocks the deletion. Pinned terms are named in the map, so the check is re-runnable after any future strunk release.
3. **Dangling-reference check**: `rg -n "rules/(python|rust|web)/" ~/.claude` returns only paths that exist on disk.
4. **Live probe (gate)**: edit a scratch `.py`, `.rs`, and `.svelte` file; confirm the destination strunk skill is offered/invoked and no deleted rules file's prose appears. A language that fails keeps a ≤3-line router file (see Risks).

Review-gate convention for the docs-only diff: `files: n/a:docs only` + `tests: none: diff touches no code` (memory `feedback_review_gate_docs_only_convention.md`).

## Risks

- **Delivery downgrade (accepted, mitigated).** A `paths:`-scoped rules file is **attached by the harness** on Read — deterministic, no model choice. A strunk skill is **invoked by the model** off its description triggers. Migration trades a guarantee for a heuristic. Mitigation: the map pins a trigger for every migrated topic, and the live probe (check 4) is a gate — a language whose skill does not reliably fire keeps one ≤3-line path-scoped router file, so the guarantee survives while the content still lives only in strunk.
- **Content loss during transfer.** 1026 lines moving across repos is where rulings quietly vanish. Mitigation: the map's per-bullet unique list plus the no-loss grep gate (check 2), run against the released cache before anything is deleted.
- **Ordering hazard.** Deleting rules before the release lands leaves a window with no guidance on either surface. Mitigation: Phase 2 hard-depends on Phase 1; the no-loss check runs against the released cache.
- **Two repos, one logical change.** strunk (normal repo, CHANGELOG required, release flow) and buvis (bare repo, CHANGELOG-exempt, absolute pathspecs — memories `feedback_buvis_pathspec_absolute.md`, `feedback_buvis_home_repo.md`). Neither commit is atomic with the other; the release is the commit point that matters.
- **Concurrent-commit hazard.** `~/.buvis` is a live shared work-tree and a user commit has landed mid-run before (memory `project_autopilot_head_moves_midreview.md`). Stage only named paths by absolute path, never `git add -A`.
- **Skill bloat.** Folding security/platform/performance into existing skills grows them; a skill that tries to rule everything gets invoked for nothing. The map must justify each fold against minting a new skill, on trigger fit, not on file count.
