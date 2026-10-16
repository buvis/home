# Autocodex host contract

## Interactive recovery

When the operator asks you to read this file for interactive recovery, work from
the intended repository root. If its path placeholders are still unresolved,
run `mise exec -- python3 ~/.config/autocodex/driver.py --dry-run` there and read
the resolved host instructions it prints. This starts no agent and changes no
workflow state. Do this once; the resolved output needs no further dry run.

Use the resolved paths and host adaptations below to read the installed
run-autopilot skill and its referenced Resume procedure. Inspect the committed
pause reason and review evidence, then obtain any required operator decision
interactively. The unattended execution wording below does not authorize
clearing a pause, raising a cap, or starting repairs by itself. Keep Codex as
coordinator and use the model-provider review routing defined below.
Use the existing state CLI for any authorized transition. Preserve the fresh
work/review session boundary, then exit so the operator can run `autocodex` again.

## Phase execution

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
- The main session coordinates and delegates substantive work. Its model/effort
  do not prescribe worker or reviewer settings. Always set model and reasoning
  effort explicitly when dispatching native agents; do not inherit the parent's
  low effort. Use isolated prompts (no parent-history fork) to apply overrides.
- Logical worker tiers: {ROLE_MAPPING}.
  Use the tier selected by the task classifier and escalation policy, recording
  the logical tier in existing schema fields and the actual provider/model in
  dispatch evidence. These are role mappings, not identical-capability claims.
  After a failed opus attempt with a concrete unresolved defect, failed check,
  or documented reasoning blocker, use {ESCALATION_ROLE} for the next bounded
  attempt when the source escalation policy permits it. Record the trigger and
  actual settings. Do not escalate merely because the logical tier is opus.
  Fable remains a distinct, human-gated rescue tier, not an alias for Astra.
- A source `/use-codex` implementation dispatch becomes a Claude dispatch through
  the real use-sonnet skill and its wrapper. Preserve guards and permissions.
- Before any implementation dispatch, check that its model provider has an
  independent review route supported by this host and its driver. If the source
  routing table selects a provider without that support (including Gemini for
  UI work), use the native worker at the task's existing logical tier and the
  resolved mapping above. This operator-authorized fallback overrides the source
  "Gemini if available" rule even when its CLI is installed; no further operator
  decision is required. Record the selected source route, missing review support
  and effective native dispatch in the build evidence. Preserve all task gates,
  tier/escalation rules and review lenses. Do not change permission-denial or
  supported-reviewer failure handling. This fallback applies only before
  dispatch: it never relabels existing implementation evidence or supplies a
  guessed review mapping for code already contributed by an unsupported model.
- Review routing uses the **actual implementation model's company**, never the
  launcher name. Codex, Claude, Kiro and Copilot are launchers, not evidence of
  model origin. This operator-authorized policy replaces the source's
  `implementor == "codex"` / additive Eve guard and the former fixed host roster.
  Keep all three lenses, their complete rubrics, isolation and coverage.

## Model evidence and review routing

Before every review cycle, inspect the current PRD's actual implementation logs:
raw worker/session metadata and dispatched model, dispatch-ledger records, and
per-task build evidence. Correlate task/attempt/session IDs and the work range;
exclude planning, coordinator and read-only review models. Include test writers,
repairs, prior contributing attempts, split tasks, model switches and fallbacks.
Do not grep the entire transcript for model names and treat prompt examples or
reviewer models as implementors. Prefer observed model metadata over requested
configuration; a requested auto/tier alias does not prove the served model.

Populate `tasks[].attempts[].actual_model` and `actual_provider` accurately via
statectl from that evidence. Retain launcher identity separately. Never rewrite
history to fit routing. Missing, ambiguous or conflicting evidence pauses for
operator clarification; neither launcher identity nor the coordinator model is
an acceptable fallback. Unknown model families require an explicit verified
mapping, never a guess. Kiro/Copilot auto routing requires the resolved model in
logs; if those logs do not expose it, pause.

Write a durable audit at
`docs/dev/project-management/autopilot/reports/<prd-stem>-implementation-models.json`:
`{"fingerprint": <driver.implementation_fingerprint(state)>,
"snapshot": <driver.implementation_snapshot(state)>, "evidence": [...]}`.
Each evidence row contains `task`, `role: "implementation"`, exact `model`, a
repo-relative `path`, 1-based `line`, and SHA-256 of that line's bytes (excluding
its newline). Cite all observed contributing models, not just one model per task.
Explain the correlation in a sibling Markdown audit. The fingerprint binds PRD,
cycle, work_start_sha and implementation attempt provenance; regenerate before
each new review. Keep the reviewed snapshot through rework: the boundary checks
receipts against that snapshot; convergence additionally requires unchanged
implementation provenance.
Use actual log/evidence files, not a new restatement of the model claim.

