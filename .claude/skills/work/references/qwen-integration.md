# Qwen Integration

How to invoke local qwen for task implementation via the `~/.claude/skills/use-qwen/scripts/qwen-run.sh` helper, which wraps the `pi` agent against a llama.cpp-served model. Always pass the prompt with `-f <file>`. The helper defaults to `unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q4_K_M`; `-m` overrides it, but an autopilot dispatch runs under `--approved-only`, so any id it names must be in the approved registry or the run is refused. Inference is local and free — no API cost, no token billing.

Qwen routing is gated by `task.metadata.qwen_eligible` (written upstream by `/plan-tasks`) and by the **Preflight** below. `work`'s step 3 routing table picks qwen only when the flag is `true` AND preflight is healthy; otherwise it falls back to Claude at the task's original tier.

## Preflight

A four-check probe MUST run before any qwen dispatch. The probe takes one of two terminal verdicts: **healthy** (proceed to dispatch) or **failed** with the specific failing check named. Checks short-circuit in order — the first failure is the verdict.

The four checks, in order:

1. **`pi` resolvable on PATH.** `command -v pi` exits 0. On failure: `preflight_outcome = "pi_missing"`.
2. **llama.cpp `/v1/models` endpoint reachable.** An HTTP GET against the configured base URL's `/v1/models` returns a 2xx response within **2 seconds** (a healthy local llamacpp responds in tens of ms; 2s is conservative slack for a busy laptop). Read the base URL from `~/.pi/agent/models.json` at JSON path `.providers.llamacpp.baseUrl`. On any failure (connection refused, timeout ≥ 2s, non-2xx, missing config): `preflight_outcome = "endpoint_unreachable"`.
3. **An APPROVED model id is live on the endpoint.** Parse the `/v1/models` JSON response (`data[].id` — a server can list SEVERAL ids, so check every entry, never just the first). At least one listed id must appear in the approved registry (`~/.claude/skills/use-qwen/scripts/approved-models.txt`); that approved id is the one check 4 probes and the dispatch runs. On absence: `preflight_outcome = "model_id_missing"`. **The registry, not the config, is the authority here.** This is exactly the gate `qwen-run.sh --approved-only` applies at dispatch, and the preflight MUST apply it too: a preflight that verdicts `healthy` on an unapproved-but-live engine sends `/work` into a dispatch the script then refuses — which consumes the one-shot qwen attempt (see "Helper exits non-zero") on a task qwen never actually ran, and logs `preflight_outcome: "healthy"` for an attempt that never happened. The Fallback rule below is the intended path instead.
4. **Real 1-token completion succeeds.** Checks 2-3 only enumerate configured models — LlamaBarn (and any on-demand server) lists the model straight from config and spawns the inference worker *lazily, on the first completion*. They pass even when the worker cannot start, so this is the only check that exercises the spawn. POST to `${baseUrl}/chat/completions` with body `{"model": <the approved id selected by check 3>, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1, "stream": false}`, timeout **120 seconds**. A 2xx response → the check passes (verdict `healthy`). Any non-2xx (e.g. `500 "failed to spawn server instance"`), connection error, or timeout → `preflight_outcome = "completion_failed"`. The 120s ceiling covers a cold model load (the ~18.5 GB GGUF takes tens of seconds the first time); the probe doubles as a warm-up, so the model is resident when the real dispatch follows — the load is not wasted. A backend that cannot emit one token in 120s would blow the task watchdog anyway: treat it as failed and fall back.

