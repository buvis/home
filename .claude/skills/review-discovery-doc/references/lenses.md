# Five-lens analysis (review-discovery-doc)

The five analysis lenses `review-discovery-doc` runs in Workflow step 3, with lens selection by depth and per-dimension resolution shapes. Three lenses look *inward* (the doc against itself and the template); two look *outward* (the doc against the problem, reality, and the future). Apply each against the discovery template's structure.

## Lens selection by depth

Run only the lenses the doc has material for; forcing an outward lens onto a thin doc manufactures strained findings. Depth-aware: a minimal-depth doc is not defective for omitting sections that only comprehensive depth requires.

- *Minimal:* the three inward lenses (Completeness, Coherence, Integrity) as full passes. Do not run Feasibility or Evolvability as systematic passes - there is too little scope to right-size or wall in. Safety valve: if a glaring lock-in or impossibility screams off a single line, still raise it.
- *Standard:* all five lenses as full passes.
- *Comprehensive:* all five, with Feasibility and Evolvability weighted hardest - the Approach section and the larger requirement set are where over-scope and one-way doors live.

## Completeness - is anything required missing?

Calibrate to declared depth:

- *All depths:* Problem stated and concrete? At least one Must-have? **Out of scope populated** (empty negative space is a real gap - it is where scope creep enters)? At least one Success Criterion? Discovery Log present (mandatory at every depth)?
- *Standard+:* Constraints, Codebase Context (with real file paths, not vague descriptions), Risks, Open Questions present?
- *Comprehensive:* Approach section with chosen option *and* rejected alternatives with reasons?
- Do not flag a section the declared depth does not require.

## Coherence - do the parts agree?

- Do any two requirements contradict each other?
- Does the Problem statement actually motivate each Must-have? (A requirement with no traceable pain point is scope creep or an unstated assumption.)
- Does every Success Criterion trace back to a requirement? (A criterion measuring something no requirement delivers is orphaned.)
- Does anything in Must-have belong in Out of scope, or vice versa?
- Do the Discovery Log answers actually support the requirements derived from them, or did a requirement drift from what the user said?

## Integrity - would this survive contact with implementation?

- Is each Success Criterion *falsifiable*? Flag vague qualifiers ("fast", "robust", "scalable", "intuitive") with no metric or threshold.
- Is each Must-have *testable* - could you write a test that fails if it's unmet?
- Are Constraints real constraints (externally imposed, non-negotiable) or smuggled-in preferences?
- Are Open Questions that block the build actually flagged as such, or buried?
- Is each requirement *singular*? Flag a Must-have that bundles several needs into one bullet ("must do X and Y and Z"); split it, or it cannot be traced, prioritised, or tested as a unit.
- Does any requirement state HOW instead of WHAT? Flag an implementation choice posing as a requirement ("store it in Postgres", "use a React modal"); discovery captures the need, the solution belongs to `design-solution`. When the smuggled-in choice is also a one-way door, it feeds Evolvability too.

## Coherence vs. Integrity (tie-breaker)

Both can claim a testability/measurability defect (e.g. "requirement R is untestable"). Route by the fix: if it edits a *single* element (a criterion says "fast" with no number) it is **Integrity**; if it adds or repairs a *link* between two elements (a fine requirement that no criterion covers) it is **Coherence**. One element → Integrity; a relationship → Coherence.

## Feasibility / right-sizing - does the scope fit the problem and reality?

This is the one outward-facing lens. Smell-test depth only - deep architecture feasibility is `review-design-doc`'s job later; here you kill the obviously over-scoped or impossible before it becomes a PRD.

- Is the Must-have set the *minimal* scope that solves the Problem, or is everything jammed into Must-have? (A 14-item Must-have list for a small convenience feature is the canonical defect - it passes Completeness, Coherence, and Integrity yet cascades into a bloated PRD.)
- Is any single Must-have so large it is really a separate feature that deserves its own discovery doc?
- Does any requirement assume something that does not exist (a service, dataset, or capability nobody has built)?
- Is the Problem big enough to justify the requirement count at all, or is this over-built for the pain described?
- Will this whole discovery become one right-sized PRD, or will it force a monster? `create-prd` splits a PRD at roughly 200 lines or at loosely-coupled seams, so if the Must-have set is clearly too large for one buildable PRD, flag it here and recommend splitting the *discovery itself* into focused docs (or marking it an epic with named slices). This is the whole-doc twin of the per-requirement right-sizing check above; the actual split still belongs to `create-prd`, this is only the early warning at the cheapest point to act.

## Evolvability - does any decision foreclose a future the solution will need?

The second outward lens, and the highest-leverage one: a one-way-door decision caught here costs a sentence to fix; caught after implementation it costs a redesign. Smell-test depth - deep architecture-reversibility analysis is `review-design-doc`'s job; here you flag the *requirement-level* decision that bakes in a corner, at its origin.

- Does any Must-have or Constraint encode a one-way door - a choice whose reversal later means redesign, not addition (a fixed data model, a single-tenant assumption, a specific vendor/format/protocol stated as a hard requirement instead of an extension point)?
- Does the requirement set assume a closed, fixed list where the Problem or domain implies it will grow - a hardcoded enum where an open registry is needed, with no extension seam?
- Does an Out-of-scope exclusion remove a seam that a foreseeable later requirement (including stated Nice-to-haves or Open Questions) will need, forcing rework to reintroduce it?
- **Discipline (guards against speculation).** Flag a lock-in only when a *named, foreseeable* evolution is blocked at redesign cost - evidence from the Problem, domain, Nice-to-haves, or Open Questions, never a hypothetical "what if". This lens pulls against Feasibility/right-sizing on purpose: right-sizing says don't over-build, evolvability says don't wall yourself in. Hold both - the resolution is almost always a cheap seam now, not a built-out feature now.

## Resolution shapes by dimension (illustrative, not literal labels)

- *Unmeasurable Success Criterion:* (1) rewrite with a concrete metric/threshold; (2) split into a measurable criterion plus move the aspiration to Nice-to-have; (3) add an Open Question to pin the metric during `create-prd`.
- *Two requirements contradict:* (1) drop/reword requirement A; (2) drop/reword requirement B; (3) add a Constraint that reconciles them.
- *Empty Out-of-scope:* (1) enumerate the obvious exclusions inferred from Problem + Must-have; (2) add the single highest-risk exclusion and flag the rest as an Open Question; (3) add an Assumption callout stating scope is bounded to the Must-have list.
- *Over-scoped Must-have:* (1) demote the non-essential items to Nice-to-have, leaving the minimal set that solves the Problem; (2) move the items that are really a separate feature to Out-of-scope with a note to spin off their own discovery doc; (3) split into a phase-1 Must-have and a deferred phase-2 list.
- *Discovery too big for one PRD:* (1) split the discovery into multiple focused discovery docs, each yielding a right-sized PRD; (2) keep one discovery but mark it an epic and name the PRD slices in Open Questions so `create-prd` splits cleanly; (3) trim the Must-have set to a phase-1 scope and move the rest to a follow-up discovery.
- *One-way-door decision:* (1) turn the baked-in choice into an extension point or open seam (a configurable registry instead of a fixed list); (2) reframe it as a default plus a documented extension path, keeping the door open; (3) add a Constraint or Open Question forcing `design-solution` to address the seam explicitly. ("Other" - accept the lock-in deliberately, recording why it is the right call.)
