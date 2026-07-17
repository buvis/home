# Model-Escalation Ladder

This file declares the escalation ladder for `/work`: every rung, budget, and
switch that governs which backend runs a task and when it escalates.
Consumers (`plan-tasks`, `work`, `phase-review`) cite this file instead of
restating it. Every number appears exactly once, here.

## Rungs

Lowest to highest:

| Rung | Backend | Activation status |
|------|---------|--------------------|
| `qwen` | local llama.cpp backend | **ACTIVE** |
| `codex` | Codex CLI | **DECLARED-INACTIVE** (activated by PRD 00077) |
| `claude-haiku` | Claude Haiku | **ACTIVE** |
| `claude-sonnet` | Claude Sonnet | **ACTIVE** |
| `claude-opus` | Claude Opus | **ACTIVE** |
| `Fable` | human-gated | **DECLARED-GATED** (activated by PRD 00076) |

Order: qwen -> codex -> claude haiku/sonnet/opus -> human-gated Fable.

## Tier -> backend map

| Tier | Backend |
|------|---------|
| `haiku` | Claude Haiku |
| `sonnet` | Claude Sonnet |
| `opus` | Claude Opus |

`qwen` is the local backend used for qwen-eligible backend tasks at haiku/sonnet
tier. It is not a tier of its own.

The INITIAL tier authority is plan-tasks step 4.7's classifier (the
`qwen_eligible` formula plus the `default_model` floor). This file cites that
classifier; it does not re-derive it.

## Per-rung budgets

| Rung(s) | Budget |
|---------|--------|
| Claude rungs (haiku / sonnet / opus) | **2 dispatches**: initial + one feedback retry. The 2nd gate failure at a rung triggers diagnosis. |
| qwen | **1 dispatch**: no same-tier feedback retry. A qwen gate failure escalates immediately (this is the qwen one-shot budget; the Capability ladders section below names it the `qwen -> sonnet` edge). |
| Repair | **At most 1 per task, total** (Claude rungs only; qwen never gets a repair). |

Worst-case examples:

- A qwen-eligible `sonnet` task: qwen (1 fail -> escalate) -> Sonnet (2
  dispatches, +1 possible repair) -> Opus (2 dispatches) -> opus exhaustion.
- A non-qwen `haiku` task: haiku (2 dispatches +1 repair) -> sonnet (2
  dispatches) -> opus (2 dispatches) -> exhaustion.

## Capability ladders

- `qwen -> sonnet` (skips haiku)
- `haiku -> sonnet -> opus`

Opus-rung exhaustion (2 failures at opus) flows into the existing abort/stall
machinery (PRD 00017). No new halt class. PRD 00076's Fable rescue hooks that
seam later.

## Infra vs capability

- An **infra** failure (qwen preflight failure, subagent watchdog timeout /
  lost result) is NOT a capability failure: it falls back at the SAME tier,
  never increments the qwen capability breaker, never enters diagnosis.
  (Existing behavior, unchanged.)
- A **capability** failure (a real test-gate failure) escalates UP the
  capability ladder, after diagnosis.

## Ordering

There are TWO separately-scoped orderings, NOT one single linear chain:

1. **Routing-time order** (per task, at implementor selection): qwen breaker
   consult -> qwen infra preflight -> dispatch. A tripped breaker
   short-circuits before the preflight.
2. **Failure-classification rule** (at the gate, or on a lost result): infra
   failure -> fall back same tier; capability failure -> diagnose, where
   **repair precedes escalate**.

Do NOT collapse these into a single `infra > breaker > repair > escalate`
chain. They are scoped to different moments.

## Kill-switches

- `_AUTOPILOT_ESCALATION=legacy`: read by `/work` step 5.5. When set to
  `legacy`, skips diagnosis, repair, escalation, attribution stamping, AND the
  qwen capability breaker; the flow becomes byte-identical to pre-00065
  (today's same-tier "max 2 implementation retries" cap). The qwen one-shot
  carve-out (qwen fail -> Claude Sonnet) still applies. Any other value or
  absent -> the new flow.
- Reserved (declared by future PRDs, env var names TBD by each): a
  sonnet-first + Fable-rescue knob (PRD 00076), a codex-rung activation knob
  (PRD 00077), a decay knob (PRD 00078).

## Decay

No decay rules yet. PRD 00078 defines them.
