# Progressive Disclosure Guide

How to organize detailed documentation outside CLAUDE.md so Claude loads it only when needed.

## Concept

Progressive disclosure keeps CLAUDE.md lean by storing detailed documentation in separate files. Claude reads these files on-demand based on the task at hand.

**Benefits:**
- Smaller context window usage for simple tasks
- Task-relevant context when needed
- Easier maintenance of detailed docs
- No stale information in CLAUDE.md

## Directory Structure

Recommended structure:

```
project/
├── CLAUDE.md                    # Core onboarding (<100 lines)
├── agent_docs/                  # Detailed documentation
│   ├── architecture.md          # System design
│   ├── database.md              # Schema and relationships
│   ├── api.md                   # Endpoints and contracts
│   ├── testing.md               # Test patterns
│   ├── deployment.md            # CI/CD and environments
│   └── troubleshooting.md       # Common issues
└── .claude/
    └── commands/                # Slash commands for specific workflows
        ├── review.md
        └── deploy.md
```

## Referencing from CLAUDE.md

Add a documentation section that tells Claude what's available:

```markdown
## Documentation

Before starting work, read relevant files from `agent_docs/`:

| File | When to Read |
|------|--------------|
| `architecture.md` | Working on system design or service boundaries |
| `database.md` | Database changes, migrations, or queries |
| `api.md` | API endpoints, request/response contracts |
| `testing.md` | Writing or modifying tests |
| `deployment.md` | CI/CD, environment setup, releases |
```

Or simpler format:

```markdown
## Documentation

Read from `agent_docs/` as needed:
- `architecture.md` - System design and service boundaries
- `database.md` - Schema documentation and relationships
- `api.md` - API endpoints and contracts
- `testing.md` - Test patterns and fixtures
```

## What Goes Where

### In CLAUDE.md (Universal)

- Project name and purpose (1-2 lines)
- Tech stack list
- Directory structure overview
- Essential commands (build, test, lint)
- Pointer to agent_docs/

### In agent_docs/ (Detailed)

| File | Contents |
|------|----------|
| `architecture.md` | Service boundaries, data flow, design decisions |
| `database.md` | Table schemas, relationships, migration procedures |
| `api.md` | Endpoint documentation, auth, error handling |
| `testing.md` | Test patterns, fixtures, mocking strategies |
| `deployment.md` | Environments, CI/CD, rollback procedures |
| `troubleshooting.md` | Common errors and solutions |

## Writing Effective agent_docs Files

### Structure Each File

```markdown
# Topic Title

Brief overview (2-3 sentences).

## Quick Reference

Most commonly needed information first.

## Details

Deeper documentation organized by subtopic.

## File References

Point to actual code:
- Main implementation: `src/feature/index.ts:15-45`
- Tests: `tests/feature.test.ts`
```

### Keep Files Focused

- One topic per file
- 50-200 lines per file
- Use file:line references instead of code snippets
- Update when code changes

### Avoid Code Duplication

Instead of embedding code:

```markdown
❌ Bad: Code snippet that will become stale

## Example

const handler = async (req, res) => {
  // 50 lines of code
}
```

Use pointers:

```markdown
✅ Good: File reference

## Implementation

See the request handler at `src/api/handler.ts:24-75`.
Key patterns:
- Error handling: lines 30-40
- Validation: lines 45-55
- Response formatting: lines 60-70
```

## Monorepo Considerations

For monorepos, organize by app/package:

```
monorepo/
├── CLAUDE.md                    # Root overview
├── agent_docs/
│   ├── architecture.md          # Overall system
│   └── apps/
│       ├── web.md               # Web app details
│       ├── api.md               # API details
│       └── admin.md             # Admin details
└── apps/
    ├── web/
    │   └── CLAUDE.md            # App-specific (optional)
    ├── api/
    │   └── CLAUDE.md
    └── admin/
        └── CLAUDE.md
```

Root CLAUDE.md should explain monorepo structure and point to app-specific docs.

## Maintenance

### When to Update agent_docs

- After significant refactoring
- When adding new features
- When changing core patterns
- During onboarding new team members

### Staleness Prevention

1. Keep docs high-level (concepts over code)
2. Use file:line references (IDE can update)
3. Review during PR process
4. Flag outdated sections for update

## Integration with Claude Code Features

### Slash Commands

For workflow-specific instructions, use `.claude/commands/`:

```
.claude/commands/
├── review.md      # Code review workflow
├── deploy.md      # Deployment checklist
├── migrate.md     # Database migration steps
└── debug.md       # Debugging workflow
```

### Hooks

Combine with hooks for automation:

```json
{
  "hooks": {
    "post-commit": [{
      "command": "npm run lint:fix",
      "description": "Auto-fix lint issues"
    }]
  }
}
```

This removes the need for style instructions in CLAUDE.md.
