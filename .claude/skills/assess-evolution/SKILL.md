---
name: assess-evolution
description: Assess a project's long-term evolution health, then emit a phased, session-sized PRD roadmap to get it back on track. Covers architecture, operational safety, security, downstream friction, simplification/librarization, and commit-history pain points, and names the top user-facing wins. Triggers on "evolution audit", "self-assessment", "assess this project", "get the project back on track", "what should we refactor", "health-check the codebase".
---

# Assess Evolution

A repeatable self-assessment that finds what blocks a project's healthy growth and turns it into a **phased, session-sized PRD roadmap** the team can execute. Built from a real multi-audit session; encodes what worked.

Core stance: **route deterministic work to code, the model to judgment** (git-log parsing is code; "is this churn a design flaw" is judgment). **Breadth via parallel read-only auditors, one per lens.** **Verify every load-bearing claim against source before asserting it** — an unverified finding is marked UNVERIFIED, never stated as fact. Calibrate: a healthy codebase under adversarial audit still yields localized, evidence-backed findings — thoroughness of the audit is not evidence of doom.

## 0. Catch up first, then load project config

**Live state first**: run the `catchup` skill (git-ferry plugin) before any lens work. Its output — branch diff, open PRs, open issues, CI health — steers direction: open PRs/issues join the already-tracked pointer auditors get in §2, failing CI and recent reverts are pain-point evidence for lens 7, and the §6 roadmap must sequence around in-flight PRs, not collide with them. No catchup skill? `gh pr list`, `gh issue list`, `gh run list --limit 20` cover the essentials.

Look for a project config the invoking skill or repo provides (a `.claude/evolution.md`, an `assess-*` project skill, or an AGENTS.md section). It supplies:
- **Downstream consumers**: name, repo path, how they consume this project (library dep, spawned binary, network API/transport, FFI), how they pin/version it. Keep this list extensible — new downstreams get appended.
- **Work-selection mechanism**: how the team's pipeline picks the next unit of work. THIS IS LOAD-BEARING for numbering (see §6). E.g. an autopilot that drains a backlog by *lowest sequence number* means the roadmap's numeric order must equal its execution order.
- **PRD/task conventions**: format, location, lifecycle folders.
- **Project shape**: languages, whether it exposes multiple interfaces/transports, security surface, release model.

No config? Infer these from the repo (README, AGENTS.md/CLAUDE.md, manifests, CI) and state what you assumed.

## 1. Scope the lenses to the project

Run the lenses that fit. A library has no transports; a CLI has no auth surface; a solo tool has no downstream. Default lens set:

1. **Architecture & growth-blockers** — layer violations (adapter types leaking into domain), god-objects/facades (count public methods), fat traits/interfaces, mutual coupling, test seams (can core logic be exercised with doubles?), size hotspots (largest files/functions), panics/`unwrap` on user-input paths.
2. **Operational safety** — concurrency (locks, races, multi-process/multi-writer), crash-consistency (partial-write windows, recovery on restart), data-loss classes, upgrade/migration safety, clock/ordering assumptions. This is where the worst, quietest bugs live.
3. **Security & robustness** — auth coverage per entrypoint, injection (SQL/query/template), path traversal, DoS/resource limits, untrusted-input parsing (one poisoned input bricking the system), secret/PII leakage.
4. **Interface/API cost-of-change** (multi-interface projects) — trace what one new field / verb / error code actually costs across every interface; find drift (the same result type exposing different fields per interface); find business policy living in adapters instead of the core.
5. **Downstream integration friction** — for each downstream, inventory the glue it wrote around this project and classify each item: **(a) generic plumbing** any consumer needs → upstream candidate; **(b) consumer-specific policy** → stays downstream; **(c) workaround for an upstream bug/gap** → upstream defect. Map upstream work → downstream LOC deleted (the deletion ledger).
6. **Simplification & librarization** — duplicated primitives (the same helper implemented twice, diverging), one-off reimplementations of things a shared helper/library should own, speculative abstractions with one implementation to delete, and clusters that multiple call sites (or multiple downstreams) reinvent and that should be extracted into a library/shared module. Pairs with lens 5: what downstreams reimplement is a librarization signal.
7. **Commit-history pain points** — mine the git log for design flaws that keep biting (see §3). Refactors that prevent a recurring bug class, not one-off fixes.
8. **Top user-facing wins** — the 3 improvements most likely to benefit the end user of the shipped product (see §4).

## 2. Execute — parallel read-only auditors

