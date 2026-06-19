---
name: use-qwen
description: Use when running a local Qwen model (via llama.cpp and the pi agent) for code analysis, refactoring, or editing - local inference, no API cost. Triggers on "run qwen", "qwen analyze", "ask qwen", "local model task".
---

# Qwen (Local) Skill Guide

Qwen runs locally through the `pi` coding agent against a llama.cpp-served model. Inference is free - no API cost, no token billing. The helper script defaults to `unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q4_K_M` and exposes `-m/--model` for overrides.

> **Do not use Ollama for this.** Ollama's `qwen3coder` tool-call XML parser mangles large edit payloads, so agentic edits abort with no result. Serve the model with llama.cpp (`--jinja`, grammar-based tool-call parsing). LlamaBarn is a convenient llama.cpp manager.

## Prerequisites

Before the helper will work:

1. **A llama.cpp server running** with the model loaded and `--jinja` enabled (e.g. via LlamaBarn). Note its port.
2. **pi installed** (mise-managed) and reshimmed so it is on PATH.
3. **`~/.pi/agent/models.json`** defines the `llamacpp` provider and the model. Minimal entry (adjust the port to your server):
   ```json
   {
     "providers": {
       "llamacpp": {
         "baseUrl": "http://127.0.0.1:8080/v1",
         "api": "openai-completions",
         "apiKey": "llamacpp",
         "compat": { "supportsDeveloperRole": false, "supportsReasoningEffort": false },
         "models": [{ "id": "unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q4_K_M", "contextWindow": 131072, "cost": {"input":0,"output":0,"cacheRead":0,"cacheWrite":0} }]
       }
     }
   }
   ```
   The model `id` must match the alias the llama.cpp server reports at `/v1/models`.

## Model Selection

Local models vary widely in agentic reliability - the wrong one fails silently and lies about it.

- **Default: `qwen3-coder-30b-a3b` (Q4_K_M).** A *coder*-tuned model. It cleared 5 of 6 real sonnet-tier Rust tasks in an agentic eval. Best on single-file, well-scoped work.
- **Do not** swap in a general-purpose model (e.g. `gemma4-26b`) without re-running an eval. In testing, gemma4 wrote wrong code *and* falsely claimed all tests passed.
- This is a local model - capable for well-scoped work, not a frontier replacement. Two known failure modes: it **under-covers multi-file tasks** (finishes one file, silently drops the rest) and **over-claims completeness** in its final report. Reserve it for single-file, well-specified tasks, **always keep code review on**, and verify against a real test gate - never against its self-report.

## Running a Task

1. Write the prompt to a temp file (avoids shell-escaping issues).
2. Assemble the command:
   - `-m, --model MODEL` to override the default
   - `-R, --read-only` for analysis tasks (no file edits)
   - `-j, --json` for a structured JSON event stream (scripting)
   - `-f, --file FILE` to read the prompt from a file
   - `-o, --output FILE` to capture output
   - `-c, --continue` / `-r, --resume [ID]` to continue a session
3. Run the helper, capture output.
4. **Verify the actual result - never trust the model's textual claim.** A local model may narrate "all tests pass" without having run them. Run the tests yourself, check the files on disk, then report.

### Quick Reference

| Use case | Key flags |
| --- | --- |
| Implement / edit code | `-f /tmp/qwen-prompt.txt` |
| Read-only analysis | `-R -f /tmp/qwen-prompt.txt` |
| Structured output | `-j -o /tmp/result.jsonl -f /tmp/qwen-prompt.txt` |
| Override model | `-m other-model -f /tmp/qwen-prompt.txt` |
| Resume recent session | `-c` |

## Background Dispatch and Waiting

Local inference is slow; a `qwen-run.sh` call can run for many minutes.

1. Dispatch the helper with `run_in_background: true`. The dispatch result returns the task's output file path.
2. Wait with `TaskOutput(task_id, block=true, timeout=600000)` (600000 ms = 10 min, the max per call). It returns on completion or at the deadline.
3. On completion, `Read` the output file. On a timeout return, treat it as an infrastructure hang - do not silently re-dispatch.

**Never hand-roll a polling loop.** Shell `while`/`wc -c` stability loops contain control flow Warden cannot analyze statically, so they prompt for approval and stall unattended runs. The harness notifies you when a background task finishes.

## Error Handling

- Stop and report when `qwen-run.sh` exits non-zero; request direction before retrying.
- **Output that narrates actions instead of showing real tool calls** (a `thought`/`<channel|>` block, a fabricated `$ pytest` run) means the model did not actually do the work. Verify on disk; do not relay the claim.
- If the model fails the task twice, escalate - do not loop. A weaker model that cannot converge is a capability limit, not a prompt bug.

## Helper Script

**IMPORTANT**: Use `-f` with a temp file for prompts to avoid shell-escaping issues.

```bash
# Write prompt to a temp file, then run
echo 'Your prompt here (can contain "quotes", parens(), etc.)' > /tmp/qwen-prompt.txt
~/.claude/skills/use-qwen/scripts/qwen-run.sh -f /tmp/qwen-prompt.txt

# Read-only analysis
~/.claude/skills/use-qwen/scripts/qwen-run.sh -R -f /tmp/qwen-prompt.txt

# Structured JSON output captured to a file
~/.claude/skills/use-qwen/scripts/qwen-run.sh -j -o /tmp/result.jsonl -f /tmp/qwen-prompt.txt

# Override model
~/.claude/skills/use-qwen/scripts/qwen-run.sh -m other-model -f /tmp/qwen-prompt.txt
```

Run `~/.claude/skills/use-qwen/scripts/qwen-run.sh --help` for all options.
