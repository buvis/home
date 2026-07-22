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
| `fable` | Claude Fable | **ACTIVE (human-gated)** — entered only through the rescue gate (§ Fable rescue): one dispatch per PRD, ever, and only after a human approves. Never a session model, never selected autonomously. |

Order: qwen -> codex -> claude haiku/sonnet/opus -> fable. The last edge is the
only one no skill may take on its own: `opus` exhaustion does not escalate to
`fable`, it stops at the human-gated rescue (§ Fable rescue).

## Tier -> backend map

| Tier | Backend |
|------|---------|
| `haiku` | Claude Haiku |
| `sonnet` | Claude Sonnet |
| `opus` | Claude Opus |
| `fable` | Claude Fable — reachable only via the rescue gate, never by the plan-tasks classifier |

`qwen` is the local backend used for qwen-eligible backend tasks at haiku/sonnet
tier. It is not a tier of its own.

The INITIAL tier authority is plan-tasks step 4.7's classifier (the
`qwen_eligible` formula plus the `default_model` floor). This file cites that
classifier; it does not re-derive it.

## Per-rung budgets

| Rung(s) | Budget |
|---------|--------|
| Claude rungs (haiku / sonnet / opus) | **2 dispatches**: initial + one feedback retry. The 2nd gate failure at a rung triggers diagnosis. |
| qwen | **1 dispatch per task**: no same-tier feedback retry. A qwen gate failure escalates immediately (this is the qwen one-shot-per-task budget; the Capability ladders section below names it the `qwen -> sonnet` edge). Scoped per task, not per PRD or per batch — every qwen-eligible task gets its own independent one-shot budget. |
| `fable` | **1 capability dispatch per PRD, ever**: no same-tier feedback retry, no repair. An *infra* failure (watchdog / lost result) still falls back at the same tier per § Infra vs capability — infra is not a capability attempt. Scoped per PRD, not per task: one approved rescue buys one Fable attempt for the whole PRD. |
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
machinery (PRD 00017), through the Fable rescue gate (§ Fable rescue) on the
way. No new halt class. A `fable` attempt has **no rung above it**: its gate
failure goes straight to the same exhaustion path, never to an escalation.

## Fable rescue

The `opus -> fable` edge is a human gate, not a ladder step. In ladder terms:

- Exhaustion at `opus` records a rescue **request** for the PRD — one per PRD,
  ever. A PRD that already has an entry (`requested`, `approved`, `rejected`,
  or `consumed`) never gets a second one.
- A human decides it out of band: `autoclaude approve-fable <prd>` (or
  `autoclaude reject-fable <prd>`).
- The next exhaustion for that PRD spends the approval on exactly one
  Fable-tier dispatch, and the entry flips to `consumed` regardless of
  outcome. A failed Fable attempt therefore stalls the PRD normally, with no
  new request.

The ledger that holds those states is `references/state-schema.md` § Fable
rescue ledger. The procedure — when the gate runs, in what order it writes,
and what each `fablectl` exit means — lives in `references/recovery.md`
§ "Rework escalation exhausted" and is not restated here.

## Infra vs capability

- An **infra** failure (qwen preflight failure, subagent watchdog timeout /
  lost result) is NOT a capability failure: it falls back at the SAME tier,
  never increments the qwen capability breaker, never enters diagnosis.
  (Existing behavior, unchanged.)
- A **capability** failure (a real test-gate failure) escalates UP the
  capability ladder, after diagnosis.

## Memory gate

`/work` step 3 routing row 4 (`work/SKILL.md`) reroutes a qwen-eligible task
to Claude at its original tier when the host is short on RAM, via:

    python3 ~/.claude/skills/work/scripts/check_memory_pressure.py --max-level <threshold>

