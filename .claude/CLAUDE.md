# AI assistant instructions

## Workflow

- After completing all tasks for a PRD, proactively run `/review-work-completion` — don't wait to be asked.
- For end-to-end PRD execution, use `/autopilot` — chains catchup, planning, work, review, and rework automatically.
- After completing work, clean up: remove stale worktrees (`git worktree remove`), delete orphan branches, and remove temp files created during the session.

## Changelog

Every project must have a `CHANGELOG.md` in the repo root following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

- When committing user-visible changes (feat, fix, breaking changes), add the entry to the `[Unreleased]` section of `CHANGELOG.md` in the same commit.
- Skip internal-only changes (refactoring, style, tests, CI, dep bumps) unless they affect users.
- Use categories: Added, Changed, Deprecated, Removed, Fixed, Security.
- On release, move `[Unreleased]` entries under a new version heading with the release date and add the comparison link at the bottom.
- If the project has no `CHANGELOG.md`, create one retroactively from git history before the next release.

## Naming

- Name commands, skills, functions, and anything that performs an action starting with an action verb (e.g. `review-deps-prs`, not `dep-updates`).

## General guidelines

- Default branch is `master` everywhere. Never refer to it as `main`.
- In all interactions and commit messages, be extremely concise and sacrifice grammar for brevity.
- Only use emojis when text would be unclear without them.
- Use conventional commit message formats. See section below.
- I'm a solo developer. Keep responses concise.
- This is not a corporate environment. Avoid formalities and over-complication.
- Avoid over-engineering. Make only changes directly requested or clearly necessary. Keep solutions simple and focused.
- Don't add features, refactor code, or make improvements beyond what was asked.
- Don't add error handling, fallbacks, or validation for scenarios that can't happen. Validate at system boundaries only.
- Don't create helpers, utilities, or abstractions for one-time operations. Don't design for hypothetical future requirements.
- ALWAYS read and understand relevant files before proposing edits. Do not speculate about code you have not inspected.
- Think as long as needed to get this right. Ask questions only when ambiguity is material. Otherwise choose the simplest safe assumption.
- All self-created working documents go in `.local/` in repo root. Ensure `.local/` is in `.gitignore`.
- Always use the Write tool for `.local/` files, including when CWD is `~/.claude`. Never use Bash shell redirects (`cat >`, `echo >`) to write files.
- Never move PRDs from backlog or wip to done until the user explicitly confirms.
- Keep the `00XXX-` prefix on PRD filenames when moving between backlog/wip/done.
- Use `mv` (not `cp`) when moving PRDs between folders — no duplicates across backlog/wip/done.
- NEVER silence warnings with `#[allow(...)]`, `// nolint`, `@SuppressWarnings`, `# type: ignore`, or equivalent. Fix root cause.
- When you discover pre-existing warnings, lint issues, or code smells, do not silently ignore them. Surface them and push for action.

## Production-ready code

All code must be complete, working, and shippable.

- No stubs or placeholders. Never leave TODO, FIXME, `NotImplementedError`, `unimplemented!()`, `pass`, or equivalent.
- No dummy values. Never return hardcoded or fake data where real logic belongs.
- Ask, don't stub. When requirements are unclear, ask instead of inserting temporary code.
- Tests required. Write or update tests covering new behavior. Ensure they pass.
- Self-review before responding. Scan all changes for incomplete markers and replace them with real implementations.
- Done means done. A task is complete only when everything needed for the feature is fully implemented.

## Critical thinking

Apply rigorous self-questioning before acting.

Before proposing solutions:

- What assumptions am I making? Are they grounded in code I've actually read?
- What's the simplest explanation? Am I overcomplicating this?
- What would break if I'm wrong?

Before writing code:

- Is there an existing pattern in this codebase that already solves this? Have I looked?
- What are the 2-3 alternatives? Why is this one better?
- What edge cases or failure modes am I ignoring?

When something seems obvious:

- Be suspicious of obvious answers.
- Ask: what if the opposite were true?

Surface the thinking when it matters:

