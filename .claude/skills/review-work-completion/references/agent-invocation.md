# Agent Invocation

## Alice (Claude subagent)

Alice runs as a direct subagent (not a nested CLI invocation - `claude -p` inside a subagent doesn't work).

```
Task tool:
  subagent_type: general-purpose
  description: "Alice reviews work against PRD requirements"
  prompt: |
    You are Alice, a code reviewer.

    {contents of alice_prompt_file}
```

The prompt file contents are inlined directly into the Task prompt. The subagent has native access to Read, Grep, Glob, and Bash tools - no need to shell out.

## Bob (Codex)

Run codex as a **direct background Bash command - do NOT wrap it in a Task subagent.** A subagent that shells out to a CLI hangs: the CLI spawns its own child process the subagent wrapper never gets a completion signal from, so the subagent yields "codex still running" and the reviewer never reports. That is the recurring Phase 4 review thrash-halt (playground 00007, 2026-06-30). Run codex directly and the harness tracks the background process, then re-invokes the session when it finishes.

Write the prompt to a temp file, then dispatch (**absolute paths** - relative `dev/local/` paths get misresolved):

```
Bash tool (run_in_background: true):
  ~/.claude/skills/use-codex/scripts/codex-run.sh -f "{bob_prompt_file_absolute_path}" -o "{abs_repo_path}/dev/local/tmp/bob-output-{id}.txt"
```

`-o` writes codex's output straight to the file step 6 consolidates - no manual save, no Agent round-trip. When the background command completes, read `bob-output-{id}.txt`. If `codex-run.sh` exits non-zero, treat Bob as a failed reviewer (graceful degradation per `retry-policy.md`); a single failed CLI reviewer does not block the cycle.

## Carl (Gemini)

Carl is the frontend & design specialist (see `agent-prompts.md`). Like Bob, run gemini as a **direct background Bash command, NOT a Task subagent** - a subagent wrapping a CLI hangs (see Bob above).

Write the prompt to a temp file, then dispatch (**absolute paths**):

```
Bash tool (run_in_background: true):
  ~/.claude/skills/use-gemini/scripts/gemini-run.sh -f "{carl_prompt_file_absolute_path}" -o "{abs_repo_path}/dev/local/tmp/carl-output-{id}.txt"
```

`-o` writes Carl's output straight to the file step 6 consolidates. When the background command completes, read `carl-output-{id}.txt`. If `gemini-run.sh` exits non-zero (e.g. monthly quota exceeded), skip Carl and proceed with the other reviewers (graceful degradation).

## Diana (Sonnet)

Diana runs Sonnet as a **direct background Bash command - do NOT wrap it in a Task subagent.** Like Bob and Carl, a subagent that shells out to a CLI hangs: the CLI spawns its own child process the subagent wrapper never gets a completion signal from, so the subagent yields "still running" and the reviewer never reports. Run `sonnet-run.sh` (headless `claude -p`, which works at the top level even though `claude -p` inside a subagent does not) directly and the harness tracks the background process, then re-invokes the session when it finishes.

Write the prompt to a temp file, then dispatch (**absolute paths** - relative `dev/local/` paths get misresolved). Pass `-a` (bypassPermissions, so the headless reviewer doesn't hang on tool prompts) and `-m sonnet` (pin the tier):

```
Bash tool (run_in_background: true):
  ~/.claude/skills/use-sonnet/scripts/sonnet-run.sh -m sonnet -a -f "{diana_prompt_file_absolute_path}" -o "{abs_repo_path}/dev/local/tmp/diana-output-{id}.txt"
```

`-o` writes Diana's output straight to the file step 6 consolidates - no manual save, no Agent round-trip. When the background command completes, read `diana-output-{id}.txt`. If `sonnet-run.sh` exits non-zero, skip Diana and proceed with the other reviewers (graceful degradation); a single failed reviewer does not block the cycle.

Diana's prompt is still built from Alice's shared template (`SKILL.md` step 4) - no sandbox-constraints appendix (that is Bob/codex only). The prompt uses absolute paths, so it resolves correctly for the headless `claude -p` reviewer.
