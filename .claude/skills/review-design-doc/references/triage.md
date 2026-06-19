# Triage: tiers and signals

Match review depth to document stakes. Running every technique on every doc is the framework's most common failure mode (review fatigue, ignored findings). Pick a tier based on doc maturity, then add techniques driven by signals you observe in the doc.

**Tier selection is mechanical**: check Tier 3 conditions first; if any apply, the review is Tier 3. Otherwise check Tier 2 conditions; if any apply, it is Tier 2. Otherwise Tier 1. The asymmetry (Tier 1 needs none-of-the-above; Tier 2 and 3 need any-of-the-conditions) is intentional: Tier 1 is the safety floor and requires confirming the doc is low-stakes; higher tiers escalate on any single high-stakes signal.

**Thresholds below are calibrated defaults** (pages, months, multiplier). They are starting points, not derived from data; tune per team if your context warrants. Reasoning behind each is noted in parentheses.

## Tier 1: Quick (15 to 30 minutes)

Apply when **none** of the Tier 2 or Tier 3 conditions hold. By definition, the doc then satisfies all of:
- Length: fewer than 5 pages (~10 min read at 200 wpm, matching the Tier 1 budget)
- Audience: internal team only, no external consumers
- Persistence: no new persistent state introduced, OR all introduced state is fully reversible by re-running a script
- Lifetime: prototype, spike, or short-lived feature (expected lifetime <6 months — below this, operational debt is contained)

If you cannot confirm all of the above, default up. Also use Tier 1 for self-review before submitting to an external reviewer (lighter pass to catch your own gaps).

Run:
- Standard checklist (skim, verdict-only per section)
- Cardinal sins (full check)
- Premortem (one paragraph)

## Tier 2: Standard (1 to 2 hours)

Apply when **any** of these conditions hold:
- The design touches a persistent store (database, cache with TTL >1 day, blob storage, message queue with retention) — state changes are not trivially reversible
- The design has >1 downstream consumer (other services, teams, or external clients) — coordination cost rises with each consumer
- A rollback procedure is required to undo it safely (i.e., the rollback is not "revert the commit") — non-trivial undo means non-trivial risk
- The design affects users or systems outside the owning team — failure modes leak across team boundaries
- The design is expected to live >6 months in production (long enough to accumulate operational dependencies and downstream assumptions)

Run Tier 1, plus:
- Advanced review techniques (all)
- Stress tests (all 10)
- Anti-pattern detection (all 14)

## Tier 3: Deep (half-day or more)

Apply when **any** of these conditions hold:
- The design affects shared infrastructure used by ≥3 teams (2 teams can coordinate informally; 3+ requires structural agreement)
- The design commits to a vendor for ≥12 months, or introduces vendor lock-in (data formats, proprietary APIs, custom contracts) — annual budget cycles make 12-month commitments structurally hard to exit
- The design introduces or modifies compliance scope (PII, PHI, PCI, SOX, HIPAA, GDPR, or local-equivalent) — legal exposure dominates ordinary engineering tradeoffs
- The design requires explicit coordination across ≥2 teams to ship
- The design's failure cost (lost revenue, lost users, legal exposure, brand damage) exceeds 10x its development cost (asymmetric-risk threshold: when downside is order-of-magnitude larger than upside)
- The design changes a public API contract, or any contract consumed by parties outside the company — external contracts are one-way doors

Run Tier 2, plus:
- Philosophical lenses (all 8)
- Persona walkthroughs (every applicable persona)
- Counterfactual constraints (full set)

## Signal-driven additions

Within any tier, add these techniques when the doc shows the matching signal. Read the doc once for signals before choosing your technique stack:

- Vague qualifiers ("scalable", "robust", "fast", "secure") → claim ladder (part of Probing reasoning)
- Binary decisions framed as forced choices → Buddhist tetralemma
- Many "we will" statements without commitment criteria → decision-vs-direction check (in Ground rules)
- Authority appeals ("FAANG uses it", "industry standard") → cognitive bias scan
- Multiple stakeholders with potentially divergent needs → persona walkthrough + Jain anekantavada
- Long horizon or persistent data → time-horizon walkthrough
- Compressed assertions about future load or scale → falsifiability check
- High blast radius or one-way-door decisions → premortem + asymmetric risk audit
- Sloppy or shifting terminology → Confucian rectification of names
- Numerical commitments without methodology → falsifiability check
- Lots of architecture, little user outcome → Aristotelian four causes (focus on final cause)
- Acclaimed inevitability ("we have to do X") → "what if we are wrong about the problem itself?"
- Visible depth imbalance between sections (one section a manifesto while another is a sentence) → Section weight audit

## Tier upgrade during review

If during a review you discover signals that suggest higher stakes than the initial tier assumed, upgrade the tier and continue from the new tier's baseline. Document the tier change and the triggering signal in the resolution log Summary, in the form "Upgraded Tier 1 → Tier 2 because <observable condition discovered>."

Common upgrade triggers (any one of these escalates to the next tier):
- Persistent data discovered to be touched but not mentioned in the doc
- Cross-team coordination implied by the design but not acknowledged in the doc
- Vendor commitment or lock-in emerging from architectural choices
- Compliance scope (PII, PHI, financial, healthcare) discovered mid-review
- Reversibility that was framed as reversible but is, on inspection, one-way

**Default-up rule for tier disagreement**: when the reviewer and the author disagree on the appropriate tier, default to the higher tier. The asymmetric cost of under-reviewing a high-stakes doc dwarfs the cost of over-reviewing a low-stakes one. The disagreement itself is a finding about the doc's stake assessment and should be recorded.
