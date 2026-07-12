---
name: manage-agents-md
description: Use when creating, auditing, or improving an AGENTS.md file for AI coding agents (progressive disclosure, context window budgeting). Triggers on "agents.md", "AGENTS.md", "create AGENTS.md", "audit AGENTS.md", "improve AGENTS.md".
---

# manage-agents-md

Build and maintain high-quality AGENTS.md files that maximize AI coding agent efficiency.

## Core Principle

AI coding agents are stateless. AGENTS.md is the **only file** that goes into every conversation. It must onboard the agent to your codebase efficiently without bloating the context window.

**Critical insight**: AI agents may ignore AGENTS.md contents if deemed irrelevant. Overstuffed files with non-universal instructions get ignored entirely.

## Three Pillars of a Good AGENTS.md

Every AGENTS.md should answer three questions concisely:

1. **WHAT** - Tech stack, project structure, key directories
2. **WHY** - Project purpose, what each part does
3. **HOW** - Essential commands, verification steps, workflows

## Hard Constraints

| Constraint | Limit | Rationale |
|------------|-------|-----------|
| Total lines | < 300 (ideal: < 100) | Context window is shared with system prompt, conversation, tools |
| Instructions | < 100 | Frontier models reliably follow ~150-200 instructions; system prompt uses ~50 |
| Applicability | 100% universal | Non-universal instructions cause entire file to be ignored |

What NOT to include: the exclusion list lives in `references/checklist.md`
("What NOT to Include" + "Common Anti-Patterns") — style guidelines belong in
linters, task-specific instructions in commands, code in `file:line` pointers.

## Progressive Disclosure Pattern

Keep AGENTS.md lean by pointing to detailed docs in `agent_docs/` — layout,
index format, and the pointers-over-copies rule are in
`references/progressive-disclosure.md`.

## Template

Full and minimal AGENTS.md structures live in `references/template.md`.

## Creating a New AGENTS.md

1. **Analyze the project** - Identify stack, structure, key workflows
2. **Start minimal** - Begin with <50 lines covering essentials
3. **Create agent_docs/** - Move detailed documentation there (per `references/progressive-disclosure.md`)
4. **Add pointers** - Reference agent_docs from AGENTS.md
5. **Validate** - Run checklist from `references/checklist.md`

## Auditing an Existing AGENTS.md

1. **Count lines** - Flag if >300 lines
2. **Check universality** - Every instruction should apply to every task
3. **Find embedded code** - Replace with file:line pointers
4. **Identify style rules** - Move to linter config
5. **Extract conditionals** - Move to agent_docs/
6. **Validate** - Run checklist from `references/checklist.md`

## Integrations

- **Formatting/linting**: configure pre-commit hooks instead of writing style
  instructions into AGENTS.md.
- **Specific workflows**: put task-specific instructions in a project commands
  directory, not AGENTS.md.

## Reference Files

- `references/template.md` - Complete AGENTS.md template with examples
- `references/checklist.md` - Validation checklist, exclusion list, anti-patterns
- `references/progressive-disclosure.md` - Guide for organizing agent_docs/
