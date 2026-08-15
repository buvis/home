# Codex Implementor Mechanics

Extracted verbatim from SKILL.md step 3 (2026-08-09; situational: consulted only
when the codex rung interception can fire). SKILL.md § Codex rung interception
decides WHETHER codex dispatches; this file owns HOW — the batch health probe,
the dispatch checklist, and the hook-gate notice. Read it in full before the
first codex probe or dispatch of a batch.

## Codex batch health probe

Same placement and the same batch scope as the qwen preflight — one probe
decides the codex rung for every task in the batch:

```
state.codex_probe = {
  "batch_id":   "<state.batch.id, or \"no-batch\">",
  "verdict":    "healthy" | "unhealthy",
  "backend":    "codex" | "copilot",
  "detail":     "<one-line cause on unhealthy, else null>",
  "checked_at": "<ISO 8601>"
}
```

**Batch-scope check, before any read or write** — the same lazy-reset idiom
`qwen_breaker` already uses: compute the effective batch id
`(state.batch.id // "no-batch")` and compare it to `codex_probe.batch_id`.
Mismatch or field absent → re-probe and overwrite the slice. Match → reuse the
cached verdict, never re-probe.

**The probe must EXERCISE TOOL USE, not just completion.** Dispatch it exactly
like a real implementor run:

```
Bash (run_in_background: true):
  ~/.claude/skills/use-codex/scripts/codex-run.sh -a \
    -d <realpath of the repo's dev/local> \
    -f <abs tmp prompt file> -o <abs tmp out file>
then: TaskOutput(task_id, block=true, timeout=300000)
```

`-d` is **mandatory on the probe**, not conditional: the probe artifact lives
under `dev/local/`, which in this repo is a symlink outside the workspace.
Under `--sandbox workspace-write` a write there resolves outside the writable
root and is denied, so a probe without `-d` returns `unhealthy` on every batch
in `~/.claude` and the rung would never fire.

Prompt file contents: the TOOL-GATE NOTICE block from § Hook interaction
verbatim, followed by these three lines with `<nonce>` substituted (a fresh
per-probe value, e.g. `<batch_id>-<uuid4>`):

```
Create the file dev/local/tmp/codex-probe-<nonce>.txt containing exactly: <nonce>
Then run: git status --porcelain dev/local/tmp/codex-probe-<nonce>.txt
Reply with the single word: done
```

The notice is required for the same reason every real dispatch carries it: the
probe performs exactly the two actions the gate intercepts (first `Write` to a
path, first `Bash` of the session).