**Threshold: `1`** — the highest `kern.memorystatus_vm_pressure_level` the
script still calls healthy (its own Python default, mirrored here because the
ladder is this file's single source of the number). The script compares
`level <= max_level`: exit 0 = headroom OK, exit 1 = under pressure, exit 2 =
probe failed. A non-zero exit reroutes the task and stamps the attempt
`qwen_excluded_reason` — `memory_pressure` on exit 1, `memory_probe_failed` on
exit 2 (`state-schema.md` `tasks[].attempts`).

**Reads pressure level, not headroom:** PRD 00075 says the gate reads RAM
headroom from host memory stats. The script actually reads
`kern.memorystatus_vm_pressure_level`, the kernel's pressure notification
level (1 normal, 2 warning, 4 critical), not computed free RAM. Deliberate:
it reuses the signal the autoclaude wrapper's memory circuit breaker already
trusts (`~/.config/bash/plugins/development.plugin.bash`), one definition of
pressure on this host instead of two. Tradeoff: it lags true headroom, only
rising once the kernel is already compressing and swapping, a coarse stop.

**Unmeasured under load:** `1` was set by symmetry with the autoclaude
wrapper's memory circuit breaker, not by measurement with a qwen server
resident. If a loaded server holds the pressure level at 2, routing row 4
fires on every qwen-eligible task forever, a silent permanent qwen-off
switch, the opposite of this gate's intent. To close this, next time a
llama-server is up, run `sysctl -n kern.memorystatus_vm_pressure_level`: a
reading of 1 confirms the threshold, 2 or higher means it must be raised or
the gate rethought.

**Revert needs no new env knob:** raise this threshold to `4` (the maximum
level macOS reports) and the gate's exit 1 verdict, the pressure check, can
never fire, since the comparison is `<=`. Raising the threshold does not
touch exit 2, the probe-failure verdict: when the sysctl can't be read or
parsed, the script exits 2 no matter what `--max-level` is set to, and the
task still reroutes off qwen. There is no env knob for that path. The actual
remedy is to fix the probe (make `kern.memorystatus_vm_pressure_level`
readable again) or mark the affected tasks `qwen_eligible: false` so routing
never reaches row 4. This works ONLY because the routing row reads
`--max-level` from this section explicitly, at dispatch time.

**Not guarded by `_AUTOPILOT_ESCALATION`** (unlike the qwen capability
breaker below): this is a host-safety mechanism, not a quality mechanism, and
keeps firing even under `_AUTOPILOT_ESCALATION=legacy`.

## Ordering

There are TWO separately-scoped orderings, NOT one single linear chain:

1. **Routing-time order** (per task, at implementor selection): qwen breaker
   consult -> memory-pressure gate -> qwen infra preflight -> dispatch. A
   tripped breaker short-circuits before the memory-pressure gate and the
   preflight; a memory-pressure gate fire short-circuits before the
   preflight.
2. **Failure-classification rule** (at the gate, or on a lost result): infra
   failure -> fall back same tier; capability failure -> diagnose, where
   **repair precedes escalate**.

Do NOT collapse these into a single `infra > breaker > repair > escalate`
chain. They are scoped to different moments.

## Kill-switches

- `_AUTOPILOT_ESCALATION=legacy`: read by `/work` step 5.5. When set to
  `legacy`, skips diagnosis, repair, escalation, attribution stamping, AND the
  qwen capability breaker; the escalation machinery becomes byte-identical to
  pre-00065 (today's same-tier "max 2 implementation retries" cap). The
  memory-pressure gate (routing row 4) is not disabled by this knob and keeps
  firing under `legacy` (see § Memory gate). The qwen one-shot carve-out (qwen
  fail -> Claude Sonnet) still applies. Any other value or absent -> the new
  flow.
- `_PLAN_TASKS_FLOOR=legacy` (alias: `sonnet`): read by `/plan-tasks`,
  plan-time only — no `/work` dispatch-time effect. Currently a documented
  no-op: the classifier rule-widening this knob was built to revert was
  withdrawn after review, so the `legacy` row and the current row of the
  step 4.7 tier classifier are identical — setting it changes nothing today.
  Any other value or absent -> the same (unchanged) classifier row.
- `_AUTOPILOT_MODEL_BUILD=<model>`: the pre-existing env override, and the
  sonnet-first kill-switch (PRD 00076). Setting it forces every build launch
  to that model regardless of promotion signals.
- The Fable rescue has **no env knob**. It is gated by human approval
  (`autoclaude approve-fable <prd>`), one request per PRD ever, and `fable` is
  never a session model (§ Fable rescue).
- Reserved (declared by future PRDs, env var names TBD by each): a codex-rung
  activation knob (PRD 00077), a decay knob (PRD 00078).

## Decay

No decay rules yet. PRD 00078 defines them.
