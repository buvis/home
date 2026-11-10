---
eligibility: test -f "$HOME/.config/buvis/buvis-braid.yaml" && ls "$HOME"/.local/share/mise/installs/pipx-buvis-gems/latest/lib/python*/site-packages/braid/domain/rules.py
design: skip
default_model: opus
model_tier_rationale: generative prose at volume (slimming 20 instruction files into RULE.md plus references) and destructive blast radius (replaces every host's instruction file)
---

# Migrate global instructions into buvis/agent-rules

Source: [Discovery 00182](../../discovery/00182-layer-agent-rules-across-hosts.md) (phase 3). Runs after buvis/gems PRD 00116 (rules kind) is released and installed, and after PRD 00183 moved the source list into `~/.config/buvis/buvis-braid.yaml`; the `eligibility` check holds it until both are true.

Before launching: `export _AUTOPILOT_WRITE_SCOPE_EXTRA="$HOME/.config/bash:$HOME/.codex:$HOME/.local/bin:$HOME/.config/buvis:$HOME/.agents:$HOME/.copilot:$HOME/.pi:$HOME/.kiro:$HOME/git/src/github.com/buvis/agent-rules"`.

## Overview

### Problem Statement

Global instructions live in two hand-kept places: `~/.claude/AGENTS.md`
(15159 bytes, read by Claude through the `@AGENTS.md` import in
`~/.claude/CLAUDE.md`, and by Codex, Copilot CLI, Pi and Kiro through
hand-made links) and twelve files in `~/.claude/rules/` (23987 bytes, read by
Claude only). The other hosts never see the rules. Discovery 00182 moves all of
it into a new public repo `buvis/agent-rules`, composed by braid into every
host. The always-on part must stay small: Codex reads at most 32768 bytes of
instruction files by default (`project_doc_max_bytes`), and the sources total
39146 bytes today.

### Target Users

Every agent session on every host on this machine; later, other machines and
colleagues who add `agent-rules` to their `sources.d`.

### Success Metrics

- `braid --check` exits 0.
- `wc -c < ~/.agents/hosts/codex/AGENTS.md` is at most 16384 (half the Codex default, leaving room for a project `AGENTS.md`; gems' own is 14106 bytes).
- `python3 docs/dev/tmp/00184/check_lossless.py` exits 0: no source line was lost.
- `~/.codex/AGENTS.md`, `~/.copilot/copilot-instructions.md`, `~/.pi/agent/AGENTS.md` resolve to `~/.agents/hosts/<host>/AGENTS.md`, and `~/.claude/rules/<name>.md` resolves into `~/.agents/rules/` or `~/.agents/hosts/claude/rules/` for every rule in the mapping.

## Functional Decomposition

### Capability: The agent-rules repository

#### Feature: Local repository
- **Description**: A new git repo at `~/git/src/github.com/buvis/agent-rules`, default branch `master`, no remote (the user creates `buvis/agent-rules` on GitHub and pushes).
- **Inputs**: none.
- **Outputs**: `README.md` (what the repo is, the layout `rules/<name>/RULE.md`, `rules/<name>/references/`, `hosts/<host>/rules/<name>/`, the 16384-byte budget, "edit here, then `braid` and `braid --check`"), `LICENSE` (copy `~/git/src/github.com/buvis/agent-skills/LICENSE` verbatim), `.gitignore` (`__pycache__/`, `.pytest_cache/`), `tests/test_budget.py`.
- **Behavior**: Premise: the directory does not exist. Re-check; if it exists, skip the PRD and report.

#### Feature: Budget test
- **Description**: `tests/test_budget.py` guards the always-on size and the shared-rule format.
- **Inputs**: `rules/*/RULE.md`, `hosts/codex/rules/*/RULE.md`.
- **Outputs**: pytest results via `uv run --with pytest pytest`.
- **Behavior**: `test_codex_always_on_fits_the_budget`: the header line plus every shared and codex `RULE.md` (trailing whitespace stripped, joined by one blank line, as braid renders them) is at most 16384 bytes. `test_shared_rules_carry_no_frontmatter`: no `rules/*/RULE.md` starts with `---`. `test_every_reference_pointer_resolves`: every `~/.agents/rules/<name>/references/<file>` or `~/.agents/hosts/<host>/rules/<name>/references/<file>` path named in any `RULE.md` exists in this repo at `rules/<name>/references/<file>` or `hosts/<host>/rules/<name>/references/<file>`.

### Capability: Content migration

#### Feature: Rule mapping
- **Description**: Each source becomes one rule. The mapping is fixed:

| Source | Rule path in agent-rules |
|---|---|
| `~/.claude/AGENTS.md` lines before `## Workflow` (title, three intro bullets, `## Autonomy`) | `rules/autonomy/` |
| `~/.claude/AGENTS.md` `## Workflow` | `rules/workflow/` |
| `~/.claude/AGENTS.md` `## Compaction` | `hosts/claude/rules/compaction/` |
| `~/.claude/AGENTS.md` `## Planning` | `rules/planning/` |
| `~/.claude/AGENTS.md` `## Handing work to the user` | `rules/user-handoffs/` |
| `~/.claude/AGENTS.md` `## Toolchain` | `rules/toolchain/` |
| `~/.claude/AGENTS.md` `## Conventions` | `rules/conventions/` |
| `~/.claude/AGENTS.md` `## Dotfiles repo` | `rules/dotfiles-repo/` |
| `~/.claude/rules/{ai-app-design,changelog,coding-style,communication,development-workflow,operating-principles,testing,working-documents,writing}.md` | `rules/<same name>/` |
| `~/.claude/rules/{claude-tooling,tools,memory}.md` | `hosts/claude/rules/<same name>/` |

- **Inputs**: The thirteen source files.
- **Outputs**: 20 rule directories.
- **Behavior**: `claude-tooling` keeps its `paths:` frontmatter in `RULE.md` (Claude host rule, passed through unchanged). Every other `RULE.md` starts with a `# ` title.

#### Feature: Slim always-on text
- **Description**: `RULE.md` keeps the rules; detail moves to `references/`.
- **Inputs**: Mapped source text.
- **Outputs**: `RULE.md` plus zero or more `references/<topic>.md` per rule.
- **Behavior**: Keep in `RULE.md` every imperative instruction line. Move verbatim to a reference: dated incident notes and rationale (`(2026-...: ...)` asides, `Rationale:` and `**Why:**` passages), worked examples, tables longer than five rows, and multi-step procedures. Replace each moved block with one pointer line `Read ~/.agents/rules/<name>/references/<topic>.md when <one-clause trigger>.` (host rules: `~/.agents/hosts/claude/rules/<name>/references/<topic>.md`). Moved text is not reworded. Stop slimming once `test_codex_always_on_fits_the_budget` passes; do not move more than needed.

#### Feature: Self-references rewritten
- **Description**: Text that names the old files is updated.
- **Inputs**: Lines matching `AGENTS\.md|CLAUDE\.md` in the sources.
- **Outputs**: Rewritten lines, the only lines allowed to change.
- **Behavior**: In `autonomy`, the intro bullet starting `This file (` becomes `Always-on agent instructions come from ~/git/src/github.com/buvis/agent-rules plus the sources listed in ~/.config/buvis/buvis-braid.yaml (shared) and ~/.local/.config/buvis/buvis-braid.yaml (company or machine-local), composed by braid. Edit the rule source, then run braid and braid --check. Never edit ~/.claude/rules/*.md, ~/.kiro/steering/*.md or the generated ~/.agents/hosts/<host>/AGENTS.md. Custom agent prompts must preserve this shared authority.` (paths in backticks). In `communication`, `` Apply `~/.claude/AGENTS.md`'s standing authorization `` becomes `` Apply the `autonomy` rule's standing authorization ``. In `memory`, the first bullet's `live under ~/.claude/ (rules/, AGENTS.md) and MUST be committed to the buvis dotfiles bare repo` becomes `live in ~/git/src/github.com/buvis/agent-rules; commit there, then run braid --check`, its three sub-bullets about `git --git-dir=~/.buvis` staging stay, scoped by a new lead-in `Other ~/.claude config (settings, hooks) still goes to buvis:`, and the sub-bullet starting `` `~/.claude/CLAUDE.md` is only an `@AGENTS.md` pointer `` is deleted. Any other line matching the pattern: replace the old path with the rule name that now holds the text, and list each such line in the report.

#### Feature: Lossless check
- **Description**: A scratch script proves nothing was dropped.
- **Inputs**: The thirteen live source files, the agent-rules tree.
- **Outputs**: `docs/dev/tmp/00184/check_lossless.py`, exit 0 or a list of missing lines.
- **Behavior**: Every non-blank source line, stripped, must appear stripped as a line in some `RULE.md` or `references/*.md`, except lines matching `AGENTS\.md|CLAUDE\.md` (rewritten above) and `## ` section headings of `~/.claude/AGENTS.md` (they become rule titles).

### Capability: Host cut-over

#### Feature: Retire the hand-kept files and links
- **Description**: Remove what braid now owns.
- **Inputs**: `~/.codex/AGENTS.md`, `~/.copilot/copilot-instructions.md`, `~/.pi/agent/AGENTS.md`, `~/.kiro/steering/AGENTS.md`, `~/.claude/AGENTS.md`, `~/.claude/CLAUDE.md`, the twelve `~/.claude/rules/*.md`.
- **Outputs**: Paths gone; buvis records the deletions of the tracked ones (`.codex/AGENTS.md`, `.claude/AGENTS.md`, `.claude/CLAUDE.md`, `.claude/rules/*.md`) by explicit `:(top)` pathspecs.
- **Behavior**: Premise: each of the four host paths is a symlink whose target resolves to `~/.claude/AGENTS.md`; `~/.claude/CLAUDE.md` holds only the `@AGENTS.md` import and the pointer comment; `~/.claude/rules/` holds exactly the twelve mapped files; `git --git-dir=$HOME/.buvis --work-tree=$HOME diff HEAD --quiet` holds for every tracked source (a live edit since migration would be lost; on failure re-run the migration task for the changed file first); and `check_lossless.py` and `uv run --with pytest pytest` in agent-rules both pass, re-run immediately before the deletion. Re-check every premise first; if any fails, change nothing on the host side and report. Claude Code loads `~/.claude/rules/*.md` natively, so no `CLAUDE.md` replaces the deleted one.

#### Feature: Compose and verify
- **Description**: braid takes over.
- **Inputs**: `~/.config/buvis/buvis-braid.yaml`.
- **Outputs**: Links and generated files from PRD 00116.
- **Behavior**: Add `~/git/src/github.com/buvis/agent-rules` as a new item of the `sources:` list in `~/.config/buvis/buvis-braid.yaml` (buvis-tracked), then run `braid`, then `braid --check`. Exit 0 is success. If `braid` fails or `--check` drifts, restore every deleted path from buvis `HEAD` (`git --git-dir=$HOME/.buvis --work-tree=$HOME checkout HEAD -- ':(top)<path>'`) and re-create the three untracked links to `~/.claude/AGENTS.md`, then report. Removing the hand-kept files and running braid happen in one task with no session boundary between them, so no host is left without instructions.

#### Feature: Repoint the remaining references
- **Description**: Code and tests that name the deleted files.
- **Inputs**: `hooks/tests/test_check_skill_triggers.py`.
- **Outputs**: `test_tracked_claude_file_resolves_from_an_unrelated_cwd` reads `Path.home() / ".claude" / "settings.json"` (buvis-tracked) instead of `AGENTS.md`, with the skip message updated to match.
- **Behavior**: After the edit, `rg -n "\.claude/AGENTS\.md|@AGENTS\.md" ~/.claude/hooks ~/.claude/skills ~/.agents ~/.config/bash` finds nothing outside `docs/dev/`. The installed autopilot plugin's `skills/run-autopilot/SKILL.md` still cites `~/.claude/AGENTS.md § Toolchain`; it belongs to `buvis/agent-plugins`, so record it in the report as a follow-up there and do not edit the plugin cache.

## Structural Decomposition

### Repository Structure

```text
~/git/src/github.com/buvis/agent-rules/         # new repo
├── README.md
├── LICENSE
├── .gitignore
├── rules/<name>/RULE.md                         # 16 shared rules (mapping table)
├── rules/<name>/references/<topic>.md           # moved detail
├── hosts/claude/rules/<name>/RULE.md            # compaction, claude-tooling, tools, memory
└── tests/test_budget.py
docs/dev/tmp/00184/check_lossless.py             # scratch, gitignored
hooks/tests/test_check_skill_triggers.py         # repointed test
~/.config/buvis/buvis-braid.yaml                 # + agent-rules source
~/.claude/AGENTS.md                              # deleted
~/.claude/CLAUDE.md                              # deleted
~/.claude/rules/<name>.md                        # 12 real files deleted, then braid links
~/.codex/AGENTS.md                               # hand link deleted, then braid link
~/.copilot/copilot-instructions.md               # hand link deleted, then braid link
~/.pi/agent/AGENTS.md                            # hand link deleted, then braid link
~/.kiro/steering/AGENTS.md                       # hand link deleted
```

### Module: agent-rules
- **Maps to capability**: The agent-rules repository, Content migration
- **Responsibility**: Hold the rules and guard their size.
- **Location**: `~/git/src/github.com/buvis/agent-rules/`
- **Exports**: rule directories; `tests/test_budget.py`
- New symbols: `test_codex_always_on_fits_the_budget`, `test_shared_rules_carry_no_frontmatter`, `test_every_reference_pointer_resolves`, `check_lossless.py`

### Module: host cut-over
- **Maps to capability**: Host cut-over
- **Responsibility**: Swap hand-kept files for braid output, verify, roll back on failure.
- **Location**: `hooks/tests/test_check_skill_triggers.py`, `~/.config/buvis/buvis-braid.yaml`
- **Exports**: none

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **agent-rules**: repo, content, budget test, lossless check.

### Core Layer (Phase 1)
- **host cut-over**: Depends on [agent-rules]

### Integration Layer (Phase 2)
- **references**: Depends on [host cut-over]

## Implementation Phases

### Phase 0: Foundation
**Goal**: agent-rules holds every instruction, within budget, with nothing lost.

**Tasks**:
- [ ] Create the repo, `README.md`, `LICENSE`, `.gitignore`, `tests/test_budget.py` (no deps) - Acceptance: `git -C ~/git/src/github.com/buvis/agent-rules rev-parse --abbrev-ref HEAD` prints `master`.
- [ ] Migrate and slim the content per the mapping, rewrite self-references, write `docs/dev/tmp/00184/check_lossless.py`, commit in agent-rules as `feat(rules): migrate global instructions from ~/.claude` (depends on: first task) - Acceptance: `uv run --with pytest pytest` in agent-rules passes; `python3 docs/dev/tmp/00184/check_lossless.py` exits 0; `ls ~/git/src/github.com/buvis/agent-rules/rules ~/git/src/github.com/buvis/agent-rules/hosts/claude/rules` lists exactly the 20 mapped names.

**Exit Criteria**: The repo passes its own tests and the lossless check.

### Phase 1: Core
**Goal**: Every host reads braid's output.

**Tasks**:
- [ ] Re-check the cut-over premises, delete the hand-kept files and links, append the source line, run `braid` and `braid --check`, roll back on failure (depends on: Phase 0) - Acceptance: `braid --check` exits 0; `readlink ~/.codex/AGENTS.md` names `.agents/hosts/codex/AGENTS.md`; `test ! -e ~/.claude/AGENTS.md && test ! -e ~/.kiro/steering/AGENTS.md`; `wc -c < ~/.agents/hosts/codex/AGENTS.md` prints at most 16384.

**Exit Criteria**: Success Metrics 1, 2 and 4 hold.

### Phase 2: Integration
**Goal**: Nothing points at the deleted files.

**Tasks**:
- [ ] Repoint `hooks/tests/test_check_skill_triggers.py` and run the reference sweep (depends on: Phase 1) - Acceptance: `uv run --with pytest --with tree-sitter-language-pack pytest hooks/tests/test_check_skill_triggers.py -k tracked_claude_file` passes; the `rg` sweep in the feature finds nothing; the report names the agent-plugins follow-up.

**Exit Criteria**: Full gate green: `uv run --with pytest --with tree-sitter-language-pack pytest hooks/tests`.

## Test Strategy

### Critical Scenarios
- **Happy path**: migration, cut-over, `braid --check` exit 0, Codex file under 16384 bytes.
- **Edge case**: a source line exists only in a reference after slimming → lossless check still passes.
- **Error case**: `braid --check` drifts after cut-over → every deleted path restored from buvis `HEAD`, links re-created, report filed.
- **Error case**: a host path is a real file, not a link → premise fails, host side untouched.

## Risks

- **Slimming changes meaning**: moved text is verbatim and the lossless check proves every line survives; only the listed self-reference lines are reworded.
- **The running session loses its instructions mid-task**: the delete-and-compose task has no session boundary, and failure restores from buvis `HEAD`.
- **Codex may count the global file and the project file against one 32768-byte budget** (not confirmed in Codex docs): the 16384 target leaves room for a project `AGENTS.md` of the same size.
- **Public repo exposure**: discovery 00182 decision 3 accepts personal-setup rules in public; nothing secret is in the sources (`~/.claude/AGENTS.md` and `~/.claude/rules/` are already in the public buvis/home repo).
