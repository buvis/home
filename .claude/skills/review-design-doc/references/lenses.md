# Ancient philosophical lenses


Modern review frameworks evolved from twentieth-century engineering practice. Ancient philosophical traditions evolved from millennia of disciplined thinking about how we know, how we argue, how we name, and how we act under uncertainty. Several of them catch failure modes engineering checklists do not: confusion of substance with cause, names that drift from referents, claims that masquerade as evidence, perspectives mistaken for universal truth, false dichotomies dressed as forced choices, false confidence under balanced evidence, and harm done to working systems in the act of changing them.

Apply these lenses on top of the standard checklist. They are particularly powerful for high-stakes designs where the author has already thought hard about the surface, so the remaining failure modes will hide in the foundations.

### Aristotle's four causes
Aristotle distinguished four causes of any thing: **material** (what it is made of), **formal** (its structure or pattern), **efficient** (what brought it into being), and **final** (its purpose, its telos). Most design docs over-describe the formal cause and under-describe the others.

Probe each in turn:
- **Material**: substrate, dependencies, third-party services, data shape. Is the substrate appropriate for the load and longevity?
- **Formal**: architecture, interfaces, data model. Is the structure coherent and minimal?
- **Efficient**: who builds, who operates, with what process and budget. Is the building plan honest about cost?
- **Final**: the actual user or business outcome served. Is the telos crisp in one sentence, and does every component trace back to it?

A doc that cannot state its final cause in one sentence is solving the wrong problem, or no problem at all. A doc with a clear final cause but uninspected material cause is building on sand it has not examined.

### Aristotle's mean between extremes
For every design choice, a virtue lies between two vices: excess and deficiency. The doc should name both extremes for each major decision, showing that the chosen path is consciously between them, not stumbled into by accident.

Examples:
- Coupling: monolithic mud (excess) vs. micro-fragmentation (deficient), virtue is appropriate cohesion
- Logging: silent (deficient) vs. firehose (excess), virtue is structured intentional events
- Abstraction: hardcoded (deficient) vs. over-generic (excess), virtue is the right shape
- Validation: trust everything (deficient) vs. validate everywhere (excess), virtue is boundary-only
- Retries: zero (deficient) vs. infinite (excess), virtue is bounded with backoff

If the doc does not name the vices, the design has not consciously chosen the mean. It has drifted into one of the extremes and called it good.

### Confucian rectification of names (zhèngmíng, 正名)
"If names are not correct, language is not in accordance with the truth of things. If language is not in accordance with the truth of things, affairs cannot be carried on to success." (Analects 13.3)

For every key term in the doc, demand:
- One and only one meaning within this doc
- The name accurately denotes what the thing is, not what we wish it were
- The name is distinct from related concepts (no silent overlap with "service", "module", "component", "system")
- The name is honest, not euphemistic or aspirational

A doc with sloppy naming has unstable foundations. Every downstream conversation will leak ambiguity, every test plan will misspecify, every incident review will dispute scope. Build a glossary if the terms warrant; if the author resists, that is itself the finding.

### Nyaya pramanas (epistemic classification)
The Nyaya school of Indian logic recognized four valid means of knowledge (pramanas). For every load-bearing claim in the doc, label its epistemic basis:

- **Pratyaksha** (perception): directly measured in this system or a representative one
- **Anumana** (inference): logically derived from established facts
- **Upamana** (analogy): a similar system behaves this way
- **Shabda** (testimony): an expert, vendor, blog post, or industry consensus says so

The four are not equal. Claims supported only by shabda are the weakest and most likely to fail under stress, because testimony does not survive context changes. Flag every load-bearing claim that lacks pratyaksha or anumana support. Strong designs are built on perception and inference, with analogy and testimony only as corroboration.

### Jain anekantavada (many-sidedness)
Reality is many-sided; every statement is true only from a perspective. Jain logic prefixes claims with **syād** ("from one viewpoint, may be"). For every absolute claim in the doc, mentally insert "from the perspective of X" and check the claim from other perspectives.

"This design is simple" might be true from the API consumer's view and false from the operator's. "This is fast" might be true at p50 and false at p99. "This is secure" might be true against external attackers and false against insiders. Each is a partial truth. A robust design either:
- Acknowledges the perspective dependence and qualifies the claim, or
- Demonstrates the claim holds across every relevant perspective

This is sharper than the persona walkthrough because it forces the *for whom* question into every assertion, not only into the dedicated persona section.

### Buddhist tetralemma (catuṣkoṭi)
For any apparent binary decision, the tetralemma forces consideration of four corners:
1. **A**: do option A
2. **not A**: do option B
3. **both**: hybrid, parallel run, layered approach where both coexist
4. **neither**: reject the binary; the question itself is wrongly framed

Many engineering dichotomies (monolith vs. microservices, sync vs. async, build vs. buy, REST vs. gRPC, SQL vs. NoSQL, queue vs. stream) are smuggled-in either/or framings. The tetralemma catches docs that picked option A without considering that the binary itself was a false framing.

For each binary in the doc, force the four-corner check. The "neither" corner is the most fertile and most often missed, because it requires reframing the question rather than answering it.

### Pyrrhonian epoché (suspended judgment under equipollent evidence)
The Pyrrhonist principle of **isostheneia** says: when arguments on opposing sides are of roughly equal strength, the disciplined response is to suspend judgment (epoché), not to choose under the pretense of certainty. Confident assertion under balanced evidence is intellectual dishonesty.

For each major decision, ask:
- Is the evidence actually strong enough to support the confidence level expressed?
- Where evidence is equipollent, does the doc acknowledge that and defer the decision via A/B test, parallel run, or feature flag, rather than asserting one path?
- Is the commitment a forced choice driven by deadline rather than evidence?

Flag false confidence specifically: claims expressed as decided when the evidence supports only a tentative lean. The fix is rarely "decide harder"; it is usually "instrument and defer."

### Hippocratic do-no-harm
From the classical medical oath: *primum non nocere*. Before introducing a change, enumerate what currently works that the change might break, degrade, or make harder. The iatrogenic effects of a change are easy to forget when the doc is focused on the benefits it delivers.

For each component the design introduces or modifies:
- What currently working behavior could this break or degrade?
- What workflows that humans rely on become harder?
- What downstream consumer assumptions get violated?
- What invariants of the existing system are at risk?

The Hippocratic check produces an explicit "what we might harm" list that sits alongside the "what we deliver" list. A design that delivers a new benefit but quietly breaks five existing ones is often a net loss. The doc should be honest about that ledger.

