---
name: save-plan
description: Save current plan into PRD file
---

# Save Plan to PRD

Transform the current plan into an RPG-compliant PRD and save to the backlog.

## Workflow

### 1. Extract plan content

From the current conversation, identify:
- Problem statement / objective
- Core requirements and features
- Technical constraints
- Dependencies between components
- Acceptance criteria

### 2. Choose template

| Plan complexity | Template | Use when |
|-----------------|----------|----------|
| Simple feature | `templates/minimal.txt` | Single capability, few features |
| Standard feature | `templates/standard.txt` | Multiple capabilities, clear dependencies |
| Complex system | `templates/example_prd_rpg.txt` | Full RPG method needed |

### 3. Format as PRD

Apply RPG structure:
1. **Functional decomposition**: Capabilities → Features (WHAT it does)
2. **Structural decomposition**: Modules → Files (WHERE it lives)
3. **Dependency graph**: Explicit dependencies between modules
4. **Implementation phases**: Topological order of tasks

### 4. Split if needed

If PRD exceeds ~200 lines or has loosely coupled parts:
- Split into separate PRD files
- Each PRD should be self-contained
- Name related PRDs with shared prefix: `auth-login-v1.txt`, `auth-session-v1.txt`

### 5. Save to backlog

```bash
# Create directory if needed
mkdir -p .local/prds/backlog

# Save PRD
# Naming: {feature-slug}-v{version}.txt
```

## File Naming Convention

```
{feature-slug}-v{version}.txt

Examples:
- user-auth-v1.txt
- api-rate-limiting-v1.txt
- dashboard-widgets-v2.txt
```

## Directory Structure

```
.local/prds/
├── backlog/    # Planned but not started
├── wip/        # Currently being implemented
└── done/       # Completed PRDs (for reference)
```

## PRD Lifecycle

1. **Create**: Save to `backlog/`
2. **Start work**: Move to `wip/`
3. **Complete**: Move to `done/`

## Templates

- `templates/minimal.txt` - Quick PRD for simple features (~50 lines)
- `templates/standard.txt` - Standard PRD structure (~100 lines)
- `templates/example_prd_rpg.txt` - Full RPG method reference
