# Advanced review techniques


Apply these alongside the standard checklist. They catch systemic issues that section-by-section reviews miss. Use judgement: not every technique fits every doc, but the higher the stakes, the more of these you should run.

### Probing reasoning
For load-bearing claims, walk back through the reasoning rather than asserting the conclusion is wrong. Three **distinct** moves, each catching a different gap. Pick the move that matches the gap, not the move you like most:

- **Socratic questioning** probes for hidden assumptions and produces information in either direction; use when you suspect a gap but are not certain the author missed something.
- **Five-whys descent** traces a load-bearing claim back to its bedrock; use when a claim feels load-bearing but you cannot tell whether it rests on evidence or habit.
- **Claim ladder** tests vocabulary against measurement; use when the doc uses compressed qualifiers ("scalable", "secure", "fast") without defining them.

#### Socratic questioning
Six question types, each with a design-doc bite:
- *Clarification*: "What exactly do you mean by 'X'?" / "Can you give a concrete example?" / "How does this relate to <other concept>?"
- *Assumption probes*: "What are you assuming?" / "How would we know if that assumption is wrong?"
- *Evidence probes*: "What is the evidence for this claim?" / "Has this been measured, or is it intuition?"
- *Viewpoint probes*: "What is the strongest argument against this approach?" / "Why didn't you choose <obvious alternative>?"
- *Implication probes*: "If this is true, what else must be true?" / "What does this commit us to in 2 years?"
- *Meta-questions*: "Why does this section matter?" / "What are we avoiding talking about?"

A well-formed question yields information either way; a confident assertion only yields defense. Contrast:
- *Assertive*: "The 50ms p99 latency budget is unrealistic with Postgres."
- *Socratic*: "The doc commits to 50ms p99. Has this been measured against the actual Postgres setup, or is it estimated?"

Use Socratic mode when you suspect a gap but are not certain; use assertion when you have evidence.

#### Five-whys descent
For each load-bearing claim, ask "why?" five times. The chain ends at one of:
- *Bedrock* (real constraint, validated evidence, external commitment): sound
- *Unvalidated assumption*: flag and request validation
- *Inherited belief* from another team or industry meme: flag, ask whether it still applies
- *Habit or preference*: flag
- *Authority deference* ("FAANG does it this way"): flag, ask whether the analogy holds at this scale

If a chain bottoms at "that is just how we do it" or "nobody remembers", the load-bearing assumption is unmoored and should be re-derived from current constraints.

#### Claim ladder
Take each compressed assertion ("scalable", "resilient", "secure", "fast", "modular", "robust") and ascend:
- What concrete behavior would I observe in a system that is X?
- What measurement distinguishes "yes" from "no"?
- What is the doc's commitment on that measurement?

If an assertion does not survive the ladder, it is a vocabulary placeholder, not a design decision.

### Premortem
Imagine it is 18 months later and this project failed. Write a 4 to 6 sentence "failure obituary" naming the most plausible failure mode (not the one the doc anticipates, the one it waves away). Then check: does the doc actually mitigate that failure mode, or just acknowledge it?

For shorter horizons (6 months), the same exercise becomes a "regret interview": what would you most likely regret at the first postmortem? Regret is often better-calibrated than risk analysis because it imagines specific lived consequences.

### Inverse problem
Reverse-engineer from the architecture: what problem is this design actually optimized for? Compare to the stated problem. They often diverge. Designs get optimized for team preference, future flexibility, vendor relationships, headcount justification, or perceived prestige rather than the named need.

### Cognitive bias scan
Audit explicitly for these biases, with citations where you suspect them:
- **Sunk cost**: chosen because someone already started building it?
- **Confirmation**: only listed alternatives the author wanted to reject?
- **Availability**: chose familiar tech without weighing unfamiliar options?
- **Authority**: "FAANG uses it" or "industry standard" without proving applicability to this scale and context?
- **Anchoring**: timeline anchored to an imposed deadline without bottom-up estimation?
- **Planning fallacy**: estimates without buffer for unknowns?
- **Curse of knowledge**: assumes context only the author has?
- **IKEA effect**: author too attached to the design to evaluate alternatives objectively?
- **Bikeshedding**: doc spends disproportionate detail on a low-stakes decision?

### Negative space audit
Catalog what a competent design doc would typically address that this one does not. Silences are where the worst problems hide. Specifically check: per-dependency failure modes, operating burden, vendor exit strategy, cost at projected scale, data deletion path, time-zone and locale handling, boundary cases (empty, max, negative, unicode, very long strings, very large counts).

### Conway's law check
Map proposed component boundaries against the org chart. Are component boundaries actually team boundaries in disguise? Is the architecture solving a coordination problem rather than a technical one? If so, is that intentional and acknowledged, or accidental?

### Hidden coupling map
Two components drawn as separate boxes can still be coupled by: shared database tables, shared SDK or library versions, shared deployment cadence, shared on-call rotation, shared kill switch, shared infrastructure quota, shared release train, shared incident response. List every implicit coupling and ask whether it is intentional.

### Falsifiability check
For every claim in the doc, ask: what observation would prove this wrong? Claims that cannot be wrong cannot be right. "Highly available" is unfalsifiable; "99.95% monthly uptime measured by external probes against the public endpoint" is. Flag every unfalsifiable claim that pretends to be a commitment. Numerical precision without a measurement methodology (e.g., "system will handle 4,238 RPS") is false confidence; demand the methodology or accept appropriate uncertainty bands.

