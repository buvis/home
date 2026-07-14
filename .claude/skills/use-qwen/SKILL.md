---
name: use-qwen
description: Use when running a local Qwen model (llama.cpp + pi agent) for code tasks, or onboarding, qualifying, or promoting a new local model id. Triggers on "run qwen", "qwen analyze", "ask qwen", "onboard model", "qualify model", "promote model".
---

# Qwen (Local) Skill Guide

Qwen runs locally through the `pi` coding agent against a llama.cpp-served model. Inference is free - no API cost, no token billing. The helper script defaults to `unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q6_K_XL` and exposes `-m/--model` for overrides.

> **Do not use Ollama for this.** Ollama's `qwen3coder` tool-call XML parser mangles large edit payloads, so agentic edits abort with no result. Serve the model with llama.cpp (`--jinja`, grammar-based tool-call parsing). LlamaBarn is a convenient llama.cpp manager.

## Mode

This skill covers two distinct jobs - check which one the invocation wants before doing anything:

- **Dispatch a task** (default: a coding/analysis task, or no special intent given) - follow "Running a Task" below.
- **Onboard, qualify, or promote a model** (invocation names a model id alongside "onboard"/"register"/"qualify"/"eval"/"promote", or the user just downloaded/started serving a new local model) - follow "Onboarding a New Model" below instead, and do not dispatch a coding task.

## Dependencies

- Files read from other skill dirs:
  `~/.claude/skills/use-codex/references/dispatch-contract.md` - mandatory,
  applies verbatim (see below)
- CLIs: the `pi` agent, plus `jq` and `curl` - hard-required, the helper exits 1
  without them; `mise` for resolution
- External service: a running llama.cpp server started with `--jinja`, and
  `~/.pi/agent/models.json` defining the `llamacpp` provider (see Prerequisites)

## Dispatch Contract (shared)

Background dispatch and waiting (TaskOutput-only waiting), following up, error handling, and the always-use-`-f` prompt rule are defined once in `/Users/bob/.claude/skills/use-codex/references/dispatch-contract.md`. Read it before dispatching; it applies verbatim to this skill (local inference is slow, so the background-dispatch guidance matters even more here).

Qwen-specific deltas on error handling:

- **Output that narrates actions instead of showing real tool calls** (a `thought`/`<channel|>` block, a fabricated `$ pytest` run) means the model did not actually do the work. Verify on disk; do not relay the claim.
- If the model fails the task twice, escalate - do not loop. A weaker model that cannot converge is a capability limit, not a prompt bug.

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
         "models": [{ "id": "unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q6_K_XL", "contextWindow": 131072, "cost": {"input":0,"output":0,"cacheRead":0,"cacheWrite":0} }]
       }
     }
   }
   ```
   The model `id` must match the alias the llama.cpp server reports at `/v1/models`.

## Model Selection

Local models vary widely in agentic reliability - the wrong one fails silently and lies about it.

- **Default: `unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q6_K_XL`.** Qualified 2026-07-14 (6/6 agentic eval, zero false claims - see `references/eval-runbook.md`; evidence: `~/.claude/dev/local/audit-results/qwen-eval-unsloth-Qwen3.6-27B-MTP-GGUF-UD-Q6_K_XL-2026-07-14.md`). Eval tasks were single-file, test-gated fix/feature work across Rust (ddb schema differ, transactional indexer guard, jink SQL collapse fix, GraphQL client method) and TypeScript (warden new module, parser refactor). Observed strengths: stayed inside the one permitted production file all 6 times, never touched tests, and every quantitative claim in its reports matched the real gate. A thinking model (emits `reasoning_content`); served via LlamaBarn on :8080. Multi-file work remains unproven - the eval deliberately contained none.
- **Do not** swap in a general-purpose model (e.g. `gemma4-26b`) without re-running an eval. In testing, gemma4 wrote wrong code *and* falsely claimed all tests passed.
- Every autonomous autopilot dispatch (the `/work` implementor lane, the plan-tasks preflight, the Quinn reviewer) passes `--approved-only`, so it can never run on an unqualified engine, while manual use stays unrestricted. See `references/eval-runbook.md` for the qualification procedure, and "Onboarding a New Model" below for the automated register -> eval -> promote workflow (`scripts/run-eval.sh`, `scripts/promote-default.sh`).
- This is a local model - capable for well-scoped work, not a frontier replacement. Two known failure modes: it **under-covers multi-file tasks** (finishes one file, silently drops the rest) and **over-claims completeness** in its final report. Reserve it for single-file, well-specified tasks, **always keep code review on**, and verify against a real test gate - never against its self-report.

## Onboarding a New Model

Triggered per the Mode section above. Concrete worked example (with the real registration story): `references/onboarding-walkthrough.md`. Drive it in order - do not skip ahead, and do not reuse a `pi_missing`/`endpoint_unreachable` diagnostic from dispatch mode here; these scripts have their own.

**1. Register - always safe, do immediately, no need to ask first.**

```
~/.claude/skills/use-qwen/scripts/qwen-run.sh --register-model -P <provider> [--name "..."]
```

Ask which provider/port if it isn't already clear from context - a provider must already exist in `~/.pi/agent/models.json` for that port (this only adds a model to an existing provider, never creates one). Low consequence: it only makes the model selectable via `-m`, nothing autopilot trusts yet.

**2. Qualify - stop and check before `--commit`.**

1. Pick 6 single-file, test-gated, backend tasks fresh from `dev/local/prds/done/` (use an `Explore` agent across the user's repos if unsure which - `references/eval-runbook.md` step 1 has the exact eligibility rule). Build a TSV manifest (`<prompt-file><TAB><verify-shell-command>` per line).
2. Run WITHOUT `--commit` first:
   ```
   ~/.claude/skills/use-qwen/scripts/run-eval.sh -P <provider> -m <model-id> --tasks <manifest>
   ```
3. Read the full evidence log yourself - every transcript marked **REVIEW**, ideally all six. `--commit` only checks the real gate's exit code; it cannot see a false claim written in prose.
4. **Report the score and verdict to the user before appending to the registry**, unless they already said to run the whole pipeline autonomously. Appending changes what autopilot trusts unattended - this is the one checkpoint `eval-runbook.md` exists to enforce; do not silently skip it because the score looks good.
5. If genuinely clean and the user confirms (or pre-authorized): re-run the same command with `--commit` added.

**3. Promote to default - stop and check again, separately from step 2.**

Only after phase 2's `--commit` actually landed the id in `scripts/approved-models.txt`. Confirm with the user before running - this changes the documented default for every manual/interactive session, not just autopilot, and is a separate decision from "is it qualified":

```
~/.claude/skills/use-qwen/scripts/promote-default.sh <model-id>
```

It rolls back automatically if the regression suite fails afterward. Promotion also writes `scripts/default-model.txt`, which dispatch resolution prefers whenever the live server lists it - so the new default changes what actually runs, not just the docs (multi-model servers like LlamaBarn list every downloaded model, and listing order must not decide). On success, hand-author a domain-specific rationale (task types, observed strengths/weaknesses) onto the regenerated fact-only Default bullet in `SKILL.md`, grounded in the phase 2 evidence log - never invent one.

## Running a Task

1. Write the prompt to a temp file (avoids shell-escaping issues).
2. Assemble the command:
   - `-m, --model MODEL` to override the default
   - `-R, --read-only` for analysis tasks (no file edits)
   - `-j, --json` for a structured JSON event stream (scripting)
   - `-s, --silent` accepted for compatibility (no-op; pi output is already clean)
   - `-f, --file FILE` to read the prompt from a file
   - `-o, --output FILE` to capture output
   - `-c, --continue` / `-r, --resume [ID]` to continue a session
   - `--approved-only` to restrict provider/model resolution to ids in `scripts/approved-models.txt`: auto-detect skips an unapproved live engine and keeps probing; a forced `-m`/`-P` that resolves to an unapproved id is refused (`model_id_missing`)
   - `--preflight` to probe health only: requires a real 1-token completion (a `/v1/models` listing alone never passes - the false-healthy class); exit 0 = healthy, nonzero names the failing check (`pi_missing`/`endpoint_unreachable`/`model_id_missing`/`completion_failed`). `model_id_missing` fires only under `--approved-only`: no approved id is live, or the registry file itself is missing (the message says which). Every dispatch runs the same probe internally before spawning `pi`.
   - `--register-model` (with `-P/--provider`, plus optional `--name`) to onboard a brand-new model id into `~/.pi/agent/models.json` without hand-editing JSON: probes that provider's live `/v1/models` for the real id + context window and upserts it (never guesses from a filename/convention - see `references/onboarding-walkthrough.md` for the real story). Only adds to an already-configured provider; does not touch the approved registry. Full onboarding procedure (register -> eval -> promote to default): "Onboarding a New Model" above.
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
| Health probe only | `--preflight` |
| Approved models only | `--approved-only` |
| Register a new model id | `--register-model -P <provider>` |

## Helper Script

```bash
# Write prompt to a temp file (see the shared dispatch contract), then run
~/.claude/skills/use-qwen/scripts/qwen-run.sh -f /tmp/qwen-prompt.txt

# Read-only analysis
~/.claude/skills/use-qwen/scripts/qwen-run.sh -R -f /tmp/qwen-prompt.txt

# Structured JSON output captured to a file
~/.claude/skills/use-qwen/scripts/qwen-run.sh -j -o /tmp/result.jsonl -f /tmp/qwen-prompt.txt

# Override model
~/.claude/skills/use-qwen/scripts/qwen-run.sh -m other-model -f /tmp/qwen-prompt.txt
```

Run `~/.claude/skills/use-qwen/scripts/qwen-run.sh --help` for all options.