**Inputs**: PATH, the llama.cpp server endpoint and its `/chat/completions` route (from `~/.pi/agent/models.json`'s `baseUrl`), the ids the endpoint actually reports at `/v1/models`, and the approved-model registry (`~/.claude/skills/use-qwen/scripts/approved-models.txt`).

**The one-command probe**: `qwen-run.sh --preflight --approved-only` performs checks 1-4 exactly as written and exits 0 only on `healthy`. Prefer it over a hand-rolled probe — running the same script the dispatch runs is what keeps the preflight verdict and the dispatch decision from ever disagreeing.

**Outputs**: Health verdict — `"healthy"`, or one of `"pi_missing"` / `"endpoint_unreachable"` / `"model_id_missing"` / `"completion_failed"`.

**Fallback rule**: ANY preflight failure → fall back to Claude at the task's original tier (`haiku` → Haiku, `sonnet` → Sonnet). Behavior in this fallback is byte-for-byte identical to today's Claude dispatch for the same task; the only addition is the recorded `preflight_outcome` in the attempt log (see `references/attempt-logging.md`). A failed probe does NOT consume the one-shot qwen attempt budget — no qwen attempt happened.

The preflight runs once per task attempt. It does NOT run on Claude or Gemini dispatches.

**Script enforcement (PRD 00019)**: `qwen-run.sh` enforces the same deciding signal internally — every dispatch re-runs the 1-token completion probe after provider/model resolution and exits 1 with the failing outcome named on stderr (`completion_failed` / `endpoint_unreachable` / `model_id_missing` / `pi_missing`) BEFORE any `pi` spawn; its `/v1/models` probe is only the provider auto-detect fast pre-check. `qwen-run.sh --preflight --approved-only` runs the probe standalone (all four checks; the model id it completes against is the approved id the endpoint reports, not a config cross-check) and exits 0 only on a successful completion — the one-command probe `review-work-completion` step 1 uses for Quinn's active-check. Regression-tested by `~/.claude/skills/use-qwen/scripts/test_qwen_run.sh` (models-200/completion-500 → refuse, no dispatch). Every autopilot surface passes `--approved-only`, so an autonomous dispatch can never reach a model id outside the registry — that guarantee lives at the call sites, not in anything the script infers on its own.

## One-shot attempt budget — and why it always escalates to Sonnet

A qwen-routed task gets exactly one qwen attempt. If qwen's output fails the step-5.5 per-task test gate, the re-dispatch targets **Claude Sonnet** regardless of the task's original tier (`haiku` → Sonnet, `sonnet` → Sonnet). qwen never re-runs for the same task.

The fixed-Sonnet target is intentional and asymmetric vs. the **preflight-failure** fallback (which keeps the original tier: `haiku` → Haiku, `sonnet` → Sonnet). Two different failure shapes, two different recoveries:

- **Preflight failure** is an *infrastructure* signal — qwen was unreachable, couldn't spawn its inference worker, was missing a model, or had no resolvable `pi`. The task itself was never attempted; nothing observable suggests the task is harder than its plan-time tier said. Preserve the tier the planner picked.
- **Step-5.5 gate failure after a qwen attempt** is a *correctness* signal — qwen produced code that did not pass the tests Tess wrote. The empirical evidence from this attempt says the task is harder than its qwen-eligible classification implied (qwen-eligible = non-UI + `≤3`-file + `haiku`/`sonnet` + no public-contract edit). A retry at the same tier on the same model family would be cheap but risk under-powering the retry; Sonnet is the conservative floor that any qwen-eligible task can re-run at. Escalating from `haiku` to `sonnet` here is the price of having tried qwen in the first place.

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

**Every command line on this page is an autopilot dispatch, so every one carries `--approved-only`** — it restricts engine resolution to the eval-qualified allowlist (`use-qwen/scripts/approved-models.txt`), and an autonomous dispatch must never reach an unqualified model. There is no autopilot task type that omits it. Manual, unpinned use is a different surface and is documented in `use-qwen/SKILL.md`; a model override (`-m`) belongs there too, since under `--approved-only` an id outside the registry is refused by design.

| Task type | Flags |
|-----------|-------|
| Analysis only | `-R --approved-only -f prompt.txt` (read-only — no file edits) |
| Code changes | `--approved-only -f prompt.txt` (default — pi auto-approves edit tools) |
| Structured output | `-j --approved-only -o /tmp/result.jsonl -f prompt.txt` |

## Execution Modes

| Mode | Flag | Use case |
|------|------|----------|
| Non-interactive | `--approved-only -f prompt.txt` | Scripted execution, exits after completion |
| Resume recent session | `--approved-only -c` | Continue most recent session |
| Resume specific session | `--approved-only -r <ID>` | Continue named session |

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

**Fix**: `task.metadata.qwen_eligible` already restricts qwen to `≤3`-file backend tasks at planning time (see PRD 00032, widened by PRD 00019). If a wider task slips through, the step-5.5 per-task test gate catches it — the one-shot qwen attempt budget then escalates the next attempt to Claude Sonnet.

### Over-claims completeness

Qwen narrates "all tests pass" or "implementation complete" in its final report without having actually run anything to verify it.

**Fix**: The per-task test gate at step 5.5 is the source of truth — qwen's self-report is never treated as a completion signal. Output that narrates actions instead of showing real tool calls (a `thought`/`<channel|>` block, a fabricated `$ pytest` run) is the visible symptom; the test gate is the backstop.

### Slow dispatch

Local inference is slow; a `qwen-run.sh` call can run for many minutes. The `use-qwen` skill prescribes background dispatch with `TaskOutput(task_id, block=true, timeout=600000)` (10-min wait; on a still-running return, re-issue the wait once, then treat a second timeout as a hang). `references/subagent-dispatch.md` documents the same 10-min × 2 watchdog pattern for qwen helper-script dispatches.

### Wrong model loaded

The llama.cpp server is running but serves a different model than `~/.pi/agent/models.json` declares.

**Fix**: The preflight's third check (`model_id_missing`) catches this. The task falls back to Claude at its original tier.

### Backend lists the model but can't serve it

`/v1/models` returns 200 with the model id, but a real completion returns `500 "failed to spawn server instance"` (or similar). LlamaBarn spawns the llama.cpp worker lazily on first completion; that spawn can fail (missing/broken runtime after an app auto-update, OOM, bad launch args) while enumeration keeps working straight from config. **2026-06-19 (playground PRD 00001):** checks 1-3 all passed → verdict `healthy` → task 1 routed to qwen → `qwen-run.sh` exited 1 on the 500, with no fallback gate to catch it.

**Fix**: the preflight's fourth check (`completion_failed`) catches this — a real 1-token completion is the only probe that exercises the worker spawn. The task falls back to Claude at its original tier. To restore qwen, fix the backend (LlamaBarn: re-download the model runtime or reinstall, then verify with a manual `curl ${baseUrl}/chat/completions`).

### Helper exits non-zero

`qwen-run.sh` returned a non-zero exit code.

**Fix**: Do not silently re-dispatch on qwen. The one-shot qwen attempt budget (see `SKILL.md` step 5.5) escalates the next attempt to Claude Sonnet — qwen failure consumes the attempt but does not consume a slot in the max-2 retry budget for the Claude Sonnet re-dispatches.
