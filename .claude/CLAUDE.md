# Claude Code user-level memory

## General guidelines

- In all interactions and commit messages, be extremely concise and sacrifice grammar for the sake of brevity.
- Only use emojis when the text would be unclear without them.
- Use conventional commit message formats, refer to specific section in this document for details.
- I'm a solo developer and it's just you and me working on this stuff, so I'm looking for all responses to be concise.
- This is not a corporate environment; avoid formalities and over-complication. Let's just get stuff done.
- Avoid over-engineering. Only make changes that are directly requested or clearly necessary. Keep solutions simple and focused.
- Don't add features, refactor code, or make "improvements" beyond what was asked. A bug fix doesn't need surrounding code cleaned up. A simple feature doesn't need extra configurability.
- Don't add error handling, fallbacks, or validation for scenarios that can't happen. Trust internal code and framework guarantees. Only validate at system boundaries (user input, external APIs). Don't use backwards-compatibility shims when you can just change the code.
- Don't create helpers, utilities, or abstractions for one-time operations. Don't design for hypothetical future requirements. The right amount of complexity is the minimum needed for the current task. Reuse existing abstractions where possible and follow the DRY principle.
- ALWAYS read and understand relevant files before proposing code edits. Do not speculate about code you have not inspected. If the user references a specific file/path, you MUST open and inspect it before explaining or proposing fixes. Be rigorous and persistent in searching code for key facts. Thoroughly review the style, conventions, and abstractions of the codebase before implementing new features or abstractions.
- Think as long as needed to get this right, I am not in a hurry. What matters is that you follow precisely what I ask you and execute it perfectly. Ask me questions if I am not precise enough.

## Planning mode

- At the end of each plan, give me a list of unresolved questions you have about the task
- Make the questions extremely concise
- Sacrifice grammar for brevity

## Writing

1. **Never use tired metaphors.** If you've read it a hundred times, skip it. "Move the needle" and "low-hanging fruit" mean nothing now.
2. **Use short words.** "Use" beats "utilize." "End" beats "terminate." Short words are faster to read and harder to misunderstand.
3. **Cut relentlessly.** If removing a word doesn't change meaning, remove it. Most first drafts carry 30% filler.
4. **Choose active voice.** "We deployed the service" is stronger than "The service was deployed." Active voice shows who did what.
5. **Drop the jargon.** Unless you're writing for specialists in your exact domain, use everyday words. "Fix" works better than "remediate."
6. **Break the rules when they make you sound ridiculous.** Sometimes passive voice works. Sometimes you need technical precision. The goal is clarity, not dogma.

Before you ship any writing, ask Orwell's six questions:

- What am I trying to say?
- What words express it?
- What image makes it clearer?
- Is this image fresh?
- Could I say it shorter?
- Have I written anything ugly?

## Quality

<frontend_aesthetics>
You tend to converge toward generic, "on distribution" outputs. In frontend design, this creates what users call the "AI slop" aesthetic. Avoid this: make creative, distinctive frontends that surprise and delight.

Focus on:

- Typography: Choose fonts that are beautiful, unique, and interesting. Avoid generic fonts like Arial and Inter; opt instead for distinctive choices that elevate the frontend's aesthetics.
- Color & Theme: Commit to a cohesive aesthetic. Use CSS variables for consistency. Dominant colors with sharp accents outperform timid, evenly-distributed palettes. Draw from IDE themes and cultural aesthetics for inspiration.
- Motion: Use animations for effects and micro-interactions. Prioritize CSS-only solutions for HTML. Use Motion library for React when available. Focus on high-impact moments: one well-orchestrated page load with staggered reveals (animation-delay) creates more delight than scattered micro-interactions.
- Backgrounds: Create atmosphere and depth rather than defaulting to solid colors. Layer CSS gradients, use geometric patterns, or add contextual effects that match the overall aesthetic.

Avoid generic AI-generated aesthetics:

- Overused font families (Inter, Roboto, Arial, system fonts)
- Clichéd color schemes (particularly purple gradients on white backgrounds)
- Predictable layouts and component patterns
- Cookie-cutter design that lacks context-specific character

Interpret creatively and make unexpected choices that feel genuinely designed for the context. Vary between light and dark themes, different fonts, different aesthetics. You still tend to converge on common choices (Space Grotesk, for example) across generations. Avoid this: it is critical that you think outside the box!
</frontend_aesthetics>

## MCP tools

### Context7

1. When questions involve APIs, packages, configuration, or usage examples, call the context7 tool first.
2. Before you are going to write any code, use context7 first for usage examples and documentation for APIs and dependencies used.

## System tools

Here are my preferences for tools to use when completing tasks.
In this context, tools don't refer to MCP offered tools,
but anything external to Claude that you might use to help complete the task.

### ast-grep vs ripgrep (quick guidance)

#### Structure matters

**Use `ast-grep` when structure matters.**
It parses code and matches AST nodes, so results ignore comments/strings, understand syntax,
and can **safely rewrite** code.

- Refactors/codemods: rename APIs, change import forms, rewrite call sites or variable kinds.
- Policy checks: enforce patterns across a repo (`scan` with rules + `test`).
- Editor/automation: LSP mode; `--json` output for tooling.

#### Text is enough

**Use `ripgrep` when text is enough.** It’s the fastest way to grep literals/regex across files.

- Recon: find strings, TODOs, log lines, config values, or non‑code assets.
- Pre-filter: narrow candidate files before a precise pass.

#### Rule of thumb

- Need correctness over speed, or you’ll **apply changes** → start with `ast-grep`.
- Need raw speed or you’re just **hunting text** → start with `rg`.
- Often combine: `rg` to shortlist files, then `ast-grep` to match/modify with precision.

#### Snippets

Find structured code (ignores comments/strings):

```bash
ast-grep run -l TypeScript -p 'import $X from "$P"'
```

Codemod (only real `var` declarations become `let`):

```bash
ast-grep run -l JavaScript -p 'var $A = $B' -r 'let $A = $B' -U
```

Quick textual hunt:

```bash
rg -n 'console\.log\(' -t js
```

Combine speed + precision:

```bash
rg -l -t ts 'useQuery\(' | xargs ast-grep run -l TypeScript -p 'useQuery($A)' -r 'useSuspenseQuery($A)' -U
```

#### Mental model

- Unit of match: `ast-grep` = node; `rg` = line.
- False positives: `ast-grep` low; `rg` depends on your regex.
- Rewrites: `ast-grep` first-class; `rg` requires ad‑hoc sed/awk and risks collateral edits.

## Conventional Commit Messages

### Message Format

Conventional commits format: `<type>(<scope>): <description>`

### Commit Types

| Type     | When                                        |
|----------|---------------------------------------------|
| fix      | Bug fix                                     |
| feat     | New or changed feature                      |
| perf     | Performance improvement                     |
| refactor | Code restructuring, no behavior change      |
| style    | Formatting only                             |
| test     | Tests added/corrected                       |
| docs     | Documentation only                          |
| build    | Build tools, dependencies, versions         |
| ops      | DevOps, infrastructure                      |
| chore    | Anything else                               |

### Rules

- imperative present tense
- no capital
- no period
- `!` before `:` for breaking changes
- commit message must fit on one line
- do not include anything like 🤖 Generated with Claude Code - Co-Authored-By: Claude <noreply@anthropic.com> in commit messages
