---
name: gateguard
description: Use when the gateguard PreToolUse hook denies a tool call with a "[Fact-Forcing Gate]" message - explains the fact list to present before retrying. Triggers on "fact-forcing gate", "gateguard", "why was my edit blocked".
---

# GateGuard — Fact-Forcing Pre-Action Gate

A PreToolUse hook that forces investigation before editing. Instead of self-evaluation ("are you sure?"), it demands concrete facts. The act of investigation creates context that changes the output.

The hook lives at `~/.claude/hooks/gateguard-fact-force.py` and is registered in `settings.json` PreToolUse for `Edit|Write|MultiEdit|Bash`.

## Three-Stage Behavior

```
1. DENY  — block the first Edit/Write/destructive-Bash attempt for a given target
2. FORCE — return the fact list the model must gather
3. ALLOW — permit retry once the same target is hit again in the session
```

State persists per session under `~/.claude/cache/gateguard/state-<session>.json` (auto-prunes after 30 minutes; override with `GATEGUARD_STATE_DIR`).

## Gate Types

### Edit Gate (first edit per file)

Code files (`.py`, `.ts`, `.rs`, `.go`, `.svelte`, …):

```
1. List ALL files that import/require this file (use Grep)
2. List the public functions/classes affected by this change
3. If this file reads/writes data files, show field names, structure,
   and date format (use redacted or synthetic values, not raw production data)
```

Config / data files (`.yaml`, `.json`, `.toml`, `.css`, `.sql`, …):

```
1. List ALL code or tooling that consumes this file (use Grep)
2. Show the expected fields/structure (or schema reference)
```

### MultiEdit Gate (one denial per batch)

A single denial covers ALL unchecked files in the batch — listed as bullets — instead of denying once per file. Mark them all as investigated together and the retry passes.

### Write Gate (first new file creation)

Same code-vs-config split as Edit, with creation-specific framing ("name the file(s) that will call this new file" / "confirm no existing file serves the same purpose").

### Destructive Bash Gate (every distinct destructive command)

Triggers on: `rm -rf`, `git reset --hard`, `git push --force`, `git checkout --`, `git clean -f`, `drop table`, `delete from`, `truncate`, `dd if=`.

```
1. List all files/data this command will modify or delete
2. Write a one-line rollback procedure
```

Non-destructive Bash is no longer gated. Run `ls`, `pwd`, test runners, etc. without ceremony.

## Exemptions and Skips

The hook silently allows:

- edits to `.claude/settings*.json` files (avoid recursion when configuring hooks)
- working-doc paths: `dev/local/`, `~/.claude/plans|projects|scratch|sessions|cache/`, PRD `backlog|wip|done/`, plus `.md`, `.txt`, `.rst`, `.gitignore`, `.env.example`
- read-only git introspection: `git status --porcelain`, `git diff --name-only`, `git log --oneline`, `git show <ref>`, `git branch --show-current`, `git rev-parse --abbrev-ref HEAD`
- **Edit on a file already Read in this conversation** — if the transcript shows a prior `Read` tool_use against the same `file_path`, the gate skips. The investigation already happened.

## How to Respond When Gated

1. Do not attempt the action again immediately.
2. Run the requested investigation (Grep for importers/consumers, Glob for duplicates, Read for schemas).
3. Present the facts as a brief list in your reply.
4. Then retry the original tool call. The second attempt is allowed.

## Anti-Patterns

- **Don't pre-answer the gate questions.** The investigation itself is what improves quality - guessing the answers without running Grep/Read defeats the mechanism.
- **Don't try to bypass the gate** by editing settings to disable the hook. If the gate is consistently wrong for a workflow, surface it and tune the rules.

## Related

- `block-no-verify` hook - prevents `--no-verify` git flags
- `protect-config.sh` hook - existing PreToolUse guard for config files
- `review-with-doubt` skill - skeptical post-implementation review (gateguard is pre-action)
