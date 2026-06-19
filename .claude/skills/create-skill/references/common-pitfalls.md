# Common pitfalls when building skills

Friction patterns hit during real skill builds. Each entry: symptom, root cause, workaround.

## Cross-script imports in a flat `scripts/`

**Symptom**: extracting a shared helper (`_common.py`) and importing it from sibling scripts.

**Root cause**: Python sibling imports in a flat directory require `sys.path.insert(...)` before the import, which triggers ruff/flake8 `E402` (module-level import not at top of file). Adding linter suppression markers is blocked by the aegis suppression-marker policy.

**Workaround**: for skills with <5 scripts, accept small duplication of shared helpers (e.g., a 3-line `strip_code_blocks` in each script). For larger script suites, convert `scripts/` to a proper Python package: add `__init__.py`, invoke scripts as `python -m <skill>.scripts.<name>`, and use relative imports. Don't try to bridge the gap with sys.path tricks — they fight tooling.

## Echo flags duplicate function names across scripts

**Symptom**: `def scan()` in `script_b.py` is flagged as duplicate of `def scan()` in `script_a.py`, even when the function bodies are entirely different.

**Root cause**: Echo's similarity matcher is name-led. Identical function names across scripts in the same skill trigger duplicate warnings.

**Workaround**: give functions distinct, action-specific names across scripts. `scan`/`audit`/`check` collide; `find_signals`/`weight_audit`/`verify_criteria` don't. The Echo gate accepts retry-passes when the duplication is genuinely new, but naming uniqueness avoids the retry round-trip and reads better at call sites.

## Scripts need explicit `chmod +x`

**Symptom**: `scripts/foo.py` with a `#!/usr/bin/env python3` shebang cannot be executed via `scripts/foo.py <args>` — only via `python3 scripts/foo.py <args>`.

**Root cause**: the Write tool does not set the executable bit, even when the file has a shebang.

**Workaround**: after writing all scripts, run `chmod +x <skill>/scripts/*.py` once. Alternatively, always invoke as `python3 scripts/foo.py` in SKILL.md instructions and skip the chmod step. Both work; the former is cleaner for user-facing examples.

## Skills don't take CLI args — paths must be solicited

**Symptom**: a skill that operates on a user-supplied file (design doc, log to analyze, config to validate) silently fails or hallucinates a path because there is nothing to act on. The skill was authored as if it had a first positional argument.

**Root cause**: commands receive positional args (`$1`, `$2`). Skills are invoked via conversation; the "input" is whatever the user typed when triggering the skill. "review this design doc" carries no path.

**Workaround**: combine a *static* hint (so the path requirement is visible at invocation time) with a *runtime* solicitation step (so the skill actually gets a path).

**Static hint** — add to the skill's frontmatter so autocomplete surfaces it when the user types `/<skill-name>`:
```yaml
argument-hint: "<path/to/input.md> [optional-context] [optional-other]"
```
Convention: `<required>` in angle brackets, `[optional]` in square brackets. Surface **all** inputs (required + optional), not only the required one — otherwise users assume the others don't exist. Also mention the primary input in the description itself (e.g., `"Use when ... (provide doc path)"`) so it shows up in the description listing, not only in the slash-command UI.

**Runtime solicitation** — put these steps in the skill's Inputs section and reference from Workflow step 1:

1. Scan the user's most recent message for the expected file/path. If exactly one is present and exists, confirm in chat: "Working on `<path>`. If that's wrong, say so now."
2. If no path is present, ask plainly with an example format. Wait for the answer; do not proceed.
3. Verify the path exists (Read or `ls`). If it doesn't, surface the error and ask again.
4. For optional inputs, only ask if the primary input references them or the user volunteers them — do not interrogate.

Skills that have neither the static hint nor the runtime ask either fail silently, ask awkwardly mid-execution, or invent a path. The two mechanisms are complementary, not alternatives.

## Batched state changes turn interruption into data loss

