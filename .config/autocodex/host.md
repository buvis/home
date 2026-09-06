# Autocodex host contract

The user requests unattended PRD execution through autocodex, inspired by
autoclaude, with Codex driving and Claude taking the former external Codex role.
Project root: {CWD}
This fresh session's phase: {PHASE}

First read the global and repository AGENTS.md, then activate
`{PLUGIN_ROOT}/skills/run-autopilot/SKILL.md` by reading it and following its
referenced procedure for the committed phase. Read the actual referenced files;
a slash command need not be registered in this host. Resolve every
`${CLAUDE_PLUGIN_ROOT}` reference to `{PLUGIN_ROOT}`. Personal skills continue to
resolve through `~/.agents/skills`. Read missing plugin skills from the installed
plugin's source rather than inventing their behavior. If a required capability
cannot be adapted, record a precise pause through the state CLI.

The following are explicit host adaptations authorized by the user's role swap.
They override Claude-specific dispatch examples in the source skills; all task,
coverage, evidence, review and transition obligations remain in force.

- Native Claude Agent/Task calls become native Codex subagent calls with isolated
  prompts. Load the complete referenced persona and rubric into each prompt;
  custom `autopilot:*` agent registrations are not presumed installed here.
  No parent conversation for reviewers. Await every dispatched agent and process
  in this session. Use the available native agent tools; never shell out to a
  nested Codex CLI to simulate a native subagent.
- Logical tiers: haiku = gpt-5.6-luna, sonnet = gpt-5.6-sol, opus = gpt-6-astra.
  Use the tier selected by the task classifier and escalation policy, recording
  the logical tier in existing schema fields and the actual provider/model in
  dispatch evidence. These are role mappings, not identical-capability claims.
  Fable remains a distinct, human-gated rescue tier, not an alias for Astra.
- A source `/use-codex` implementor or review dispatch becomes a Claude dispatch.
  For implementation use the real `use-sonnet` skill and its native Claude CLI
  wrapper at the equivalent logical tier. Preserve its guards and permission
  checks. For Bob's doubt review use the helper below, which invokes Claude Opus
  directly. Do not invoke codex-run.sh, codex_review_run.py, or strip nesting
  guards. Do not resume a Codex thread as a Claude session. Start the external
  reviewer fresh and supply all of the current cycle's required evidence.
- Alice: isolated native Codex Sol, implementation-aware consensus, complete
  consensus rubric. Blake: isolated native Codex Sol, PRD-only blind lens, complete
  blind rubric; no diff, file list, plan, history or sibling findings. Bob:
  external Claude Opus with the full assembled Bob persona, doubt D1-D5 and
  de-slop appendix, every cycle. Retain the requested R1-R5 doubt intent under
  the source's D1-D5 identifiers. Carl's optional Gemini lens and any required
  Eve/Fable constraints still follow the skill. Do not claim native model
  diversity without actual model dispatch evidence. Claude Bob supplies the
  independent provider voice; if unavailable, preserve the failure and pause.

Bob dispatch, using absolute paths and argument arrays (or safe shell quoting):

    python3 {DRIVER} --cd {CWD} reviewer -f <assembled-prompt> -o <unique-bob-output>

The helper saves immutable raw JSONL, stderr, reviewer text, and a receipt at
`<unique-bob-output>.receipt.json`. Include in the consolidated review top matter:

    autocodex_bob_receipt: <absolute receipt path>

Retain every raw rubric verdict in each corresponding consolidated reviewer
section: Alice's R rules, Blake's B rules, Bob's D1-D5. Do not emit a stale
`codex_thread_id` for a Claude reviewer. Keep provider provenance accurate in
state fields that accept it. The source codex-rung guard still needs accurate
task evidence and a non-Codex doubt voice; do not fake an Eve dispatch or claim
an unavailable capability. Record the Claude Bob host substitution explicitly.

Use the existing single state writer, never Write/Edit state.json directly:

    python3 {PLUGIN_ROOT}/skills/run-autopilot/cli/__main__.py <verb> <args>
    python3 {PLUGIN_ROOT}/skills/run-autopilot/scripts/statectl.py <state-path> <verb> <args>

These explicit paths replace shell functions `autopilot` and `statectl` when
they are unavailable in a headless shell. State is rooted at the exact project
directory above, `dev/local/autopilot/state.json`. Never attach to a different
ancestor or import another workflow's state.

Claude hooks are not assumed to run inside Codex. Perform the source-mandated
checks explicitly, including state/schema validation, task count consistency,
review coverage and full rubrics, and required quality/build gates. The wrapper
also checks review artifacts before it can advance. Do not omit a check merely
because the source expected a hook. Use Codex native compaction; do not copy
Claude's 500K context threshold or force a claimed 1M window.

Complete the active phase, commit the canonical phase transition, write the
handoff/contract card, then END this session. Never enter completion review from
a session that implemented the work; a fresh process must receive that handoff.
Review/rework follows the source's one-cycle-per-session procedure, followed by
a fresh review session. Do not invoke the next gate after its handoff. Final
prose is not a completion signal. Only committed state and a successful process
result authorize the wrapper to continue. A genuine missing user decision or
permission denial becomes a precise persisted pause; elapsed time is not consent.
