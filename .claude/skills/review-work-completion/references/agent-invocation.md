# Agent Invocation

## Alice (Claude subagent)

Alice runs as a direct subagent (not a nested CLI invocation - `claude -p` inside a subagent doesn't work).

```
Task tool:
  subagent_type: general-purpose
  description: "Alice reviews work against PRD requirements"
  prompt: |
    You are Alice, a code reviewer.

    {contents of alice_prompt_file}
```

The prompt file contents are inlined directly into the Task prompt. The subagent has native access to Read and Bash (`rg` for search; the Grep/Glob tools are absent in this build) - no need to shell out.

## Bob (Codex)

Run codex as a **direct background Bash command - do NOT wrap it in a Task subagent.** A subagent that shells out to a CLI hangs: the CLI spawns its own child process the subagent wrapper never gets a completion signal from, so the subagent yields "codex still running" and the reviewer never reports. That is the recurring Phase 4 review thrash-halt (playground 00007, 2026-06-30). Run codex directly and the harness tracks the background process. **In an interactive session** this re-invokes you when it finishes; **in headless/loop mode (`$_AUTOPILOT_LOOP` set) it does not** — headless `claude -p` kills background Bash ~5s after your turn ends, so ending the turn to "wait" for Bob kills him mid-review (2026-07-15 loop death, PRD 00062 cycle 3: Bob/Quinn killed with empty output). Dispatch the Watcher subagent from SKILL.md step 5 in the same message, or you will not be re-invoked.

Write the prompt to a temp file, then dispatch (**absolute paths** - relative `dev/local/` paths get misresolved).

**Full review (cycle 1)** - capture Bob's codex session thread id so later cycles can resume it:

```
Bash tool (run_in_background: true):
  ~/.claude/skills/use-codex/scripts/codex-run.sh -f "{bob_prompt_file_absolute_path}" -o "{abs_repo_path}/dev/local/tmp/bob-output-{id}.txt" --emit-thread-id "{abs_repo_path}/dev/local/tmp/bob-thread-{id}.txt"
```

**Incremental review (rework cycle) with a prior `codex_thread_id`** (step 3 read it from the previous review file) - same command plus `--resume-thread` so Bob verifies fixes against his own cycle-1 critique instead of re-reviewing from zero:

```
Bash tool (run_in_background: true):
  ~/.claude/skills/use-codex/scripts/codex-run.sh -f "{bob_prompt_file_absolute_path}" -o "{abs_repo_path}/dev/local/tmp/bob-output-{id}.txt" --emit-thread-id "{abs_repo_path}/dev/local/tmp/bob-thread-{id}.txt" --resume-thread "{prior_codex_thread_id}"
```

`--emit-thread-id` records the codex session id (from the `thread.started` event) to `bob-thread-{id}.txt`; step 8 stamps it into the review-file frontmatter as `codex_thread_id`, and the next cycle's step 3 reads it back. `--resume-thread` continues that session; an empty/expired thread degrades to a fresh run with a loud stderr note (never a blocked cycle), and it composes with `--emit-thread-id` (re-writing the same id keeps the sidecar fresh for the following cycle). **Never add `--ephemeral` to the cycle-1 dispatch - it disables resume.** `-o` writes codex's review text straight to the file step 6 consolidates - no manual save, no Agent round-trip. When the background command completes, read `bob-output-{id}.txt`. If `codex-run.sh` exits non-zero, treat Bob as a failed reviewer (graceful degradation per `retry-policy.md`); a single failed CLI reviewer does not block the cycle.

## Carl (Gemini)

Carl is the frontend & design specialist (see `agent-prompts.md`). Like Bob, run gemini as a **direct background Bash command, NOT a Task subagent** - a subagent wrapping a CLI hangs (see Bob above).

Write the prompt to a temp file, then dispatch (**absolute paths**):

```
Bash tool (run_in_background: true):
  ~/.claude/skills/use-gemini/scripts/gemini-run.sh -f "{carl_prompt_file_absolute_path}" -o "{abs_repo_path}/dev/local/tmp/carl-output-{id}.txt"
```

`-o` writes Carl's output straight to the file step 6 consolidates. When the background command completes, read `carl-output-{id}.txt`. If `gemini-run.sh` exits non-zero (e.g. monthly quota exceeded), skip Carl and proceed with the other reviewers (graceful degradation).

## Quinn (Qwen, local)

Quinn runs local qwen as a **direct background Bash command - do NOT wrap it in a Task subagent.** Like Bob and Carl, a subagent that shells out to a CLI hangs: the CLI spawns its own child process the subagent wrapper never gets a completion signal from, so the subagent yields "still running" and the reviewer never reports. Run `qwen-run.sh` (the `pi` agent against a llama.cpp-served model) directly and the harness tracks the background process. **This only re-invokes you in an interactive session.** In headless/loop mode (`$_AUTOPILOT_LOOP` set), the Watcher subagent from SKILL.md step 5 is what keeps the session alive while Quinn runs — dispatch it in the same message, or ending your turn kills Quinn mid-review.

Write the prompt to a temp file, then dispatch (**absolute paths** - relative `dev/local/` paths get misresolved). Pass `-R` (read-only tools — a reviewer must never edit the repo; pi's default mode auto-approves edit tools):

```
Bash tool (run_in_background: true):
  ~/.claude/skills/use-qwen/scripts/qwen-run.sh -R --approved-only -f "{quinn_prompt_file_absolute_path}" -o "{abs_repo_path}/dev/local/tmp/quinn-output-{id}.txt"
```

`-o` writes Quinn's output straight to the file step 6 consolidates - no manual save, no Agent round-trip. The script re-runs its own 1-token completion preflight before dispatch, so a backend that died between step 1 and step 5 exits non-zero fast instead of hanging; local inference then takes minutes, and only the Watcher subagent (SKILL.md step 5, headless/loop mode) keeps the session alive to see it finish — background Bash alone does not re-invoke a headless session. When it completes, read `quinn-output-{id}.txt`. If `qwen-run.sh` exits non-zero, skip Quinn and proceed with the other reviewers (graceful degradation); a single failed reviewer does not block the cycle.

Quinn's prompt is still built from Alice's shared template (`SKILL.md` step 4) - the standard implementation-aware review prompt, never the blind or doubt lens, and no sandbox-constraints appendix (that is Bob/codex only). The prompt uses absolute paths, so it resolves correctly for the local reviewer. Quinn's weight is ADVISORY (`SKILL.md` step 6): findings unique to him land under `advisory (local model, unconfirmed)` and create no tasks; his concurrence counts toward consensus normally.

## Eve (Fable 5)

Eve runs Claude Fable 5 as a **native Task subagent** (like Alice - NOT a background-Bash CLI like Bob/Carl/Quinn). There is no `fable-run.sh` wrapper and none is needed: the Task/Agent tool's `model` parameter accepts `"fable"` directly (the same tier alias as `"sonnet"`/`"opus"`/`"haiku"`; Fable 5 is model id `claude-fable-5`), so Eve dispatches in-process with native Read/Bash access (`rg` for search; Grep/Glob absent in this build) - no CLI shell-out, no `-o` output file, no background-Bash hang risk. Eve is a skeptical, high-scrutiny reviewer suited to final doubt review.

Assemble Eve's prompt from the **same base document codex uses** (`~/.claude/skills/run-autopilot/prompts/doubt-review.md`) plus the **same three appended inputs** codex receives - the PRD content, the diff range (`<base>..HEAD`), and the changed-file list - inlined directly into the Task prompt. (Alice inlines her prompt file the same way; the CLI reviewers write it to a temp file and pass `-f` instead. This is the only delivery difference.)

```
Task tool:
  subagent_type: general-purpose
  model: fable
  description: "Eve doubt-reviews the work against the PRD"
  prompt: |
    {contents of ~/.claude/skills/run-autopilot/prompts/doubt-review.md}

    ---
    ## PRD
    {PRD content}

    ## Diff range
    {base}..HEAD

    ## Changed files
    {changed-file list, one path per line}
```

Do NOT fork or modify `prompts/doubt-review.md` for Eve - the base prompt already prescribes the full output contract, and any future edit to it must apply to all reviewers uniformly (the codex/Claude-fallback paths and Eve share one base file).

Eve's output must satisfy the doubt-review contract exactly (PRD 00016 — no coverage block):
- **FIX / VERIFY / KNOWN** sections, one finding per line; an empty bucket emits its header and `- (none)`.
- The five rubric verdict lines `R1:`-`R5:`, each `pass` or `fail`, emitted verbatim (a rule that cannot be evaluated is `fail`; never omit a line).

If Eve's dispatch fails or times out, treat her as a failed reviewer - she retries Alice-style (the native-Task-reviewer branch of `retry-policy.md`, message the running agent again) and, after the one-retry budget is spent, is marked unavailable while the other reviewers proceed (graceful degradation, per `retry-policy.md`). The failure is legible and distinguishable from a valid empty-findings response; a single failed reviewer does not block the cycle.
