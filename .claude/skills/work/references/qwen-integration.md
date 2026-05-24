# Qwen Integration

How to invoke local qwen for task implementation via the `~/.claude/skills/use-qwen/scripts/qwen-run.sh` helper, which wraps the `pi` agent against a llama.cpp-served model. Always pass the prompt with `-f <file>`. The helper defaults to `qwen3-coder-30b-a3b-q4`; override with `-m`. Inference is local and free — no API cost, no token billing.

Qwen routing is gated by `task.metadata.qwen_eligible` (written upstream by `/plan-tasks`) and by the **Preflight** below. `work`'s step 3 routing table picks qwen only when the flag is `true` AND preflight is healthy; otherwise it falls back to Claude at the task's original tier.

## Preflight

A fast three-check probe MUST run before any qwen dispatch. The probe takes one of two terminal verdicts: **healthy** (proceed to dispatch) or **failed** with the specific failing check named.

The three checks, in order:

1. **`pi` resolvable on PATH.** `command -v pi` exits 0. On failure: `preflight_outcome = "pi_missing"`.
2. **llama.cpp `/v1/models` endpoint reachable.** An HTTP GET against the configured base URL's `/v1/models` returns a 2xx response within **3 seconds** (a healthy local llamacpp responds in tens of ms; 3s is conservative slack for a busy laptop). Read the base URL from `~/.pi/agent/models.json` at JSON path `.providers.llamacpp.baseUrl`. On any failure (connection refused, timeout ≥ 3s, non-2xx, missing config): `preflight_outcome = "endpoint_unreachable"`.
3. **Configured qwen model id present in the endpoint's model list.** Parse the `/v1/models` JSON response (`data[].id`). The configured model id (read from `~/.pi/agent/models.json` at JSON path `.providers.llamacpp.models[].id`, defaulting to `qwen3-coder-30b-a3b-q4`) must appear in that list. On absence: `preflight_outcome = "model_id_missing"`.

