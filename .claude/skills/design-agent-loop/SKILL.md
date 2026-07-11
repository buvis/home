---
name: design-agent-loop
description: Use when designing a goal-oriented agent loop or reviewing one for runaway risk - build gate, machine-decidable goal, anti-Goodhart boundaries, five failure modes. Triggers on "design a loop", "review this loop", "will this loop run away".
metadata:
  origin: ECC (loop-design-check)
---

# Design Agent Loop

> **Premise.** An LLM is feed-forward: prompt in, tokens out, with no built-in "steer toward the goal" across turns. To make it behave like a goal-oriented system you wrap a feedback loop around it. This skill helps you **write** that loop correctly and **review** it so it won't run away.

## When to use / not

**Use it when:**

- You want to hand a repeating task to an agent that runs over and over (write→test, test→fix, fix→verify...).
- You already have a loop and worry it spins, cheats, or runs a wrong answer to completion.

**Don't use it for:**

- A one-off task: just do it; don't wrap a loop around it.
- A plain timer or poll: use `/loop`; no design needed.
- Wiring the loop architecture itself: that's the mechanism layer (`/loop`, `/schedule`, `run-autopilot`). This skill covers only "is the goal right, and will it run away".

## Red-line premise: two levels of feedback

| Level | Who owns it | What it does |
|---|---|---|
| **Execution** (low) | machine / agent | Measures "how far from the literal goal" and grinds it to zero. The machine is strong here. |
| **Judgment** (high) | **human** | Decides "is this goal itself right, should it change, should it stop." The machine can't step outside its own loop to question the goal. |

> A thermostat can feed back "how far from 26°C", but when you have a fever and want 28°C it can't judge whether 26 is the right target. "What to set today" is always the human's call. Handing judgment, sign-off, or the last switch to the machine removes the high-level feedback: it sprints, fast and hard, toward a goal no one questioned.

## Action 1 - Write a loop (5 steps)

### Step 0 · Subtract first: should it exist? (4-condition gate, any miss = veto)

1. The task repeats weekly or more.
2. Verification can be automated.
3. The token budget can take it.
4. The agent has tools that actually run and see the result.

Miss any one → don't build a loop; do it by hand or another way.

> A repo that deserves a loop has a reconciliation baseline (golden sample, upstream total), tests, and a lint guard. A repo without them will only have its errors amplified by one.

### Step 1 · Define a machine-decidable goal (the loop lives or dies here)

The whole loop rides on the comparator's "is it done yet?". The exit condition must be judgeable yes/no by a machine.

- Bad: vague ("make it good", "write it sharper"). The comparator can't judge, so it either never passes (stuck retrying) or guesses (passes/blocks at random).
- Good: decidable ("all 96 unit tests green AND a change-list produced", "module-02 fields filled, pytest passes, business logic untouched"). One check settles it; the loop converges.

**Five-point goal framework:**

1. **Done-criterion is machine-verifiable.**
2. **Boundary conditions defined alongside it** ("what it must NOT do"). Missing boundaries = a license to cheat (Goodhart).
3. **Failure fallback**: retry cap N, escalate to a human when exceeded.
4. **Goal is layered.**
5. **Prefer reconciliation over assertion**: anchor to external fact (golden sample, upstream total, financial tie-out) before your own assertions. "All tests pass" can be gamed (loosen asserts, fake mocks, swallow exceptions); "diff vs the reference < 0.01" can't.

> Self-check: could someone who doesn't know the domain run one command and tell whether it's done? If not, it isn't decidable enough. Go back.

### Step 2 · Pick the loop type

| Your task | Loop type | How it stops |
|---|---|---|
| Clear "done" test (write to done, a batch processed) | **servo** (closed loop; autopilot-style run) | stops on reaching the goal |
| No endpoint, keep maintaining a state (inventory alert, scheduled health check) | **regulator** (`/loop` thermostat) | never stops; acts only on change (dead-band suppresses noise) |
| Periodic sampling, stop on a condition (watch a PR until CI is green) | **regulator with an exit** | stops when the exit condition holds |
| Must happen on time | wrap the above in `/schedule` | cron fires it |

> Rule of thumb: clear "done" test → servo; keep maintaining, no endpoint → regulator; must happen on time → wrap a regulator in schedule.

### Step 3 · Pick a skeleton

**Maintenance type (tend something that exists) → document-driven dispatch.** The loop isn't "run a fixed check on a timer"; it's "read a doc on a timer, dispatch only when the doc changed." The doc is the task queue, state machine, and human interface. Three disciplines: (1) the problem column is human-write-only, the result column is loop-write-only, state advances one-way and never rolls back; (2) the exit code is final (if the script says exit 1, the script wins); (3) state advances only to "awaiting verification". The "done" cell is flipped by a human only. The loop is the worker, not the acceptance officer.