Run `python3 {DRIVER} --cd {CWD} review-route` before dispatch. It validates audit
freshness, evidence hashes and task coverage and returns the required providers:

- OpenAI GPT implementation → Anthropic Claude Opus/xhigh for Alice, Blake, Bob.
- Anthropic Claude implementation → OpenAI {REVIEW_ROLE} for Alice, Blake, Bob.
- Mixed implementation → both complete three-lens rosters, independently. Each
  roster reviews the whole change so interactions also receive review. Consolidate
  all findings; no same-company review replaces the opposite-company coverage.

Alice retains the complete consensus rubric and implementation context. Blake
gets only the PRD and repository access: no diff, file list, plan, history,
implementation audit or sibling findings. Bob retains the full assembled persona,
D1-D5 doubt rubric and de-slop appendix. Every invocation is fresh and isolated.
Carl remains optional under the source rules. Eve is not added merely because
Codex implemented a task: the provider guard now establishes independence. An
explicit separate Fable rescue request remains human-gated.

For these review lanes only, use real external reviewer processes via the helper
below, including GPT reviewers. This is an explicit external-review transport,
not an attempt to simulate native subagents; it overrides native reviewer dispatch
examples. Do not strip nesting guards or resume an implementation thread. If the
launcher cannot run the reviewer with its guards intact, preserve evidence and
pause. Native work delegation remains as specified above.

    python3 {DRIVER} --cd {CWD} reviewer --lens alice|blake|bob -m <model> -f <assembled-prompt> -o <unique-output>

Use `opus` for Anthropic and the model portion of `{REVIEW_ROLE}` for OpenAI;
GPT effort follows AUTOCODEX_REVIEW_EFFORT (default high). Pass absolute paths and
argument arrays (or safe shell quoting). Await every process. The helper checks
the selected lens's full rubric and writes immutable raw evidence and a receipt.

External reviewer dispatches need network access in the calling Codex command.
When that command's sandbox restricts network access, request
`sandbox_permissions="require_escalated"` for the exact helper or dispatch
command, with a narrow justification. Let the host's approval review decide;
preserve the launcher's permission settings and nesting guards. An inherited
network restriction can report `ENOTFOUND` even while the host can reach the API.
If a dispatch already failed inside that sandbox, retain its evidence and follow
the host tool's required approved retry before treating it as a terminal reviewer
failure. If approval is denied, record the denial and pause. The terminal-failure
rule below applies after dispatch with the required network access.

The helper saves immutable raw JSONL, stderr, reviewer text, and a receipt at
`<unique-output>.receipt.json`. Include in the consolidated review top matter:

    autocodex_<lens>_<provider>_receipt: <absolute receipt path>

Use lens alice/blake/bob and provider anthropic/openai. Include every required
receipt, including both providers for mixed work. Record `provider_review_guard:
satisfied` on one line only after all required rosters succeed. The host gate
checks each receipt, raw successful output, provider and complete rubric. Record
`codex_rung_guard: not fired` only as the legacy compatibility field and explain
that the model-provider guard supersedes it; never claim Eve ran.

The helper handles confirmed Claude quota resets itself: after a structured
API 429 rejection, it waits until the reported reset plus five seconds, within
the quota-wait deadline, then retries with a fresh raw log. Keep
awaiting that same helper while it waits; do not launch another reviewer,
classify its pending output as a failed review, or retry before reset. If the
helper exits unsuccessfully, preserve its raw evidence and pause as above.

Retain every raw rubric verdict in the corresponding consolidated section:
Alice's R rules, Blake's B rules, Bob's D1-D5. For mixed work, preserve both
provider outputs under each persona heading, with explicit provider subheadings.
Keep actual provider, model, effort, session and source evidence accurate. Do not
reuse a Codex thread ID for Claude. Source schema enum labels are not provenance.

Use the existing single state writer, never Write/Edit state.json directly:

    python3 {PLUGIN_ROOT}/skills/run-autopilot/cli/__main__.py <verb> <args>
    python3 {PLUGIN_ROOT}/skills/run-autopilot/scripts/statectl.py <state-path> <verb> <args>

These explicit paths replace shell functions `autopilot` and `statectl` when
they are unavailable in a headless shell. State is rooted at the exact project
directory above, `docs/dev/project-management/autopilot/state.json`. Never attach to a different
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