**Inputs**: PATH, the llama.cpp server endpoint (from `~/.pi/agent/models.json`'s `baseUrl`), the configured qwen model id (from the same file's `models[].id` — reused from the `use-qwen` skill's prerequisites).

**Outputs**: Health verdict — `"healthy"`, or one of `"pi_missing"` / `"endpoint_unreachable"` / `"model_id_missing"`.

**Fallback rule**: ANY preflight failure → fall back to Claude at the task's original tier (`haiku` → Haiku, `sonnet` → Sonnet). Behavior in this fallback is byte-for-byte identical to today's Claude dispatch for the same task; the only addition is the recorded `preflight_outcome` in the attempt log (see `references/attempt-logging.md`).

The preflight runs once per task attempt. It does NOT run on Claude or Gemini dispatches.

## One-shot attempt budget — and why it always escalates to Sonnet

A qwen-routed task gets exactly one qwen attempt. If qwen's output fails the step-5.5 per-task test gate, the re-dispatch targets **Claude Sonnet** regardless of the task's original tier (`haiku` → Sonnet, `sonnet` → Sonnet). qwen never re-runs for the same task.

The fixed-Sonnet target is intentional and asymmetric vs. the **preflight-failure** fallback (which keeps the original tier: `haiku` → Haiku, `sonnet` → Sonnet). Two different failure shapes, two different recoveries:

- **Preflight failure** is an *infrastructure* signal — qwen was unreachable, missing a model, or had no resolvable `pi`. The task itself was never attempted; nothing observable suggests the task is harder than its plan-time tier said. Preserve the tier the planner picked.
- **Step-5.5 gate failure after a qwen attempt** is a *correctness* signal — qwen produced code that did not pass the tests Tess wrote. The empirical evidence from this attempt says the task is harder than its qwen-eligible classification implied (qwen-eligible = `≤2`-file + `haiku`/`sonnet`). A retry at the same tier on the same model family would be cheap but risk under-powering the retry; Sonnet is the conservative floor that any qwen-eligible task can re-run at. Escalating from `haiku` to `sonnet` here is the price of having tried qwen in the first place.

The normal max-2 step-5.5 retry budget then applies to the Sonnet re-dispatches (not qwen). The qwen attempt does NOT consume a slot in that budget — it consumed the (single) qwen attempt instead.

## Prompt Template

```
Task: {task.subject}

Description:
{task.description}

Acceptance Criteria:
{task.acceptance_criteria or "Complete the task as described"}

Architecture:
{relevant sections from AGENTS.md or agent_docs/architecture.md}

Key invariants:
{domain rules and boundaries from AGENTS.md or agent_docs/}

Context:
- Working directory: {cwd}
- Relevant files: {list files if known}

Instructions:
1. Read existing code before making changes
2. Follow existing patterns and conventions
3. Run tests if available
4. Keep changes minimal and focused
```

## Permission Modes

All flags are passed to `qwen-run.sh`.

| Task type | Flags |
|-----------|-------|
| Analysis only | `-R -f prompt.txt` (read-only — no file edits) |
| Code changes | `-f prompt.txt` (default — pi auto-approves edit tools) |
| Structured output | `-j -o /tmp/result.jsonl -f prompt.txt` |
| Override model | `-m other-model -f prompt.txt` |

## Execution Modes

| Mode | Flag | Use case |
|------|------|----------|
| Non-interactive | `-f prompt.txt` | Scripted execution, exits after completion |
| Resume recent session | `-c` | Continue most recent session |
| Resume specific session | `-r <ID>` | Continue named session |

## TDD Implementation Mode (Ivan)

When tests already exist from step 2.7, use this prompt variant instead of the standard template:

```
Failing tests exist at: {test_file_paths}

Make all failing tests pass.

Architecture:
{relevant sections from AGENTS.md or agent_docs/architecture.md}

Key invariants:
{domain rules and boundaries from AGENTS.md or agent_docs/}

Context:
- Working directory: {cwd}
- Relevant files: {list files if known}

Rules:
1. Do NOT modify test files
2. Read the tests to understand expected behavior
3. Implement minimal code to pass all tests
4. Follow existing patterns and conventions
5. Run tests after implementation to verify
```

The task's acceptance criteria prose is intentionally omitted. Tests ARE the spec.

## Common Issues

### Under-coverage on multi-file tasks

Qwen finishes one file and silently drops the rest of a multi-file task.

**Fix**: `task.metadata.qwen_eligible` already restricts qwen to `≤2`-file backend tasks at planning time (see PRD 00032). If a multi-file task slips through, the step-5.5 per-task test gate catches it — the one-shot qwen attempt budget then escalates the next attempt to Claude Sonnet.

### Over-claims completeness

Qwen narrates "all tests pass" or "implementation complete" in its final report without having actually run anything to verify it.

**Fix**: The per-task test gate at step 5.5 is the source of truth — qwen's self-report is never treated as a completion signal. Output that narrates actions instead of showing real tool calls (a `thought`/`<channel|>` block, a fabricated `$ pytest` run) is the visible symptom; the test gate is the backstop.

### Slow dispatch

Local inference is slow; a `qwen-run.sh` call can run for many minutes. The `use-qwen` skill prescribes background dispatch with `TaskOutput(task_id, block=true, timeout=600000)` (10-min wait; on a still-running return, re-issue the wait once, then treat a second timeout as a hang). `references/subagent-dispatch.md` documents the same 10-min × 2 watchdog pattern for qwen helper-script dispatches.

### Wrong model loaded

The llama.cpp server is running but serves a different model than `~/.pi/agent/models.json` declares.

**Fix**: The preflight's third check (`model_id_missing`) catches this. The task falls back to Claude at its original tier.

### Helper exits non-zero

`qwen-run.sh` returned a non-zero exit code.

**Fix**: Do not silently re-dispatch on qwen. The one-shot qwen attempt budget (see `SKILL.md` step 5.5) escalates the next attempt to Claude Sonnet — qwen failure consumes the attempt but does not consume a slot in the max-2 retry budget for the Claude Sonnet re-dispatches.