### Compression test
What is the load-bearing 10% of the doc? If forced to compress to a single page, what survives? If 90% of the doc is not load-bearing, the design is still in exploration, not decision. State which sections are load-bearing; the rest is ornamentation. Apply the telephone-game variant: if a 2-page summary led another team to build the system, would they build the same thing? If not, the design lives in tacit context, not in the doc.

### Section weight audit
A targeted check for internal balance. For each top-level section of the doc, measure its weight (word count, or bullet count if the doc is mostly bulleted). Compute the median weight across sections. Then:

- **Heavy outliers** (>3x median weight): potential over-detail. Ask: does this section's importance justify its depth, or is it where the author had a lot to say independent of how much weight the topic warrants?
- **Light outliers** (<1/3 median weight): potential under-detail. Ask: is this section brief because the topic is genuinely low-stakes, or because the author rushed past a hard concern?

A doc with one or two heavy outliers is normal (some sections genuinely matter more). A doc with **many outliers**, or with a **critical section as a light outlier**, is structurally unbalanced and warrants a finding. The fix is either to rebalance the depth or to make the importance asymmetry explicit (e.g., "Section X is intentionally brief because Y is a settled non-issue; Section Z is deep because it is the load-bearing decision").

**Audit at the right level**: if a top-level section is a container of multiple parallel sub-sections (e.g., a "Checklist" with N items, an "Endpoints" section listing N endpoints, a "Techniques" section listing N techniques each at comparable depth), the container's top-level weight is structural, not imbalanced. Audit at the sub-section level in that case. Balance is a per-level property, not a flat one.

**Exclude code blocks**: when counting with naive tools (`wc`, `awk`, regex), strip fenced code blocks first. Headings inside code blocks (` ```\n## Example\n``` `) are illustrative content, not document structure; counting them as sections produces false splits and wrong weights.

Run this audit even when the doc reads smoothly. Smooth-reading docs often have hidden depth imbalances that only an inventory surfaces; the reader's attention follows the depth, not the importance, so the rushed sections slip past unchecked. The cost is low (one pass with a word counter or bullet count); the catch rate for structural issues is high.

### Surprise check
Where does the doc tell you something you could not have predicted from the title and problem statement alone? That is where the real design lives. A doc with no surprises contains no novel design; it is description, not decision. If everything is unsurprising, ask the author what they considered and rejected, because the actual interesting decisions are missing.

### Persona walkthrough
Read the doc from each perspective and capture findings unique to that viewpoint:
- **New hire on day 1**: can I build a mental model from this alone?
- **On-call engineer at 3am during an incident**: can I find the failing component and a runbook?
- **Security auditor**: can I evaluate the threat model, controls, and audit trail?
- **Finance or capacity planner**: can I forecast cost and resource use?
- **Regulator or compliance officer** (if applicable): can I find evidence of required controls?
- **Customer or end-user**: do I understand what changes for me, when, and how to recover from a bad change?
- **Adversary**: how do I exploit, abuse, or break this system for fun, profit, or chaos?

### Time-horizon walkthrough
Walk through the system at each horizon and capture distinct findings:
- **Day 1 (launch)**: is launch itself feasible, observable, and safely reversible?
- **Day 100 (steady state)**: does it run without daily human intervention?
- **Day 1000 (long term)**: has it accumulated lethal tech debt, or aged gracefully?
- **End of life**: how does it die gracefully without stranding users, data, or downstream consumers?

### Counterfactual constraints
Stress-test by changing constraints. Surface which decisions are fragile to constraint changes (revealing which constraints actually drove the design) vs. robust (sound regardless):
- Half the headcount?
- 10x smaller budget?
- No new technology allowed, only existing in-house tools?
- Twice the deadline?
- One region instead of multi-region?
- No vendor allowed, build everything in-house?
- Vendor-only, build nothing?

### Load-bearing assumption graph
List every assumption the design depends on. Identify which ones, if wrong, cascade and kill the project (load-bearing) vs. which are local and recoverable. For each load-bearing assumption, classify: validated by data, validated by prototype, validated by external commitment, or merely plausible-sounding. Plausible-only load-bearing assumptions are the biggest risks in any design.

### Bus factor per component
For each component, how many people understand it well enough to operate, debug, and extend it? Anything with bus factor 1 is a risk, even if those people are not leaving. Especially flag bus factor 1 where that 1 is the author of this doc, since reviews are the one chance to surface this.

### Asymmetric risk audit
Identify decisions where downside is huge relative to upside (or vice versa). Examples: a vendor with small short-term benefit but painful long-term lock-in; a refactor with small upside but large blast radius; a feature flag system that costs little but enables fast safe rollouts. Lean into asymmetric upside, away from asymmetric downside. Flag any asymmetric-downside bet the doc has not surfaced as such.

### Decision quality vs. outcome quality
For each decision, evaluate based on information available now, not on imagined outcomes. A good decision can still fail; a bad decision can succeed by luck. Critique the reasoning, not the speculative outcome. Conversely, flag decisions justified only by past lucky outcomes ("we did this last time and it worked").

### "What if we are wrong about the problem itself?"
The biggest failure mode of any design is solving the wrong problem perfectly. Is the problem statement questioned anywhere? Have user interviews, data, or direct observation grounded it? Or is the problem merely asserted? Flag any design where the problem feels assumed rather than evidenced.

