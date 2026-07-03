---
name: create-prd
description: Use when converting a plan, design doc, brainstorming output, or discovery doc into a structured PRD saved to the backlog. Triggers on "create PRD", "create PRD from plan", "make PRD", "convert to PRD", "save plan as PRD".
---

# Create PRD

Transform a plan or design document into an RPG-compliant PRD and save to the backlog.

**RPG means Repository Planning Graph**: Microsoft Research's method for dependency-aware repository planning (see <https://docs.task-master.dev/capabilities/rpg-method> and `assets/example_prd_rpg.md`). It separates WHAT (functional decomposition) from WHERE (structural decomposition) and connects them with an explicit dependency graph. It does NOT mean role-playing game: a PRD is a plain engineering document. Never add narrative framing, quest logs, or fantasy flavor; downstream tooling (`/plan-tasks`, the review coverage gate) parses the literal section headings, including `#### Feature:`.

## Workflow

### 0. Check for discovery doc

Before proceeding, check whether requirements were elicited:

1. If the user passed a file from `dev/local/discovery/`, requirements were elicited. Proceed to step 1.
2. Otherwise (different file, conversation context, or no argument), warn:

> No discovery doc provided. Run `/elicit-requirements` first to validate requirements, or say "skip" to proceed without one.

Wait for the user to respond. If they say "skip" (or equivalent), proceed. Otherwise, stop and let them run `/elicit-requirements`.

This gate is advisory, not blocking. The user can always skip it for simple, well-understood features.

### 1. Identify source material

Look for plan/design content in this order:

1. **Discovery doc** - file from `dev/local/discovery/` (produced by `/elicit-requirements`)
2. **Explicit file reference** - user points to a specific markdown file (e.g. a plan file in the repo)
3. **Current conversation context** - a plan just produced by brainstorming or plan mode

Read the source file if one was referenced. Extract:

- Problem statement / objective
- Core requirements and features
- Technical constraints
- Dependencies between components
- Acceptance criteria

### 2. Choose template and load it

Pick one based on complexity:

| Plan complexity | Template | Use when |
|-----------------|----------|----------|
| Simple feature | `assets/minimal.md` | Single capability, few features |
| Standard feature | `assets/standard.md` | Multiple capabilities, clear dependencies |
| Complex system | `assets/example_prd_rpg.md` | Full RPG method needed |

**Read the chosen template file before drafting.** The PRD MUST contain every section the template defines, in the same order, with the same headings.

**Do NOT model the structure on existing PRDs in the repo**, even if they look authoritative. Repo PRDs predate or postdate the template and may drift. The template is the single source of truth for structure. Use the repo's prevailing tone and naming conventions, never its section layout.

### 3. Format as PRD

Apply the full RPG structure. All four sections are mandatory; none may be omitted, renamed, or merged into another section:

1. **Functional decomposition**: Capabilities > Features (WHAT it does). Each Feature is its own sub-block under its Capability, populated with the fields the template specifies (typically Description / Inputs / Outputs / Behavior).
2. **Structural decomposition**: Modules > Files (WHERE it lives). MUST include BOTH:
   - The Repository Structure code-block tree showing module → file mapping
   - One **Module: {Name}** block per module with Maps-to-capability / Responsibility / Exports
   A file tree alone is not sufficient.
3. **Dependency graph**: Foundation Layer / Core Layer / Integration Layer with explicit per-module dependency lists. Even single-phase PRDs MUST include this section — a one-line "no dependencies; built first" entry is fine, but the heading must be present.
4. **Implementation phases**: Topological order of tasks. Each task includes its dependency reference and an Acceptance criterion.

### Optional frontmatter fields

PRD frontmatter is a YAML block at the top of the file delimited by `---` lines. Five optional fields are recognized by `/run-autopilot` Phase 0:

- `catchup: run | skip | force` — controls Phase 1 (Catchup) behavior. `run` (default) honors the batch cache; `skip` bypasses catchup entirely; `force` ignores the batch cache and re-runs full catchup. Use `skip` for PRDs that need no fresh project context (e.g. small docs-only changes). Use `force` after a major structural change you want catchup to pick up.
- `rework_cap: <int>` — caps how many review-rework cycles Phase 5 will run before pausing. Default `3`. `rework_cap: 5` allows five review cycles before pause; `rework_cap: 3` (the default) allows three. Raise this for genuinely hard PRDs that need more cycles; the default suits most work.
- `design: run | skip` — controls the Phase 1.5 design sub-step (between catchup and planning). `run` (default) generates a reviewed design doc via `/design-solution` before planning; `skip` bypasses design entirely. Use `skip` for trivial PRDs that need no implementation design.
- `design_gate: user` — when set, Phase 1.5 PAUSEs for your review of the design doc (summary + unresolved non-blockers) before planning. Absent by default (design runs autonomously, no pause). Set it on PRDs where you want to vet the design before tasks are planned.
- `doubt_reviewer: codex | fable` — selects the doubt-review (Phase 8) reviewer set for this PRD. `codex` (default) uses the standard codex doubt reviewer; `fable` opts into the Eve (Claude Fable 5) doubt-review leg. Absent by default. (Only adds/parses the flag today; the Phase 8 consumer lands in a follow-on PRD.)

Example combining several:

```yaml
---
catchup: force
rework_cap: 5
design: run
design_gate: user
doubt_reviewer: fable
---
```

All five fields are optional. Invalid values fall back to defaults (a one-line warning is logged).

### 4. Split if needed

If PRD exceeds ~200 lines or has loosely coupled parts:

- Split into separate PRD files
- Each PRD should be self-contained
- Name related PRDs with shared prefix: `00001-auth-login-v1.md`, `00002-auth-session-v1.md`

### 5. Verify structure before saving

Walk the chosen template top-to-bottom and confirm every `##`/`###` heading the template defines is present in your draft, in the same order, with the same wording. If any are missing, renamed, or out of order, revise before saving. This is the gate that prevents drift toward whatever PRD style happened to dominate the repo's existing files.

### 6. Save to backlog

```bash
# Create directory if needed
mkdir -p dev/local/prds/backlog

# Determine next sequence number
# Scan ALL prds in dev/local/prds (backlog, wip, done) for highest existing sequence
# Extract 5-digit prefix from filenames matching pattern NNNNN-*.txt
# Increment by 1, pad to 5 digits

# Save PRD with sequence prefix
```

## File Naming Convention

```text
{sequence}-{feature-slug}-v{version}.md

Where:
- sequence: 5-digit zero-padded number (00001, 00002, ...)
- Sequence determined across ALL subdirs in dev/local/prds/

Examples:
- 00001-user-auth-v1.md
- 00002-api-rate-limiting-v1.md
- 00003-dashboard-widgets-v2.md
```

## Sequence Number Logic

1. List all `.md` files in `dev/local/prds/**` and `dev/local/discovery/`
2. Extract leading 5-digit prefixes matching `^[0-9]{5}-`
3. Find max sequence number (default 0 if none exist)
4. New sequence = max + 1, zero-padded to 5 digits

## Directory Structure

```text
dev/local/prds/
├── backlog/    # Planned but not started
├── wip/        # Currently being implemented
└── done/       # Completed PRDs (for reference)
```

## PRD Lifecycle

1. **Create**: Save to `backlog/`
2. **Start work**: Move to `wip/`
3. **Complete**: Move to `done/`

## Assets

- `assets/minimal.md` - Quick PRD for simple features (~50 lines)
- `assets/standard.md` - Standard PRD structure (~100 lines)
- `assets/example_prd_rpg.md` - Full RPG method reference
