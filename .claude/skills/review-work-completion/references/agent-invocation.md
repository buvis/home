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

Write prompt to temp file, then invoke. **Use absolute path for the prompt file** - relative `dev/local/` paths get misresolved as `~/dev/local/` by subagents.

```
Task tool:
  subagent_type: general-purpose
  description: "Bob reviews work"
  prompt: |
    You are Bob. Run this command:

    ~/.claude/skills/use-codex/scripts/codex-run.sh -f "{bob_prompt_file_absolute_path}"

    Return output verbatim. If command fails, report failure immediately.
```

## Carl (Gemini) - DISABLED

Carl is disabled until GitHub re-enables Gemini models in copilot CLI. The model `gemini-3-pro-preview` was removed from GitHub's server-side model routing. Do not invoke Carl until this is resolved.

When re-enabling: restore prerequisite check for `~/.claude/skills/use-gemini/scripts/gemini-run.sh` in SKILL.md step 1, and add Carl back to the active agent list in step 5.

```
Task tool:
  subagent_type: general-purpose
  description: "Carl reviews work"
  prompt: |
    You are Carl. Run this command:

    ~/.claude/skills/use-gemini/scripts/gemini-run.sh -f "{carl_prompt_file}"

    Return output verbatim. If command fails, report failure immediately.
```

## Diana (Sonnet)

Write prompt to temp file, then invoke. **Use absolute path for the prompt file** - relative `dev/local/` paths get misresolved as `~/dev/local/` by subagents.

```
Task tool:
  subagent_type: general-purpose
  description: "Diana reviews work"
  prompt: |
    You are Diana. Run this command:

    ~/.claude/skills/use-sonnet/scripts/sonnet-run.sh -f "{diana_prompt_file_absolute_path}"

    Return output verbatim. If command fails, report failure immediately.
```
