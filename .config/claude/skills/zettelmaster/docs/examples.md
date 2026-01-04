# Zettelkasten Examples

## Example 1: Creating a New Zettel

### User Input
"I learned that LLM hallucinations occur when models generate plausible-sounding but factually incorrect information. This happens because they predict statistically likely text rather than accessing true facts."

### Generated Zettel
```markdown
---
version: 1.0
id: 20251107150234
title: LLM Hallucinations as Statistical Prediction Artifacts
date: 2025-11-07T15:02:34+01:00
tags: [ai/generative, ai/safety, llm/limitations]
type: note
publish: false
processed: false
synthetic: true
---

# LLM Hallucinations as Statistical Prediction Artifacts

LLM hallucinations represent factually incorrect but plausible-sounding outputs that arise from the model's fundamental operation as a statistical text predictor rather than a knowledge retrieval system.

## Core Mechanism

The hallucination phenomenon emerges because LLMs generate text by predicting statistically likely continuations based on training patterns. This means they optimize for linguistic plausibility rather than factual accuracy, creating confident-sounding statements without actual knowledge verification.

## Implications

This suggests that hallucinations are not bugs but inherent features of the current LLM architecture. Therefore, any application requiring factual accuracy must implement external verification mechanisms rather than trusting model outputs directly.

---
+defines:: [[zettel/20250915082314]]
+contradicts:: [[zettel/20250822141556]]
+develops:: [[zettel/20250901093421]]
```

## Example 2: Enhancing an Existing Zettel

### Existing Zettel
```markdown
---
id: 20250901093421
title: Pattern Recognition in Neural Networks
tags: [ai/fundamentals, neural/architecture]
processed: true
---
# Pattern Recognition in Neural Networks

Neural networks identify patterns through layered transformations of input data.
```

### New Information
"Recent research shows that neural networks don't just recognize patterns but actually create hierarchical representations, with early layers detecting simple features and deeper layers composing complex concepts."

### Enhancement Diff
```markdown
## Enhancement Diff for: Pattern Recognition in Neural Networks
**ID**: 20250901093421

⚠️ **WARNING**: This zettel is marked as `processed: true`
User approval required before modification!

## Tags to Add
+ ai/research
**Final tags**: ai/fundamentals, neural/architecture, ai/research

## Content to Append
```markdown

## Hierarchical Representation Learning (2025-11-07)

Recent research reveals that pattern recognition in neural networks involves creating hierarchical representations. Early layers detect simple features (edges, colors), while progressively deeper layers compose these into complex concepts (objects, abstractions).

This hierarchical structure suggests that neural networks don't merely match patterns but actively construct multilevel representations, similar to how human visual cognition builds complex understanding from primitive features.
```

## Relations to Add
+ +develops:: [[zettel/20251107150234]]

**Accept enhancement?** [Y/N]
```

## Example 3: Splitting Non-Atomic Content

### Input
"Zettelkasten has three main principles: atomicity means one idea per note, connectivity means linking related notes, and development means continuously expanding notes with new insights. It was created by Niklas Luhmann who used it to write over 70 books."

### Split Result

#### Zettel 1: Atomicity Principle
```markdown
---
id: 20251107151102
title: Atomicity Principle in Zettelkasten
tags: [knowledge/mgmt, zettelkasten/principles]
---
# Atomicity Principle in Zettelkasten

The atomicity principle mandates one idea per note, ensuring each zettel contains a single, complete concept that can be understood independently and referenced precisely.
```

#### Zettel 2: Connectivity Principle
```markdown
---
id: 20251107151145
title: Connectivity Through Linking in Zettelkasten
tags: [knowledge/mgmt, zettelkasten/principles]
---
# Connectivity Through Linking in Zettelkasten

Connectivity requires actively linking related notes, creating a web of interconnected ideas that enables knowledge discovery through relationship traversal.

---
+related:: [[zettel/20251107151102]]
```

#### Zettel 3: Continuous Development
```markdown
---
id: 20251107151223
title: Continuous Development of Zettels
tags: [knowledge/mgmt, zettelkasten/principles]
---
# Continuous Development of Zettels

The development principle encourages continuously expanding existing notes with new insights, treating zettels as living documents that evolve with understanding.

---
+related:: [[zettel/20251107151102]]
+related:: [[zettel/20251107151145]]
```

## Example 4: Creating a Hub

When 5+ zettels share the "ai/safety" tag:

```markdown
---
version: 1.0
id: 20251107152001
title: AI Safety Hub
date: 2025-11-07T15:20:01+01:00
tags: [ai/safety, meta/hub]
type: hub
publish: false
processed: false
synthetic: true
---

# AI Safety Hub

Hub for AI safety domain.

## Fundamental Concepts

- [[zettel/20250915082314]] – Definition of AI alignment
- [[zettel/20250822141556]] – Value alignment problem
- [[zettel/20251107150234]] – LLM hallucinations as safety issue

## Mitigation Strategies

- [[zettel/20250901093421]] – RLHF for alignment
- [[zettel/20250912101234]] – Constitutional AI approach
- [[zettel/20250925143022]] – Interpretability for safety

## Case Studies

- [[zettel/20250830091122]] – ChatGPT safety measures
- [[zettel/20250905112233]] – Anthropic's safety research

---
clusters:: alignment, mitigation, research
```

## Example 5: Detecting Contradictions

### Zettel A
"LLMs always produce deterministic outputs for the same input."

### Zettel B
"LLM outputs vary due to temperature settings and sampling strategies."

### Suggested Relations
```markdown
# For Zettel A:
+contradicts:: [[zettel/B_ID]]

# For Zettel B:
+contradicts:: [[zettel/A_ID]]
```

### User Prompt
"These zettels contain contradictory claims about LLM determinism. How would you like to resolve this?
1. Keep both with contradiction relations
2. Merge into a single nuanced zettel
3. Update Zettel A with correct information"

## Common Patterns

### Pattern: Definition → Implementation → Example
```
Zettel 1: +defines:: concept
Zettel 2: +implements:: [[zettel/1]]
Zettel 3: +exemplifies:: [[zettel/2]]
```

### Pattern: Thesis → Antithesis → Synthesis
```
Zettel 1: Original claim
Zettel 2: +contradicts:: [[zettel/1]]
Zettel 3: +develops:: [[zettel/1]], [[zettel/2]]
```

### Pattern: Progressive Deepening
```
Zettel 1: Basic concept
Zettel 2: +develops:: [[zettel/1]]
Zettel 3: +develops:: [[zettel/2]]
```