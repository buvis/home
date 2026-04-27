---
name: elicit-requirements
description: "Structured requirement elicitation from rough ideas. Use before /create-prd when requirements are unclear or complex. Adaptive depth: minimal for clear requests, comprehensive for vague or architectural ones. Triggers on \"elicit requirements\", \"flesh out this idea\", \"what should we build\", \"requirements for\", \"scope this out\"."
argument-hint: "[<rough idea or path to brainstorming output>]"
---

# Elicit Requirements

Turn a rough idea into a validated discovery document that `/create-prd` can consume. Asks structured questions at adaptive depth, analyzes existing code when relevant, and produces a traceable requirements artifact.

**Pipeline position:** rough idea -> `/elicit-requirements` -> `/create-prd` -> `/plan-tasks` -> `/run-autopilot`

## Workflow

### 1. Accept Input

Find source material in this order:

1. **Argument** - user passed a rough idea or file path
2. **Brainstorming output** - check `docs/superpowers/specs/` for recent design docs. If found, read it and extract existing requirements, constraints, and decisions. Skip questions that the brainstorming output already answers.
3. **Conversation context** - idea discussed in current conversation

If the input is a file path, read the file. Extract whatever is available: problem statement, requirements, constraints, success criteria, open questions.

### 2. Classify Depth

Read `references/classification-guide.md`. Score the input across four dimensions:

1. **Requirement clarity** - how complete is the input?
2. **Scope breadth** - how many modules/files affected?
3. **Codebase impact** - greenfield vs brownfield?
4. **Problem complexity** - obvious solution vs multiple approaches?

Apply the classification rule: all low = minimal, any high = comprehensive, otherwise standard.

Announce the classification and let the user override:

> **Depth: {level}** ({1-sentence rationale}). Say "go deeper" or "keep it light" to adjust.

If the user says nothing or proceeds, accept the classification and continue.

### 3. Brownfield Analysis (standard+ depth only)

For standard and comprehensive depth, scan the codebase before asking questions:

1. **Pattern scan** - find similar existing implementations. For skills: scan `~/.claude/skills/` for structure conventions. For hooks: scan `~/.claude/hooks/`. For the relevant project: scan source directories.
2. **Dependency map** - identify existing modules the new feature will touch
3. **Convention extraction** - naming patterns, file organization, testing approaches
4. **Integration surface** - specific files or functions that would need modification

Store findings internally. Use them to:
- Auto-populate integration point options in questions
- Skip questions whose answers are obvious from the scan
- Include findings in the Codebase Context section of the output

### 4. Ask Clarifying Questions

Read `references/question-bank.md`. Select questions appropriate to the depth level.

**Rules:**
- One question per message. Concise, with enough context to answer quickly.
- Use `AskUserQuestion` tool with multiple-choice options when the question fits that format. Open-ended for scope boundaries and risk identification.
- Skip questions the input or brownfield analysis already answers. Note the inferred answer in the discovery log.
- After each answer, append the Q&A pair to the Discovery Log section of the working discovery file. This survives compaction.
- For comprehensive depth: after all questions, review answers for contradictions. If found, ask a contradiction resolution question.

**Question count by depth:**
- Minimal: 0-2 (inline, no file needed for the questions themselves)
- Standard: 3-6
- Comprehensive: 6-12

**Early exit:** If the user says "that's enough" or similar, stop asking and generate the document with what you have.

### 5. Write Discovery Document

Read `references/discovery-template.md`. Generate the discovery document at the classified depth.

**Sequence numbering:**
1. Scan all `.md` files in `dev/local/prds/**` and `dev/local/discovery/`
2. Extract leading 5-digit prefixes matching `^[0-9]{5}-`
3. New sequence = max + 1, zero-padded to 5 digits

**File path:** `dev/local/discovery/{sequence}-{feature-slug}.md`

Create `dev/local/discovery/` if it doesn't exist.

**Content rules:**
- Every section that appears must have real content. No stubs, no "N/A", no "TBD".
- Omit sections that don't apply at the current depth rather than filling them with placeholders.
- Discovery Log is mandatory at all depths.
- Open Questions section: list anything still unresolved. `/create-prd` will see these.

### 6. Suggest Next Step

After writing the document:

> Discovery saved to `dev/local/discovery/{filename}`.
> Review it, then run `/create-prd dev/local/discovery/{filename}` when ready.

Do not auto-invoke `/create-prd`. The user reviews first.

## Principles

These are drawn from AIDLC's Inception phase and adapted for a solo developer workflow:

- **When in doubt, ask.** Never assume requirements. Overconfidence leads to rework.
- **Adaptive depth.** Simple ideas get minimal ceremony. Complex ideas get thorough exploration. The workflow adapts to the work, not the other way around.
- **Questions in files, not just chat.** Storing Q&A in the discovery document creates a traceable record and survives context compaction.
- **Human approval gates.** The user reviews the discovery doc before it becomes a PRD. No silent progression.
- **Don't ask what code can answer.** If brownfield analysis reveals the answer, state the finding instead of asking.

## Reference Files

- `references/classification-guide.md` - depth classification rubric
- `references/question-bank.md` - question templates by depth and category
- `references/discovery-template.md` - output document template
