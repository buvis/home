---
name: gateguard
description: Use when the gateguard PreToolUse hook denies a tool call with a "[Fact-Forcing Gate]" message - explains the fact list to present before retrying. Triggers on "fact-forcing gate", "gateguard", "why was my edit blocked".
---

# GateGuard — Fact-Forcing Pre-Action Gate

A PreToolUse hook that forces investigation before editing. Instead of self-evaluation ("are you sure?"), it demands concrete facts. The act of investigation creates context that changes the output.

The hook lives at `~/.claude/hooks/gateguard-fact-force.py` and is registered in `settings.json` PreToolUse for `Edit|Write|MultiEdit|Bash`.

## Three-Stage Behavior

```
1. DENY  — block the first Edit/Write/Bash attempt for a given target
2. FORCE — return the fact list the model must gather
3. ALLOW — permit retry once the same target is hit again in the session
```

State persists per session under `~/.claude/cache/gateguard/state-<session>.json` (auto-prunes after 30 minutes; override with `GATEGUARD_STATE_DIR`).

## Gate Types

### Edit / MultiEdit Gate (first edit per file)

Each file in a MultiEdit batch is gated individually.

```
1. List ALL files that import/require this file (use Grep)
2. List the public functions/classes affected by this change
3. If this file reads/writes data files, show field names, structure,
   and date format (use redacted or synthetic values, not raw production data)
4. Quote the user's current instruction verbatim
```

### Write Gate (first new file creation)

```
1. Name the file(s) and line(s) that will call this new file
2. Confirm no existing file serves the same purpose (use Glob)
3. If this file reads/writes data files, show field names, structure,
   and date format (use redacted or synthetic values, not raw production data)
4. Quote the user's current instruction verbatim
```

### Destructive Bash Gate (every destructive command)

Triggers on: `rm -rf`, `git reset --hard`, `git push --force`, `git checkout --`, `git clean -f`, `drop table`, `delete from`, `truncate`, `dd if=`.

```
1. List all files/data this command will modify or delete
2. Write a one-line rollback procedure
3. Quote the user's current instruction verbatim
```

### Routine Bash Gate (once per session)

```
1. The current user request in one sentence
2. What this specific command verifies or produces
```

## Exemptions

The hook silently allows:
- edits to `.claude/settings*.json` files (avoid recursion when configuring hooks)
- read-only git introspection (`git status --porcelain`, `git diff --name-only`, `git log --oneline`, `git show <ref>`, `git branch --show-current`, `git rev-parse --abbrev-ref HEAD`)

## How to Respond When Gated

1. Do not attempt the action again immediately.
2. Run the requested investigation (Grep for importers, Glob for duplicates, Read for schemas).
3. Present the facts as a brief list in your reply.
4. Then retry the original tool call. The second attempt is allowed.

## Anti-Patterns

- **Don't pre-answer the gate questions.** The investigation itself is what improves quality - guessing the answers without running Grep/Read defeats the mechanism.
- **Don't try to bypass the gate** by editing settings to disable the hook. If the gate is consistently wrong for a workflow, surface it and tune the rules.

## Related

- `block-no-verify` hook - prevents `--no-verify` git flags
- `protect-config.sh` hook - existing PreToolUse guard for config files
- `review-with-doubt` skill - skeptical post-implementation review (gateguard is pre-action)