**Greenfield type (build from scratch) → plan / build / judge, three roles.**

| Role | Does | Key |
|---|---|---|
| **Plan** | break the goal into a spec + decidable acceptance conditions | acceptance must be script-judgeable |
| **Build** | write to the spec | must not change the acceptance conditions |
| **Judge** | run acceptance independently; pass → stop, fail → return with the failure reason to Build | independent + deterministic |

Three iron rules (all bet on the judge): (1) the judge must be independent, never the same agent as Build (grading your own homework always inflates); (2) deterministic rules (pytest, reconciliation diff, type check, diff), never "looks right"; (3) Build may not edit the acceptance conditions to pass. Three failed retries → escalate to a human.

### Step 4 · Add damping (against oscillation and runaway)

Retry cap, hard stop, human flips the last switch. Negative feedback with no damping oscillates: spinning in place, burning tokens.

### Step 5 · Land in three stages (don't go fully automatic on day one)

(1) Run it once by hand (forces you to state exactly how the judge decides) → (2) harden into a skill or subagent dispatch (a main session loops, dispatching plan/build/judge) → (3) hang it on `/schedule` for full automation.

## Action 2 - Review a loop (checklist = five failure modes)

> Run the loop past each row. Hitting any one = this loop will misfire; send it back.

| # | Failure mode (how it breaks) | Review question (a hit = red) | Antibody |
|---|---|---|---|
| 1 | Goal is a correct platitude → spins, burns money | Can the exit condition be machine-judged yes/no? Or is it "manage it well"? | Replace with a decidable result condition (Action 1 · Step 1) |
| 2 | "Verification" written as "check if it looks ok" → agent confidently says fine and stops | Is the judge the defendant itself? Does verification rest on "looks right" or deterministic rules? | Reconcile + exit-code rules + independent judge |
| 3 | (worst) Only gates on "all tests pass" → agent deletes the tests | Is there a boundary ("what it must NOT do")? Or only a done-criterion? | Done-criterion **+ boundary** together (the Goodhart antibody) |
| 4 | Counts on the agent asking mid-run → it won't; it runs the wrong answer to the end | Is there any "clarify only at runtime" point? | Front-load every clarification; settle it once before launch |
| 5 | Bloated CLAUDE.md + stale memory → the faster it loops, the more it errs | Are the docs/memory it depends on fresh? Who maintains them? | Layered memory + periodic lint |

**Plus three red lines (violate any = not allowed to go automatic):**

- **Keep judgment with the human.** Acceptance / the "done" cell is flipped by a human; the loop is not the acceptance officer.
- **Responsibility doesn't transfer.** Anything whose failure you can't afford (merge the wrong PR, publish the wrong thing, misallocate money) → don't hand over the authority automatically.
- **Counter-intuitive warning.** The more "self-improving / rewrites-its-own-rules" a loop is, the stricter the human review it needs, not looser. The machine is too fast to intercept after the fact, so the human's judgment must sit before the action (a hard gate), not as a post-hoc patch.

## Worked example - reviewing a "nightly green-keeper" loop

You want a loop that runs every night and fixes whatever tests are failing.

- **Naive goal:** "make all tests pass." Step-1 self-check fails: this is the bait for failure mode #3.
- **Decidable goal (fixed):** "all tests green AND no test file deleted or weakened AND coverage not lowered AND a change-list produced." Boundary now sits beside the done-criterion.
- **Type:** servo with a retry cap of 3 (Step 2 + Step 4).
- **Skeleton:** plan/build/judge; the judge is CI run independently, never the fixing agent (Step 3).

Run the review checklist and it catches what the naive version would have missed:

- **#3 hit** → the naive "all tests pass" lets the agent delete a failing test to "win." Fixed by the boundary "no test file deleted/weakened."
- **#2 hit** → if the fixing agent also judged its own fix, it would pass itself. Fixed by "judge = independent CI, deterministic."
- **#4 hit** → if a fix is ambiguous, the agent won't stop to ask at 2 a.m.; it'll commit a guess. Fixed by front-loading: ambiguous fixes are left for the human, not guessed.
- **Red line** → the loop opens a PR but does not auto-merge; the human flips the last switch.

The naive loop and the reviewed loop differ by four lines of constraint. That's the difference between "wakes you to a deleted test suite" and "wakes you to a clean PR."

## One-line close

> The hard part of writing a loop isn't "can I write a loop"; it's defining a goal a machine can reconcile: decidable, bounded, reconciliation-based. The controller must be deterministic and external; keep judgment and the standard with the human. A loop only rewards someone who has already thought it through. Count on it to think for you, and it will happily think wrong, with you, at scale.

Mechanism layer (wiring, scheduling, recovery): `/loop`, `/schedule`, `run-autopilot`. This skill covers goal definition and runaway prevention only.