Dispatch one auditor agent per in-scope lens, **in a single batch**, all strictly read-only (no builds, no running the product's mutating commands, no touching downstream repos beyond reading). Give each:
- the lens's specific questions,
- the instruction to cite exact `file:line` evidence and to mark anything not confirmed by reading as UNVERIFIED,
- the instruction to return **conclusions, not file dumps** (keeps the orchestrator's context clean),
- a pointer to the existing backlog/roadmap so it separates **NEW** findings from **already-tracked** ones (reprioritize, don't rediscover).

Then **verify the load-bearing claims yourself** — read the exact cited code for anything that will drive a roadmap decision. Auditors (and your own briefs) will contain errors; catching them here is the point. Downgrade or drop what you can't confirm.

## 3. Commit-history pain-point method (lens 7)

Deterministic extraction (code), then judgment (model):
- **Churn**: files changed most often (`git log --format= --name-only | sort | uniq -c | sort -rn`) — high churn on non-generated code often means a design that resists change.
- **Fix clustering**: commits whose messages say fix/hotfix/revert/regression, grouped by the files they touch — a module that attracts repeated fixes has a structural flaw, not bad luck.
- **Fix-of-fix chains**: a fix commit shortly followed by another fix to the same lines — the first fix treated a symptom.
- **Co-change coupling**: files that keep changing together but live apart — a missing seam or a leaked abstraction.
Then judge: for each pattern, name the underlying design flaw and the refactor that removes the *class* of pain. Output "module X churns because Y; refactor to Z ends the recurrence," not a list of past fixes.

## 4. Top-3 user-facing wins method (lens 8)

Rank candidate improvements by **(user value) × (likelihood it actually lands and is adopted)**. Draw candidates from: the product's public surface and its rough edges, the downstream consumers' unmet needs (from lens 5 — what they work around is often what users feel), and user-visible signals in commits/issues (repeated bug areas, feature requests). Output exactly 3, each with the concrete user benefit and a one-line "what it takes." Keep it honest — these compete with the safety fixes for the same hands.

## 5. Synthesize the findings report

One ranked report. Each finding: **severity** (Critical/High/Med/Low) · **lens** · one-line defect · exact `file:line` evidence · one sentence on why it blocks growth / threatens stability / costs users · cheapest fix direction · **NEW vs already-tracked**. Include a short "what the architecture gets right" list so the team doesn't fix non-problems, and a "checked and safe" list so ruled-out hazards are visible. Mark UNVERIFIED explicitly (fail loud).

## 6. Emit a phased, session-sized PRD roadmap

Convert findings into PRDs, each scoped to **one implementation session** (split anything that bundles independent capabilities or needs cross-cutting regeneration; a decision/spike with no code is its own small PRD). For each PRD: problem + evidence, session-sized scope, explicit **dependencies**, and per-downstream impact.

**Number the PRDs to match the work-selection mechanism from §0.** If the pipeline runs the lowest number first, then numeric order MUST equal the dependency-and-priority execution order — emergency/data-loss first, then correctness, then leverage refactors, then enablement, then hygiene. Verify no PRD depends on a higher-numbered one. If the pipeline selects some other way (priority field, manual), encode order there instead. Getting this wrong means the pipeline does the wrong work first — check the mechanism, don't assume.

Group into phases: **P0 stop-the-bleeding** (data-loss/safety) → **P1 correctness/convergence** → **P2 leverage** (the refactor that makes everything after cheaper) → **P3 downstream enablement** → **hygiene**. Look for the *one root cause behind many findings* (a half-built abstraction, a missing seam) — finishing it is usually the highest-leverage phase.

## 7. Close the loop — guardrails + ledger

- **Guardrails**: encode the invariants that would have prevented the worst findings into the always-loaded agent instructions (AGENTS.md/CLAUDE.md) plus a developer-facing doc, honest about which invariants currently hold vs are gaps with a tracking PRD. This is what stops recurrence.
- **Downstream deletion ledger**: table of upstream PRD → downstream LOC/complexity it deletes. This is the measurable "we're paying down the tax" signal.
- **Memory**: record the root-cause insight and any load-bearing gotcha for future sessions.

## Outputs

1. A findings report (working doc).
2. The phased PRD set in the project's backlog, numbered for its pipeline.
3. A roadmap/index doc that is the ordering authority.
4. Guardrail edits (AGENTS.md/CLAUDE.md + a doc).
5. A downstream deletion ledger and the top-3 user wins.

Scale effort to the ask: a quick check runs a few lenses inline; "be thorough / get us back on track" runs the full parallel battery with adversarial verification.
