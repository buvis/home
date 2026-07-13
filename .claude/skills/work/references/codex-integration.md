# Codex Integration

Codex is **a review tool only** in this skill — never an implementor. UI tasks route to Gemini and backend tasks route to qwen or Claude per `work` SKILL.md's deterministic routing table; Codex appears strictly in the review path.

## Where Codex is invoked today

Codex IS currently invoked as a reviewer from `/run-autopilot`'s review phase — specifically by `skills/review-work-completion`, which dispatches the "Bob" reviewer (doubt lens) as a background Bash call to `~/.claude/skills/use-codex/scripts/codex-run.sh` (see `skills/review-work-completion/references/agent-invocation.md`). That is the one way `/work` indirectly produces work that Codex touches. The batched de-slop pass Codex used to execute was removed in the 2026-06-09 lifecycle refactor; the per-task de-slop at step 5.6 is a Claude dispatch, not Codex.

`/work` itself does not invoke Codex directly. The per-task code review at step 5.7 dispatches a Claude Agent code-reviewer, not Codex.

## Invocation

Codex review invocations go through the `use-codex` helper script — never through bare `codex` or `copilot` CLI calls. The helper auto-detects its backend: the native `codex` CLI when installed, the `copilot` CLI as fallback. On the copilot backend it defaults to `gpt-5.4` (1x multiplier); on the codex backend it uses codex's own configured default. See the `use-codex` skill for the full flag reference.

Pass the prompt with `-f <file>` (read from temp file, avoids shell-escaping issues). Reviewers use the `-a` flag (auto-approve tools) so they can run test/lint commands as part of verification — review output is read-only against the codebase, but the reviewer still needs tool access to execute its checks.

Standard review-call shape:

```bash
~/.claude/skills/use-codex/scripts/codex-run.sh -a -f /tmp/review-prompt.txt
```

The dispatch is a Bash helper-script call from the parent session, governed by the 10-min × 2 `TaskOutput` deadline documented in `references/subagent-dispatch.md` (Helper-script dispatches). It is NOT the 15-min `Monitor` watchdog (that one applies only to Agent dispatches — the implementor and the test-author subagents).

## Prompt-template note

Review prompts live with the reviewing skill, not here:

- PRD-level reviewer ("Bob") prompts: `skills/review-work-completion/references/agent-prompts.md`
- Batched de-slop prompt: `skills/run-autopilot/prompts/de-sloppify.md`

This file does not duplicate those templates — they belong to the consumers that own the review semantics. A skill that adds a NEW Codex-driven review path should write its own prompt template adjacent to its SKILL.md, then link back here.

## Common Issues

### Timeout

Codex hit a context/time limit during a long review (e.g. a large diff, a full test-suite re-run as part of verification).

**Fix**: Either narrow the review scope (specify exact files instead of a sprawling commit range) or split the work into multiple smaller review passes. Never re-dispatch the same review against the same prompt on a timeout — that is the hung-helper case and routes through `references/subagent-dispatch.md` instead.

### Context exceeded

The codebase slice the reviewer was asked to consider exceeded codex's context window.

**Fix**: Narrow scope. Pass `-d <DIR>` to constrain the working directory the reviewer can read. Trim the prompt to the specific files / commits in question rather than full architecture docs.

### Wrong approach

The reviewer's report drifted into a redesign instead of staying behavior-focused.

**Fix**: The review prompt template (in the consumer skill) should explicitly state the reviewer's scope (`flag bugs and concrete simplifications, do not propose redesigns`). If the prompt is correct and the reviewer still drifts, that is a model-fit issue and the consumer skill should consider switching the reviewer to a different backend.
