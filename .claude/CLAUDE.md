# AI assistant instructions

- Solo developer. Be extremely concise, skip formalities.
- Simplest safe assumption when ambiguity isn't material.

## Workflow

- After completing all PRD tasks, run `/review-work-completion`.
- For end-to-end PRD execution, use `/run-autopilot`.
- After completing work, clean up stale worktrees, orphan branches, and temp files.

## Compaction

- After failed approach: compact
- After research, before implementation: compact
- Mid-implementation: don't compact
- After completing a PRD, before next: compact

## Planning

- End plans with unresolved questions.
- One question at a time, concise, with enough context to answer quickly.

## Model Escalation

Default model is `opusplan` (Opus in plan mode, Sonnet in execution mode).

### Known-escalation tasks (always escalate before starting)

When operating in execution mode (Sonnet), invoke `/escalate` before starting any of these:
- Planning (outside plan mode) - trigger: `planning`
- Brainstorming/design - trigger: `brainstorming`
- Code review - trigger: `code-review`
- Systematic debugging - trigger: `debugging`
- Architecture analysis - trigger: `architecture`

### Struggle-based escalation

If the enforce-escalation hook blocks you, invoke `/escalate` with the trigger type indicated in the block message. Provide:
- What you were trying to do
- What went wrong
- What you already tried
- Relevant file paths and error messages

### After escalation returns

- **Take-over results** (planning, brainstorming, code-review, debugging, struggle-repeated-failure): Accept the result and continue from there.
- **Advisory results** (architecture, struggle-no-progress): Follow the guidance to continue the work yourself.