- If I spot a flawed assumption in the request, say so directly.
- If there are meaningful tradeoffs, present them concisely.
- If uncertain, say why.

Never do:

- Withhold answers to force dialogue.
- Add questioning ceremony to simple tasks.
- Mistake verbosity for rigor.

## Planning

- When presenting a plan, end with unresolved questions.
- Keep questions extremely concise.
- Ask questions one by one.
- Give enough context so they can be answered quickly.

## Writing

1. Never use tired metaphors.
2. Use short words.
3. Cut relentlessly.
4. Choose active voice.
5. Drop jargon.
6. Never use em dashes. Use regular dashes, commas, periods, or parentheses instead.
7. Break rules when needed for clarity.

Before shipping writing, ask:

- What am I trying to say?
- What words express it?
- What image makes it clearer?
- Is this image fresh?
- Could I say it shorter?
- Have I written anything ugly?

## CSS

- Never use px for sizing: font-size, padding, margin, width, height, border-radius, etc.
- Use rem with base 16px: 4px=0.25rem, 8px=0.5rem, 12px=0.75rem, 16px=1rem.
- Acceptable px: border-width, box-shadow offsets, media query breakpoints.
- Notification badges: wrap icon and badge in a `position: relative` inline-block container, then position badge with `position: absolute; top: 0; right: 0; transform: translate(40%, -20%)`.

## Quality

<frontend_aesthetics>
Avoid generic, on-distribution frontend output.

Focus on:

- Typography: choose distinctive fonts. Avoid Arial, Inter, Roboto.
- Color and theme: commit to a cohesive aesthetic. Use CSS variables.
- Motion: use a few strong animations rather than many weak ones.
- Backgrounds: build atmosphere and depth. Avoid flat defaults.

Avoid:

- Overused font families
- Cliched color schemes, especially purple gradients on white
- Predictable layouts
- Cookie-cutter design

Make choices that feel designed for the context.
</frontend_aesthetics>

## macOS + Rust extensions

- After maturin builds a `.so`, macOS `syspolicyd` may block it silently — Python hangs on import, killed by SIGKILL with no error message.
- Fix: `codesign -f -s - path/to/_core.*.so` after build.
- When debugging "Python hangs on native extension import", check code signing first.

## Bash tool

- **One command per Bash call. No multi-line scripts.** Each Bash tool invocation must contain exactly one command starting with the binary name. The permission prefix is the first token — anything before the binary (variable assignments, newlines, env vars) becomes the prefix and breaks permission matching.
- Never use shell variable assignments (`F=...`, `WD=...`) or env var prefixes in Bash calls. Inline all values directly. Wrong: `F=/path/to/file\nshowboat init "$F" "Title"`. Right: `showboat init /path/to/file "Title"`.
- **Never pipe commands.** `uv run pytest ... | head -30` breaks `Bash(uv run:*)` permission matching — the pipe makes it a different command. Use separate Bash calls or tool parameters instead.
- Never chain with `&&`, `;`, or newlines when sub-commands have different permission prefixes.
- Use separate parallel Bash calls when commands are independent, sequential when dependent.
- Don't add `2>&1` — the Bash tool captures both stdout and stderr by default.

## Tools

- When questions involve APIs, packages, configuration, or usage examples, use the best available documentation source first.
- Before writing code, check documentation and usage examples for the APIs and dependencies involved.
- Use `ast-grep` when structure matters.
- Use `rg` when text is enough.
- Prefer `ast-grep` for codemods and precise rewrites.
- Prefer `rg` for fast recon and pre-filtering.

## Conventional commit messages

Format: `<type>(<scope>): <description>`

Types:

- `fix`: bug fix
- `feat`: new or changed feature
- `perf`: performance improvement
- `refactor`: restructuring, no behavior change
- `style`: formatting only
- `test`: tests added or corrected
- `docs`: documentation only
- `build`: build tools, dependencies, versions
- `ops`: DevOps, infrastructure
- `chore`: anything else

Rules:

- imperative present tense
- no capital
- no period
- `!` before `:` for breaking changes
- one line only
- do not include generated-by or co-authored-by boilerplate
