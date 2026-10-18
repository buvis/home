---
design: skip
---

# Prevent Reference Rot in Working Documents

## Overview

### Problem Statement

2026-07-14 fixed seven dangling references by hand: six PRDs cited a discovery
doc renumbered the day before, and PRD 00063 plus a memory cited a spike dir
that dev/local GC had removed. Nothing checks references when documents are
renumbered, moved, or trashed: purge-devlocal trashes paths without asking who
still points at them, and review-prd-backlog does not verify that PRD source
citations resolve. Maintenance audits run only when someone remembers (46MB of
stale plugin caches sat until today's ad-hoc audit).

### Target Users

The operator and the autopilot loop: implementor premise checks stop tripping
on dangling pointers, and maintenance findings arrive on a schedule.

### Success Metrics

- A dangling path/PRD/memory reference inside dev/local or project memory is
  reported with file:line by one command.
- review-prd-backlog fails a backlog PRD whose citations do not resolve.
- purge-devlocal never trashes a path that is still referenced without
  flagging it first.
- A maintenance nag appears in brief-portfolio when the last filesystem audit
  is older than 30 days.

## Functional Decomposition

### Capability: Link checking

#### Feature: check_links.py
- **Description**: scan markdown for references and verify each resolves.
- **Inputs**: a repo root (default cwd); scans `dev/local/**/*.md` and, when run in ~/.claude, the project memory dir. Reference kinds: explicit paths (`dev/local/...`, `~/.claude/...`, absolute `/Users/...`), five-digit PRD/discovery citations (`NNNNN-` resolved against `dev/local/prds/**` and `dev/local/discovery/`), and `[[memory-name]]` links resolved against the memory dir.
- **Outputs**: findings as `file:line -> missing target`; `--json` for machine use; exit 0 clean, 1 dangling found.
- **Behavior**: stdlib-only python3 with pytest fixtures. A line containing the literal token `link-ok:` is exempt (for prose that names intentionally-removed paths, e.g. "since removed"). Findings quote the citing line so self-documenting removals are recognizable at a glance.

### Capability: Wiring into the two rot sources

#### Feature: review-prd-backlog gate
- **Description**: backlog review runs check_links.py over backlog/ and wip/ PRDs; dangling citations become Blocking findings.
- **Inputs**: the script; the skill's existing findings format.
- **Outputs**: a new numbered check in the skill's checklist with its own findings section.
- **Behavior**: Premise, re-checked at execution: read the skill's current check structure first and match its conventions; the check runs the script, it does not restate the logic.

#### Feature: purge-devlocal pre-trash check
- **Description**: before trashing any path, search dev/local and project memory for references to it; referenced paths are skipped and reported instead of trashed.
- **Inputs**: the GC candidate list; `rg` over the scanned scopes.
- **Outputs**: per-candidate verdict in the GC manifest: trashed, or kept ("still referenced by <file:line>").
- **Behavior**: Premise, re-checked at execution: read purge-devlocal SKILL.md's GC flow and manifest format first; the check slots in before the mv-to-trash step; no `--force` override is added (a referenced path stays until the reference is fixed).

### Capability: Maintenance cadence

#### Feature: brief-portfolio maintenance nag
- **Description**: the portfolio dashboard nags when the last filesystem audit is stale, mirroring the existing brush nag.
- **Inputs**: newest file matching `~/.claude/dev/local/audit-results/*filesystem*` (or the triage naming in use) by mtime.
- **Outputs**: a dashboard row: green when < 30d, nag row "run /claude-checkup:audit-filesystem + check-links" when older or absent.
- **Behavior**: Premise, re-checked at execution: the brush nag mechanism exists in brief-portfolio (memory `project_brush_skill_status`); reuse its pattern and thresholds verbatim. If the audit skill's reports carry no stable naming, key on the audit-results dir's newest mtime and note the imprecision in the row tooltip.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/review-prd-backlog/
├── SKILL.md                        # Maps to: review-prd-backlog gate
└── scripts/
    ├── check_links.py              # Maps to: Link checking (new)
    └── test_check_links.py         # Maps to: Link checking tests (new)
~/.claude/skills/purge-devlocal/
└── SKILL.md                        # Maps to: pre-trash check (cites the script)
~/.claude/skills/brief-portfolio/
└── SKILL.md                        # Maps to: maintenance nag
```

### Module: check-links
- **Maps to capability**: Link checking
- **Responsibility**: one command that says which references are dangling.
- **Exports**: `check_links.py` CLI (`--json`, exit codes 0/1).

### Module: skill wiring
- **Maps to capability**: Wiring into the two rot sources, Maintenance cadence
- **Responsibility**: the three skill-prose integrations; each skill's `## Dependencies` section names the script (cross-skill dependency convention).
- **Exports**: backlog-review check, pre-trash verdicts, dashboard nag row.

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **check-links**: the script both wirings call.

### Core Layer (Phase 1)
- **skill wiring (review-prd-backlog, purge-devlocal)**: Depends on [check-links].

### Integration Layer (Phase 2)
- **skill wiring (brief-portfolio nag) + commit**: Depends on [check-links]; last for single-commit ordering.

## Implementation Phases

### Phase 0: Foundation
**Goal**: The scanner exists and is trustworthy.

**Tasks**:
- [ ] Implement check_links.py + tests (no deps) - Acceptance: fixture tree covers each reference kind resolving and dangling, the `link-ok:` waiver, exit codes, and `--json`; run against the live ~/.claude dev/local and report (not fix) whatever it finds.

**Exit Criteria**: tests green; live run output attached to the task report.

### Phase 1: Core
**Goal**: The two rot sources are gated.

**Tasks**:
- [ ] Add the backlog-review check per its conventions (depends on: Phase 0) - Acceptance: skill text names the script and Blocking semantics; `## Dependencies` updated; a dry run over the current backlog reports clean (references were fixed 2026-07-14).
- [ ] Add the purge-devlocal pre-trash check (depends on: Phase 0) - Acceptance: skill text inserts the check before mv-to-trash with the kept-because-referenced manifest verdict; `## Dependencies` updated.

**Exit Criteria**: both skills cite one script; no logic duplicated.

### Phase 2: Integration
**Goal**: Cadence lands and everything is committed.

**Tasks**:
- [ ] Add the brief-portfolio maintenance nag row mirroring the brush nag (depends on: Phase 0) - Acceptance: with the fixture mtime aged >30d the row nags; fresh, it is green.
- [ ] Commit all touched skills + script to the buvis bare repo by absolute pathspec, never `-a` (no CHANGELOG; dotfiles exemption) (depends on: all) - Acceptance: `git --git-dir=$HOME/.buvis --work-tree=$HOME log -1 --stat` lists them.

**Exit Criteria**: nag verified both ways; commit landed.

## Test Strategy

### Critical Scenarios
- **Happy path**: PRD citing an existing discovery doc → no finding; after renaming the doc in the fixture → file:line finding, exit 1.
- **Edge case**: memory line saying a path was "since removed" with `link-ok:` → no finding; without the waiver → finding that quotes the line.
- **Error case**: unreadable file in the scan tree → reported as a scan error, exit still meaningful (fail loud, no silent skip).

## Risks

- **False positives on prose that mentions paths illustratively**: the waiver token plus quoted citing lines keep triage cheap; gate severity lives in the backlog-review skill, not the script.
- **purge-devlocal slows down**: one rg per candidate is milliseconds; the GC is already batch-oriented.
- **Nag fatigue**: single row, 30d threshold, mirrors an accepted pattern (brush).
