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
| `tools` | native lanes only | Omitted entirely for CLI-dispatched personas. |
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
| bob, carl, quinn, pat | *(omitted)* | CLI-dispatched (codex / gemini / qwen / sonnet runners). The runner owns the tool policy, not this file. |

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

**On the `agentType` probe (PRD 00109 Phase 0, task 3).** The PRD gates the
mechanism on a live probe workflow. That probe was NOT run. Two reasons, both
recorded rather than worked around: newly created agent files are not visible
to the Agent tool in the session that creates them (the registry is read at
session start), and this session was instructed not to invoke the Workflow
tool. The mechanism was instead settled documentarily: the Workflow tool's own
contract states that `opts.agentType` is "resolved from the same registry as
the Agent tool", and that registry is what `~/.claude/agents/` populates. That
is a documented contract, not an observation. **Before relying on the workflow
lane in anger, dispatch one registry agent by `agentType` from a fresh session
and record the result here.** If it does not resolve, the decided fallback
stands: the orchestrating skill reads the agent bodies at invocation and
passes them through workflow args — either way no persona text lives in the
workflow JS.

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
