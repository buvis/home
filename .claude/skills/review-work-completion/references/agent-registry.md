# Agent Registry Conventions

The reviewer personas live as flat agent files in `~/.claude/agents/`. This
file is the convention every registry agent follows. The QA agent pack
(PRD 00091 / agoge) inherits these conventions rather than redefining them —
PRD 00109 owns them.

## File format

One flat `.md` file per persona, named for the persona (`alice.md`, `rita.md`).
Frontmatter carries:

| Key | Required | Notes |
|-----|----------|-------|
| `name` | yes | Matches the filename stem. This is the dispatch name. |
| `description` | yes | One line, ≤120 characters. It lands in the boot prefix, so length is a budget, not a style preference. |
| `tools` | yes, every persona | **Never omit it.** An absent `tools` key does not mean "no tools" — the harness registers every file here as a native agent type, and one with no `tools` key inherits the full set, Edit and Write included. Absence is the hazard; the hygiene suite asserts presence. |
| `model` | only when pinned | Eve pins `model: fable`. |

The body below the frontmatter is the persona's system prompt.

## Tool sets

No registry reviewer may carry `Edit` or `Write`. A reviewer that can modify
the repo is not a reviewer (discovery 00092 must-have 5). Beyond that:

| Persona | `tools` | Why |
|---------|---------|-----|
| rita, cora, grace, toby, mallory, trent | `Read` | The diff arrives inline in the dispatch prompt; these lanes never hunt for code. `Read` covers the truncated-diff path. |
| victor | `Read, Bash` | Explicitly told to check the surrounding code, not just the quoted finding. |
| alice, blake, eve | `Read, Bash` | Each is instructed to find the code itself. |
| bob, quinn, pat | `Read` | CLI-dispatched, and each is read-only on its own lane: Bob's prompt forbids running commands outright, Quinn runs `-R --approved-only`, Pat is dispatched with no `-a`/`-y`. |
| carl | `Read, Bash` | CLI-dispatched; documented as able to execute tests, linters and build commands. |

**The CLI four still declare tools.** Their runner owns the tool policy on the
CLI path and never reads this frontmatter — the consuming skill strips it and
passes only the body. But the same files are registered as native agent types,
so leaving `tools` off would make `bob`, `carl`, `quinn` and `pat` dispatchable
with Edit and Write. Bob in particular has a documented native fallback (when
codex is unavailable the same prompt runs on a Claude subagent), so this is not
hypothetical. Declaring a set costs nothing on the CLI path and closes the
native hole.

**Deviation from the PRD, recorded deliberately.** PRD 00109 specifies
`tools: Read` for native reviewers with "Victor alone adds Bash". That
convention assumes a reviewer can search with `Read` alone. In this build it
cannot: the native `Grep`/`Glob` tools are unregistered (upstream bug, see
`rules/tools.md` § Search Strategy), so search happens through `rg` via Bash. A
`Read`-only Alice, Blake or Eve could not locate the code each of their prompts
orders them to find. They therefore carry `Read, Bash`. The invariant the
must-have actually protects — no reviewer can modify the repo — is unchanged,
and the dimension lanes stay `Read`-only exactly as specified. Revisit if
`Grep`/`Glob` come back.

## No personal paths in bodies

A body must contain no `/Users/` and no `~/.claude`. Run-specific content
enters through named placeholders that the consuming skill substitutes; the
skill owns path resolution, the persona does not. Placeholders in use:

| Placeholder | Substituted with |
|-------------|------------------|
| `{CONTEXT_FILE}` | Absolute path to the gathered review context file. |
| `{DIFF_FILE}` | Absolute path to the full diff file. |
| `{DIFF}` | The diff text itself, inlined. |
| `{PRD}` | Full PRD content. |
| `{RUBRIC}` | Contents of the lane's rubric source, inlined. |
| `{REVIEW_CHECKLIST}` | Contents of `references/review-dimensions.md`. |
| `{OUTPUT_FORMAT}` | The "Agent Output Format" section of `references/output-formats.md`. |
| `{FINDING_TITLE}`, `{FINDING_SEVERITY}`, `{FINDING_FILE}`, `{FINDING_EVIDENCE}`, `{FINDING_PROOF}` | Fields of the finding Victor must refute. |
| `{TASK_SUBJECT}`, `{TASK_DESCRIPTION}`, `{TASK_ACCEPTANCE_CRITERIA}` | The task under per-task review. |
| `{SIMPLIFICATION_MANDATE}` | `work/references/simplification-mandate.md`, verbatim. |

A rubric is always inlined, never referenced by path: Bob, Carl and Quinn run
as external CLIs that cannot resolve a relative path, and native subagents get
self-contained prompts too.

## Dispatch mechanism

Registry personas dispatch by name:

- **Native lanes** — the Agent tool's `subagent_type`, with the persona file
  supplying the system prompt and run inputs supplied in the prompt argument.
- **Workflow lanes** — `agent(prompt, { agentType: '<name>' })`.
- **CLI lanes** — the skill assembles persona body + substitutions into a
  prompt file and passes it to the runner with `-f`, unchanged.

**On the `agentType` probe (PRD 00109 Phase 0, task 3).** Half observed, half
still open.

*Observed:* writing these files registered all 14 as native agent types **in
the same session that created them**, with their `tools` and `model` pins
applied. The registry does not require a session restart. (An earlier draft of
this note claimed the opposite; it was wrong, and the `tools`-key rule above
exists because the live registration is what exposed the inherit-everything
hazard.)

*Still open:* whether a workflow's `opts.agentType` resolves a user-level
persona. That was not probed — this session was instructed not to invoke the
Workflow tool. It rests on the Workflow tool's own contract, which states
`opts.agentType` is "resolved from the same registry as the Agent tool", and
that registry is demonstrably the one `~/.claude/agents/` populates. That is a
documented contract plus one observed half, not an end-to-end observation.
**Before the workflow lane is relied on, dispatch one registry agent by
`agentType` and record the result here.** If it does not resolve, the decided
fallback stands: the orchestrating skill reads the agent bodies at invocation
and passes them through workflow args — either way no persona text lives in
the workflow JS.

## Fail-closed

There is no fallback prompt anywhere. Before dispatch, the orchestrator
verifies each roster agent file exists and parses (frontmatter carries `name`
and `description`). A failure marks that reviewer failed, which the existing
retry policy and fail-closed verdict logic already escalate. In the workflow, a
dimension whose agent cannot be dispatched contributes a null result, which the
existing `decide_verdict` fail-closed path turns into CHANGES_REQUESTED.

## The roster

14 personas, names fixed:

| Lane | Personas |
|------|----------|
| Consensus | alice, bob, carl, quinn |
| Blind | blake |
| Doubt | eve |
| Fan-out dimensions | rita (requirements), cora (correctness), grace (quality), toby (tests), mallory (security) |
| Fan-out rubric / verify | trent, victor |
| Per-task patch | pat |
