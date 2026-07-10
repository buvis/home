---
name: convene-council
description: Use when an ambiguous decision has multiple credible paths and needs structured disagreement before choosing. Triggers on "council", "second opinion", "convene council", "decision council", "multiple perspectives", "go or no go".
---

# Convene Council

Convene four advisors for ambiguous decisions: the in-context Claude voice
(Architect) plus Skeptic, Pragmatist, and Critic subagents (lenses in the
Roles table). For **decision-making under ambiguity** only — see When NOT to
Use.

## When to Use

Use convene-council when a decision has multiple credible paths and no obvious winner,
tradeoffs need explicit surfacing, the user asks for second opinions or
dissent, or conversational anchoring is a real risk (e.g. monorepo vs
polyrepo, ship now vs hold, feature flag vs full rollout).

## When NOT to Use

| Instead of convene-council | Use |
| --- | --- |
| Verifying whether output is correct | `review-with-doubt` or `review-blindly` |
| Breaking a feature into implementation steps | `plan-tasks` |
| Reviewing code for bugs or security | `review-blindly` or `review-with-doubt` |
| Validating completed work | `review-work-completion` |
| Straight factual questions | just answer directly |
| Obvious execution tasks | just do the task |

## Roles

| Voice | Lens |
| --- | --- |
| Architect | correctness, maintainability, long-term implications |
| Skeptic | premise challenge, assumption breaking, the simplest credible alternative |
| Pragmatist | shipping speed, simplicity, user impact, real-world execution |
| Critic | edge cases, downside risk, failure modes, reasons the plan could fail |

The three external voices should be launched as fresh subagents with **only the question and relevant context**, not the full ongoing conversation. That is the anti-anchoring mechanism.

## Workflow

### 1. Extract the real question

Reduce the decision to one explicit prompt:
- what are we deciding?
- what constraints matter?
- what counts as success?

If the question is vague, ask one clarifying question before convening the council.

### 2. Gather only the necessary context

Codebase-specific decision: collect the relevant files, snippets, issue text,
or metrics — compact, only what the decision needs. Strategic/general
decision: skip repo snippets unless they materially change the answer.

### 3. Form the Architect position first

Before reading other voices, write down:
- your initial position
- the three strongest reasons for it
- the main risk in your preferred path

Do this first so the synthesis does not simply mirror the external voices.

### 4. Launch three independent voices in parallel

Launch them via the Agent tool (subagent_type: general-purpose) in a single
message, in parallel — each gets only the prompt below (question, compact
context, strict role; no conversation history, per the Roles-table rule).

Prompt shape:

```text
You are the [ROLE] on a four-voice decision council.

Question:
[decision question]

Context:
[only the relevant snippets or constraints]

Respond with:
1. Position — 1-2 sentences
2. Reasoning — 3 concise bullets
3. Risk — biggest risk in your recommendation
4. Surprise — one thing the other voices may miss

Be direct. No hedging. Keep it under 300 words.
```

Each role's emphasis is its Roles-table lens — restate nothing else.

### 5. Synthesize with bias guardrails

You are both a participant and the synthesizer, so use these rules:
- do not dismiss an external view without explaining why
- if an external voice changed your recommendation, say so explicitly
- always include the strongest dissent, even if you reject it
- if two voices align against your initial position, treat that as a real signal
- keep the raw positions visible before the verdict

### 6. Present a compact verdict

Use this output shape:

```markdown
## Council: [short decision title]

**Architect:** [1-2 sentence position]
[1 line on why]

**Skeptic:** [1-2 sentence position]
[1 line on why]

**Pragmatist:** [1-2 sentence position]
[1 line on why]

**Critic:** [1-2 sentence position]
[1 line on why]

### Verdict
- **Consensus:** [where they align]
- **Strongest dissent:** [most important disagreement]
- **Premise check:** [did the Skeptic challenge the question itself?]
- **Recommendation:** [the synthesized path]
```

Keep it scannable on a phone screen.

## Persistence Rule

Do **not** write ad-hoc notes to shadow paths from this skill.

If the council materially changes the recommendation:
- update the relevant GitHub / Linear issue directly if the decision changes active execution truth
- save a memory file under `~/.claude/projects/-Users-bob--claude/memory/` only if the outcome is durable guidance for future sessions

Only persist a decision when it changes something real. Never persist every
verdict regardless of importance.

## Multi-Round Follow-up

Default is one round. On a requested second round: keep the new question
focused, include the previous verdict only if necessary, and keep the Skeptic
clean to preserve anti-anchoring value.

## Related Skills

- `review-with-doubt` — adversarial self-review of a single output
- `research` — gather external reference material before the council if needed
- `debug-stuck-agent` — when the issue is a stuck agent rather than an ambiguous decision

The value is not unanimity. The value is making the disagreement legible before choosing.