Verdict is `"healthy"` iff ALL of: the helper exited 0, the `-o` file is
non-empty, AND `dev/local/tmp/codex-probe-<nonce>.txt` exists on disk with
content equal to `<nonce>`. Delete the file after the verdict is written.
**The nonce is load-bearing:** a fixed filename would still be on disk from a
previous batch (`dev/local/tmp/` is GC'd only at 7 days), so a fully
hook-blocked run — exit 0, a non-empty `-o` explaining the deny, and last
batch's leftover file — would satisfy every condition and report `healthy`.

**Why a tool-less probe is rejected.** A prompt like "reply with the word ok"
invokes zero tools, so it returns `"healthy"` in exactly the state that kills a
real run. Measured, not hypothetical: a codex reviewer in this repo died on
`Command blocked by PreToolUse hook: [Fact-Forcing Gate]`, retried until its
run was exhausted, and emitted no findings — while a completion probe would
have reported perfect health. Same trap the qwen stack taught one layer up.

**Watchdog and cleanup (no new halt class).** Background-dispatched with a
`TaskOutput` deadline like every other helper-script call — never a bare
foreground CLI call, the canonical way to hang an unattended session. A timeout
return is verdict `"unhealthy"`, `detail: "probe_timeout"`, followed by
`TaskStop` on the probe task so it cannot outlive the decision. **300s, not
120s:** the probe must survive two one-shot gate denials (restate facts, retry)
plus a final reply — five-plus model round trips, against the qwen preflight's
~2 min budget for a single 1-token completion. A `probe_timeout` is fail-safe
(rung off, batch continues, no halt) but indistinguishable from real
ill-health, so the batch-report probe-verdict line is the signal to re-tune it.

**Backend check.** `codex-run.sh` silently falls back to `copilot` when `codex`
is not on PATH, and a premium Copilot model once burned 25% of monthly Copilot
quota in one run — the same quota the UI reviewer lens runs on. A
cost-reduction rung that silently drains the UI reviewer inverts its own
premise. Record the resolved backend (`command -v codex`) in
`state.codex_probe.backend`; `backend == "copilot"` is verdict `"unhealthy"`,
`detail: "copilot_fallback_not_authorized_for_implementor"`.

**No exit-4 clause.** `codex-run.sh` has no exit 4 and writes no
`codex-review-last.jsonl` — both belong to
`run-autopilot/scripts/codex_review_run.py`, a wrapper the implementor path
does not use. The real empty-output signal for this helper is its own "codex
exited 0 but wrote no output" warning, already covered by the non-empty `-o`
condition.

**On `"unhealthy"`** — every codex interception is skipped for the rest of the
batch; affected tasks take the Claude implementor the table already named, with
**no** escalation stamp (infra semantics).

## Codex dispatch

Reuses `use-codex/references/dispatch-contract.md`, whose § Implementor-mode
divergence records the three rules this path departs from (exit-code trust,
contract-level retry, the `-a` grant) — that file wins on disagreement, so read
the departures there, not here:

- **No-edit probe: before-capture.** Immediately before this background Bash
  dispatch, capture porcelain for the task's own file slice — never the whole
  worktree, so a concurrent user edit elsewhere cannot mask this arm:
  `git --git-dir=<bare-git-dir> --work-tree=<work-tree> status --porcelain -- <file slice>`;
- background Bash, never Agent-wrapped (era invariant: a subagent that shells
  out to a CLI hangs);
- `-f <prompt file>` and `-o <output file>`, absolute paths;
- `TaskOutput(task_id, block=true, timeout=600000)` as the watchdog;
- **No-edit probe: after-capture.** Immediately after `TaskOutput` returns,
  before step 4 hands off, capture porcelain again with the same command and
  file slice. Latch the before/after comparison as `codex_no_edit` in the
  attempt record — step 5.5 reads only this latched flag and never re-runs
  `git status`. A non-zero exit on either capture is INDETERMINATE, not "no
  change": do not latch `codex_no_edit`; record the exit code in
  `codex_no_edit_probe_exit` instead and continue through the capability path
  normally;
- completion judged by the `-o` file plus the step-5.5 test gate — **never by
  exit code alone**;
- **edit-enabled sandbox: `-a` (`--sandbox workspace-write`), never `-y`.**
  `-y` maps to `--dangerously-bypass-approvals-and-sandbox`, i.e. no sandbox at
  all; granting that to an unattended autonomous implementor is unbounded write
  access for no added capability, and the dispatch contract requires an
  explicit calling-skill grant before any unattended high-impact flag. **This
  bullet is that grant, and it covers `-a` at this rung only** — never `-y`,
  and never a reviewer dispatch.
- **`-d <realpath of dev/local>`** whenever the task's file slice includes a
  `dev/local/` path: that path is a symlink outside the workspace here and CLI
  backends cannot follow it without `--add-dir`. Omit it otherwise, keeping the
  sandbox as narrow as the task requires.
- **On a `TaskOutput` timeout, kill before falling back.** `TaskStop` the codex
  background task and verify it is gone BEFORE dispatching the Claude
  fallback, then capture `git status --porcelain`. An orphaned
  `--sandbox workspace-write` codex keeps write access to the very files the
  Claude implementor is about to edit; without the kill, its late writes either
  get swept into that commit or land as unexplained foreign paths.
- **Hook-coverage delta**: this dispatch runs under a weaker `Bash`-hook set
  than a Claude implementor — see `model-ladder.md` § Codex rung ("Hook
  coverage").

## Hook interaction

Codex's tool calls are gated by this host's own PreToolUse hooks, and this is
the single largest execution risk in the rung: `~/.codex/hooks.json` registers
PreToolUse hooks on codex's `Edit|Write|MultiEdit` and `Bash` matchers; the
fact-forcing gate denies the FIRST `Edit`/`Write` to each distinct `file_path`
and the FIRST `Bash` command of a session, and its deny text tells the agent to
use Grep/Glob — tools codex does not have and which do not exist in this build
at all. Observed consequence: a codex design reviewer burned its entire run
retrying blocked commands and returned nothing.

The gate is one-shot per path, so a run that understands it can proceed. Every
codex implementor prompt therefore ends with this block:

```
TOOL-GATE NOTICE. This host runs PreToolUse hooks on your Edit/Write/Bash calls.
A deny message beginning "[Fact-Forcing Gate]" is a ONE-SHOT gate, not a refusal:
state the facts it asks for once, in plain text, then retry the IDENTICAL
operation, which will then be allowed. Never retry more than once per operation
and never loop. If a deny message names a preferred tool you do not have
(Grep/Glob), use `rg` via Bash instead. If an operation is denied twice, stop and
report the deny text verbatim as your result rather than continuing to retry.
```

This is a prompt-level mitigation for a host-level policy, so it is best-effort
by construction — which is why the no-edit infra arm (`model-ladder.md` § Codex
rung) exists as the backstop: if the notice fails, the run is classified infra,
falls back to Claude at tier, and costs one wasted dispatch rather than a false
capability verdict or a stalled loop.