**Symptom**: a skill that walks the user through N decisions (findings, options, items to triage) silently batches the resulting edits and applies them at session end. If the session interrupts mid-walk (context cap, user stops, tool error), all collected decisions are lost; only the unmodified input survives. The user has done the work; the artifact has no record of it.

**Root cause**: the skill spec says "apply the chosen X" but doesn't enforce *when*. The model reasonably infers it can batch for turn efficiency — `AskUserQuestion → Edit → AskUserQuestion → Edit → ...` is more turns than `AskUserQuestion × N → Edit × N at end`. Batching reads as a reasonable optimization absent an explicit prohibition.

**Workaround**: write the workflow as a strict per-decision sequence and explicitly forbid batching. Example phrasing for SKILL.md:

> For each item, perform these in strict sequence before considering the next item:
> a. Present the item.
> b. Call AskUserQuestion.
> c. **Immediately** apply the result via Edit/Write. The change must complete before the next item is presented.
> d. Only then proceed.
>
> Do **not** batch. Do **not** queue changes. The output artifact is the single source of truth.

This makes the artifact itself the session state and interruption safe by construction (partial progress = artifact with partial changes; resume by re-invoking the skill). Skills that batch require separate state-recovery mechanisms (resume files, decision logs), which the no-side-file workflow specifically tries to avoid.

Add a "Session safety" subsection to the skill that explicitly tells the user: if you see no per-item changes happening on the artifact after the first few decisions, batching is happening — stop and ask the model to flush pending decisions before continuing.

## "Three options" must mean three distinct alternatives, not "mine + your own + skip"

**Symptom**: a skill that walks the user through decisions presents each as "approve my suggestion / specify your own / ignore." The user gets one real proposal plus two escape hatches, not a multi-option choice. Decisions feel pre-decided; the synthesis work the skill was supposed to do (generating alternatives) gets pushed onto the user as Option B.

**Root cause**: when a spec says "give the user three options," the model can satisfy that literally (A: my proposal, B: you specify, C: skip) without satisfying the intent (three different proposals). The "you specify" option is structurally an escape hatch, not an alternative.

**Workaround**: write the spec so that A/B/C must be **three distinct solution approaches**, each justified and concrete. Use a fourth explicit "no change" option (D) for the dispute/defer/skip case. AskUserQuestion supports four options — use all four.

Discipline each option must meet:
- **Distinct**: a different approach, not a minor variation. Wording change vs. structural change vs. addition vs. removal are distinct; "use X" vs. "use X with parameter Y" is not.
- **Relevant**: a plausible response to the actual decision, not padded to reach three.
- **Justified**: a one-line "why this works" attached.
- **Concrete**: specific enough to execute (an edit string, a config change, a specific action).

If three genuinely distinct options don't exist, the decision may be over-specified. Allow the skill to fall back to two real options with explicit acknowledgement ("Only two approaches are reasonable here") rather than padding. Padding to three produces options the user dismisses, which trains them to ignore the structure entirely.

Example of the failure mode and its fix:

| Failure | Fix |
|---|---|
| A: Apply proposed edit. B: Apply different edit (you specify). C: No edit. | A: Add a security review subsection. B: Add inline security notes per component. C: Reference an existing security doc with summary. D: No edit. |

The Fix column gives the user real choices that involve different tradeoffs. The Failure column gives the user one choice plus two escape paths.

## Card-text and picker-options must share one canonical order AND one label scheme

**Symptom**: a skill presents options in text (e.g., a "Solution options" card labeled A/B/C/D) and then calls AskUserQuestion with the same options. The picker auto-numbers them 1/2/3/4. The user sees `(Recommended) A` in the prose and `1. <approach name> (Recommended)` in the menu, and is forced to mentally remap "A in the card" → "1 in the menu" plus track which approach corresponds to which. Trust drops; mis-selections rise. Even when the order is preserved, the *label* mismatch alone is enough to confuse.

**Root cause**: two display surfaces with independent conventions. The prose card uses traditional A/B/C/D enumeration. AskUserQuestion's UI auto-numbers 1/2/3/4 and that numbering cannot be overridden. Without an explicit alignment rule, the model satisfies each convention independently and the two surfaces diverge.

