---
name: create-prd
description: Create PRD from a plan or design document. Use when converting plans, design docs, or brainstorming output into structured PRDs. Triggers on "create PRD", "create PRD from plan", "make PRD", "convert to PRD", "save plan as PRD".
---

# Create PRD

Transform a plan or design document into an RPG-compliant PRD and save to the backlog.

## Workflow

### 1. Identify source material

Look for plan/design content in this order:

1. **Explicit file reference** - user points to a specific markdown file (e.g. a plan file in the repo)
2. **Current conversation context** - a plan just produced by brainstorming or plan mode

Read the source file if one was referenced. Extract:

- Problem statement / objective
- Core requirements and features
- Technical constraints
- Dependencies between components
- Acceptance criteria

### 2. Choose template

| Plan complexity | Template | Use when |
|-----------------|----------|----------|
| Simple feature | `assets/minimal.md` | Single capability, few features |
| Standard feature | `assets/standard.md` | Multiple capabilities, clear dependencies |
| Complex system | `assets/example_prd_rpg.md` | Full RPG method needed |

### 3. Format as PRD

Apply RPG structure:

1. **Functional decomposition**: Capabilities > Features (WHAT it does)
2. **Structural decomposition**: Modules > Files (WHERE it lives)
3. **Dependency graph**: Explicit dependencies between modules
4. **Implementation phases**: Topological order of tasks

### 4. Split if needed

If PRD exceeds ~200 lines or has loosely coupled parts:

- Split into separate PRD files
- Each PRD should be self-contained
- Name related PRDs with shared prefix: `00001-auth-login-v1.md`, `00002-auth-session-v1.md`

### 5. Save to backlog

```bash
# Create directory if needed
mkdir -p .local/prds/backlog

# Determine next sequence number
# Scan ALL prds in .local/prds (backlog, wip, done) for highest existing sequence
# Extract 5-digit prefix from filenames matching pattern NNNNN-*.txt
# Increment by 1, pad to 5 digits

# Save PRD with sequence prefix
```

## File Naming Convention

```text
{sequence}-{feature-slug}-v{version}.md

Where:
- sequence: 5-digit zero-padded number (00001, 00002, ...)
- Sequence determined across ALL subdirs in .local/prds/

Examples:
- 00001-user-auth-v1.md
- 00002-api-rate-limiting-v1.md
- 00003-dashboard-widgets-v2.md
```

## Sequence Number Logic

1. List all `.md` files in `.local/prds/**`
2. Extract leading 5-digit prefixes matching `^[0-9]{5}-`
3. Find max sequence number (default 0 if none exist)
4. New sequence = max + 1, zero-padded to 5 digits

## Directory Structure

```text
.local/prds/
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
