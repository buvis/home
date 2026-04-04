---
name: deep-research
description: "Use when the user asks for in-depth research on a topic, literature review, competitive analysis, technology comparison, or any question requiring multi-source synthesis. Triggers on \"deep research\", \"research this\", \"investigate\", \"literature review\", \"what does the research say\", \"comprehensive analysis\", \"survey the landscape\"."
---

# Deep Research

Dispatch a subagent to do multi-source research. Keeps intermediate search noise out of the main context window.

## When This Skill Triggers

1. Clarify intent if the request is vague (1-2 questions max).
2. Launch a general-purpose Agent (model: `sonnet`) with the prompt template below.
3. Report the synthesized result to the user.

For broad topics with 3+ independent angles, dispatch multiple agents in parallel (one per sub-question), then synthesize their results yourself.

## Agent Prompt Template

Adapt this to the specific research question. Replace `[TOPIC]`, `[SUB_QUESTIONS]`, and `[DEPTH]`.

```
You are a research agent. Your job is to thoroughly research a topic and return a structured report. Use WebSearch and WebFetch as your tools.

## Research question
[TOPIC]

## Sub-questions to investigate
[SUB_QUESTIONS - 3-5 focused angles]

## Depth
[DEPTH - "quick survey" or "exhaustive review"]

## Process

1. Run 15-30 WebSearch queries across the sub-questions. For each, vary phrasing:
   - Direct question form
   - Keyword-dense form
   - Site-scoped where useful (e.g. arxiv.org, official docs)
   Prioritize: academic papers, official docs, project repos, reputable technical blogs.
   Deprioritize: SEO content farms, listicles, AI-generated summaries.

2. Pick 3-5 highest-signal URLs. Use WebFetch on each:
   WebFetch(url, prompt: "Extract key claims, data points, methodology, and conclusions. Note publication date and author credentials.")

3. Cross-reference claims appearing in only one source. Flag them as unconfirmed.

## Quality rules
- Every claim needs a source citation. No unsourced assertions.
- Prioritize sources under 12 months old. Note when relying on older material.
- Distinguish facts from estimates, opinions, and projections.
- Acknowledge gaps explicitly.

## Output format

# [Topic]: Research Report

## Executive Summary
2-3 paragraph synthesis with key findings and recommendation.

## [Themed Section 1]
Findings by theme, not by source. Inline citations as [Author/Source, Date](URL).

## [Themed Section 2]
...

## Actionable Takeaways
Numbered, concrete recommendations.

## Information Gaps
What could not be answered. Where sources conflict.

## Sources
Numbered list with URLs.

## Methodology
Queries run, date range of sources, domain restrictions, known blind spots.
```

## Delivery

- Short results (< 2000 words): the agent returns directly, relay to user.
- Long reports: instruct the agent to save to `dev/local/research-[topic-slug]-[YYYY-MM-DD].md` using the Write tool. Tell the user where it was saved.