**Workaround**: state explicitly in the skill spec that there is **one canonical label scheme and one canonical order**, used in both surfaces:

1. **Use the picker's numbering in the card too.** AskUserQuestion auto-numbers 1/2/3/4; use 1/2/3/4 in the card. Do not use A/B/C/D in the card while the picker uses numbers — the labels must match.
2. **Identify the recommended option first and assign it to position 1.** List next-best as 2, third-best as 3, no-edit/skip as 4. Both the card and the picker preserve this order.
3. **Never write "3 (Recommended)" in the card.** The recommended is always at position 1 in both surfaces.

State the rule loudly in the skill spec and forbid the alternatives. Example phrasing:

> Use numeric labels (1, 2, 3, 4) in both the prose card and the AskUserQuestion picker. Identify the recommended approach **before** writing the card and assign it to position 1. List next-best as 2, third-best as 3, no-edit as 4. The AskUserQuestion picker preserves this exact order. Do not use A/B/C/D anywhere; do not reshuffle between surfaces.

This is a specific instance of a broader rule: **when a skill presents the same content twice (e.g., a card and a picker, or a summary and a confirmation), the two presentations must share identical structure, identical ordering, AND identical labeling.** Any difference reads as a bug.

## Review-style skills need a comprehension pass before a critique pass

**Symptom**: a skill that reviews or audits an artifact (design doc, code, config, plan) immediately generates findings against the artifact's first sections. The findings are grammatically valid but semantically shallow — they nitpick phrasing and miss the structural ambiguities that a careful reader would notice. The reviewer never built a model of the whole before critiquing the parts.

**Root cause**: the model is asked to "review" without being asked to "understand first." It satisfies the literal instruction by generating critique-shaped output, but skips the comprehension that good human reviewers do (read end-to-end first, mark confusions, then critique with the whole in mind).

**Workaround**: split the review workflow into two passes:

1. **Comprehension pass**: read the artifact end-to-end **before generating any findings**. During the read, keep a **confusion-notes list** — specific places where the artifact is ambiguous, contradicts itself, or could mislead a competent reader. Each note must have: a location, what specifically is unclear, and why a reader could misread it.
2. **Critique pass**: generate findings against the artifact, including the confusion notes from pass 1 as Question-severity findings.

**Discipline on confusion notes**: a note is only valid if you can articulate (a) the specific source of ambiguity and (b) why a competent reader would misread. Stylistic preferences ("I'd phrase this differently") are not confusion notes. The bar is "a reader could misunderstand," not "I would word it otherwise."

This pattern applies broadly: any skill that examines an artifact and produces structured feedback (code review, doc review, plan critique, audit) should have an explicit comprehension step before the critique step. Without it, findings drift toward surface flaws and miss the structural issues that need the whole-artifact context.

## Migrating from a monolithic command file to a skill

**Symptom**: porting a 500–1000 line markdown command file (e.g., `~/.claude/commands/foo.md`) into a skill structure (`SKILL.md` + `references/*.md`). Reading each section into context and re-writing it wastes tokens proportional to the file size.

**Workaround**: use `awk` (inline via Bash, no script file) to route content sections directly into reference files without loading into Claude's context. Write `SKILL.md` manually as the orchestrator; migrate analytical content mechanically. Only the routing rules enter context; the content does not.

Example one-shot split:

```bash
awk -v dest="path/to/skill/references" '
  BEGIN { cf="" }
  /^## Section A/ { cf=dest"/a.md"; print "# A\n" > cf; next }
  /^## Section B/ { cf=dest"/b.md"; print "# B\n" > cf; next }
  /^## /          { cf=""; next }
  cf != ""        { print >> cf }
' source.md
```

The orchestrator (`SKILL.md`) is rewritten by hand because its structure changes (workflow, interaction patterns, references). The reference files are pure content moves and benefit from the mechanical split.
