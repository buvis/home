# Discovery: Auto-approve Bounded Warrant Requests

## Classification

Depth: comprehensive | Date: 2026-10-17 | Status: reviewed; two sequenced
PRDs, with seed-enablement gates for A and a use-case prerequisite for B
Source: the first draft of this doc, seeded from the 2026-10-17 session that
revoked the PATH write grants in the Seatbelt profile (buvis `14f93f50`, PRD
00160 question 3), plus the same day's review notes. Legacy discovery layout,
no `idea.md`. Elicitation and review decisions are in the Discovery Log.

## Problem

Every warrant request costs a human-typed PIN, including routine, bounded
operations: one reviewed patch on 2026-10-17 cost three PINs (apply, commit,
push). More operations now sit behind warrant (every write to `~/.buvis`,
`mise install`, `mise reshim`, `claude update`), so the PIN is on its way to
becoming a rubber stamp, the exact failure warrant was built to prevent: a
tired human types the PIN into a decoy, or approves the one request in twenty
that widens the sandbox. Two engines overlap in spirit: **warden**
(claude-warden, TypeScript) parses a shell command into an AST and returns
allow/ask/deny from YAML rules inside the sandbox; **warrant** (`~/bin/warrant`,
Python, PRD 00159) brokers one command to run outside the sandbox after a human
reads it and types a PIN. The user wants bounded requests settled without a
human: by code where the shape is bounded by construction, by a model where
judgement is needed, without giving up what warrant guarantees.

## Requirements

### Must have

1. **Code bounds every verdict.** A request is auto-approvable, by rule or by
   judge, only when it passes the envelope: its resolved executable is one a
   policy rule names (and sits under `trusted_exe_roots`, as `resolve_exe()`
   already requires), its arguments fit the rule's grammar, every path
   argument resolves under the profile-derived writable roots or a root the
   rule names (the buvis git dir for bookkeeping), its cwd does not resolve under an
   agent-writable root, and nothing it names is on the backstop list.
   The profile-derived roots are a candidate set, not proof of permission:
   the envelope also excludes the profile's explicit write denies and
   warrant's own protected files. Executable dependencies, including hooks,
   helpers, imported code and executable configuration, must not load
   agent-writable code. A protected executable or cwd alone is insufficient.
   Preserve required checks such as glean; disabling them is not a remedy.
   An unproven dependency chain waits for the PIN. These are requirements
   for auto-approval; existing broker refusals still apply.
2. **Deterministic fast path.** A rule may carry `decision: allow`, which
   approves without a judge call, only for shapes bounded by construction.
   Seed candidates use separate grammars and activate only after their
   bounds are established:

   - Buvis `add` and `commit`: fixed repository and worktree, at least one
     explicit pathspec, and every selected path inside the envelope.
     Support the established `:(top)` form; ambiguous or unsupported
     pathspec magic waits for the PIN. Check selected paths, including
     deletions and directory contents, rather than a pathspec's text prefix.
     `add -A`, `add -u`, `add --all`, bare `commit` and `commit -a` stay with
     the human. A permitted commit must exclude unrelated staged changes
     and preserve them in the shared index.
   - Buvis `push`: no file pathspec requirement. Permit only a fast-forward
     of local `master` to `origin`'s `master` at the protected configured
     destination. The fixed `master` argument is a refspec; reject other
     caller-selected mappings and options that broaden or force the push.
     Effective configuration must not add refs, tags or destinations.
     This publishes committed history, including human-created commits;
     it does not inherit the add/commit file-path filter.
   - Mise: `mise install` with no tool argument and `mise reshim`, from a
     protected cwd and protected configuration sources. Protected config
     does not mean pinned versions or bounded installer effects: the current
     config uses `latest`, and installation can execute downloaded code.
     Each candidate needs a separate bound for its dependencies and effects;
     until demonstrated, it stays on PIN (open question 7). Neither a judge
     verdict nor a protected cwd supplies that proof.

3. **The judge is a configurable command.** The policy holds the judge's
   argv, env and timeout; its executable resolves like any brokered command.
   It reads the human's view (what `show()` prints) on stdin and returns JSON
   with `verdict` (`yes` or `no`) and `reason`. A rule may carry
   `decision: judge` to route in-envelope requests to it; only a well-formed
   `yes` approves. Before PRD B, name a useful in-envelope operation that
   needs judgement and define when its judge should say yes or no; the
   current seed list supplies no such example (open question 8).
4. **No means PIN.** A `no`, a malformed answer, a timeout, a non-zero exit or
   an unreachable judge leave the request waiting for the human exactly as
   today, with the verdict and reason in the ledger. The agent never sees a
   judge `no` as a rejection.
5. **Rate cap.** At most N judge approvals per rolling hour, and one per
   identical argv and cwd per window (both policy values); past the cap the
   request waits for the PIN. Also cap judge invocations at C per rolling
   hour, counting no, malformed, failed and timed-out calls. Enforce caps
   before invoking or approving, including across restarts and concurrent
   approvers. A pending request receives at most one automatic judge attempt;
   polling or restarting must not reroll a no or failure. Its manual approval
   remains available. Ledger entries distinguish calls from approvals.
6. **Fail closed.** No matching rule, a missing, unreadable or invalid policy
   (unknown key, rule or judge executable under an agent-writable root), an
   engine exception, or a missing judge isolation setting: the request waits
   for the PIN. This fallback applies to automatic evaluation failures;
   requests already refused by the existing broker do not become PIN-eligible.
7. **Every auto-approval is a ledger line** in the shape of a human approval
   plus `decision: auto`, `rule: <id>`, and for judged requests `judge: <id>`,
   `verdict` and `reason` (escaped through `visible()`), so `warrant list` and
   a later audit show what ran without a human.
8. **The approver is undriveable.** It runs outside the sandbox as a resident
   `warrant serve`, accepts requests only from the schema-validated untrusted
   spool and authority only from protected policy and profile sources, and
   starts the judge with a
   configuration home under `~/.config/warrant/`, a protected cwd, no custom
   instructions, no tools, no MCP servers, no hooks and no auto-update.
   The approver may read the spool and inspected request files as untrusted
   data, as `review()` does today. The judge receives that data only through
   the request view on stdin; it must not discover or load files from
   agent-writable roots. Neither process loads code, configuration, hooks or
   custom instructions from those roots. Request text is evidence to assess,
   never authority to change the protected judging instructions.
9. **Shared syntax, separate policy.** Rules use warden's JSON config shape
   (`rules[].command`, `argPatterns[].match`, `decision`) extended with
   warrant-only predicates (paths, cwd, judge), so one mental model covers
   both. The two share no policy file; v1 ships its own matcher (engine
   option b) and keeps the subset consumable by a future
   `warden eval --policy` (option a), so the matcher can be swapped without
   touching the policy.
10. **Tests per rule and per judge.** Each shipped rule carries a one-line
    "why bounded" comment, one positive test and at least two negative tests
    (a boundary path, an extra flag). Envelope tests prove out-of-envelope
    requests never auto-execute, even with a fake judge that always says yes.
    Separately, in-envelope requests routed to the real judge carry hostile
    and benign fixtures classified by the rubric from open question 8:
    hostile cases never yield `yes` across N runs, benign ones do in at least
    M of N. Text alone does not override a deterministic allow rule.
    A test checks the backstop against the profile's explicit write-deny
    forms, including literal, subtree, regex and project-relative cases,
    plus warrant's own files. Unsupported policy/profile forms must not
    silently grant automatic authority. Extend `ProfileCase` in
    `test_warrant.py`; the old mirror test no longer exists.

### Nice to have

- `warrant rules`: list the loaded policy with each rule's bound comment.
- `warrant judge <id>`: run the judge on a pending request and print the
  verdict without executing, for tuning the prompt and the fixtures.
- A per-machine judge example for a machine that may hold an Anthropic API
  key: `claude --bare -p --tools "" --disable-slash-commands
  --strict-mcp-config --json-schema <schema>`, key read from the policy dir.

### Out of scope

- A judge that rejects: `no` never reaches the agent as exit 125.
- A veto window, two-model agreement, or any gate beyond the envelope and the
  rate cap.
- Merging warden and warrant into one product or plugin.
- Replacing the PIN for anything outside the envelope.
- Changes to the Seatbelt profile.
- A `git apply` rule: a patch confined to agent-writable paths needs no
  warrant (the agent applies it inside the sandbox), and one that is not goes
  to the human by construction.
- The portfolio brief nag row (00155 cadence; a separate item).
- Fixing the warrant notify path (PRD 00160 finding; separate).
- A `claude update` rule (open question 1).

## Constraints

- Stdlib-only Python under `/opt/homebrew/bin/python3`, as `~/bin/warrant`
  today (PRD 00159): JSON policy, `subprocess` for the judge, no YAML parser.
- Approver code, interpreter, policy and the judge's configuration home
  resolve outside every agent-writable root (`preflight()` enforces the first
  three today); the profile denies agents reading `~/.config/warrant`.
- The Seatbelt profile does not change: `~/Library/LaunchAgents` and
  `~/.config/warrant` are already outside the write allowlist.
- The policy loader is stricter than `config.json`'s: required keys present
  and no unknown keys (`load_config()` today checks only required keys).
- Judge isolation on the reference backend: `COPILOT_HOME` under
  `~/.config/warrant/`, `-C` a protected directory, `--no-custom-instructions`,
  `--disable-builtin-mcps`, no tool grants, `--no-auto-update`, `--no-ask-user`,
  `disableAllHooks` in that home, `COPILOT_ALLOW_ALL` never set. Any other
  backend must prove the same property: nothing under an agent-writable root
  (`~/.claude`, `~/.codex`, `~/.copilot`, `~/.gemini` included) is read.
- A network judge endpoint authenticates with a secret held in the policy; a
  loopback port alone is spoofable from the sandbox (network and signals are
  allowed, and warden allows `llama-server`).
- Judge calls spend Copilot AI credits on the host's Copilot plan; the rate cap
  limits call volume only when failed calls count too. A hard credit budget
  also needs a per-call usage bound and the selected model's rate; neither
  has been established here (open question 3).
- The agent side (`request`, `wait`), `~/.codex/config.toml` and
  `~/.claude/settings.json` do not change.

## Codebase Context

- **Relevant code**: `~/bin/warrant` (`review()` builds the `Op`, `show()`
  prints the human's view, `decide()` runs review, show, then the PIN,
  `launch()` re-hashes and executes, `record()` writes the ledger,
  `load_config()` loads broker config, `load_profile()` / `write_grants()`
  derive writable roots, `agent_writable()` checks those roots, and
  `resolve_exe()` checks executables); `~/bin/tests/test_warrant.py`
  (unittest, fake site, cheap scrypt, `ProfileCase` for profile parsing);
  `~/.config/warrant/config.json` (the code reads `trusted_exe_roots`,
  `exec_path`, `allowed_env`, `inherit_env`; config contents were not read);
  `~/.config/seatbelt/ai-agents.sb`;
  `~/.claude/warden.yaml` (the rule shape to mirror; warden accepts `.json`
  beside `.yaml`).
- **Baseline verified 2026-10-17**: PRD 00163 replaced the config allowlist
  mirror with profile parsing; `test_warrant_mirror.py` no longer exists.
  The parser deliberately ignores deny forms and skips runtime parameters,
  so its conservative trust check is not an exact auto-approval permission
  check. The new envelope must apply its own deny exclusions.
  Buvis's protected `~/.config/buvis/hooks/pre-commit` invokes glean through
  `~/.agents/skills/glean/scripts/glean.py`, which resolves into agent-writable
  `~/git/src/github.com/buvis/agent-skills/`. That current chain fails
  Must-have 1; the Git seed must preserve glean using protected execution
  dependencies before automatic commits can pass.
- **Conventions**: stdlib only; `Refused` for policy refusals; every
  agent-written string printed through `visible()`; `ponytail:` comments on
  deliberate ceilings; tests named for the rule they enforce; the suite runs
  outside the sandbox with
  `/opt/homebrew/bin/python3 -m unittest discover -s ~/bin/tests -t ~/bin/tests -p 'test_warrant*.py'`.
- **Integration points**: the verdict slots into `decide()` between
  `review()` and `show()`; `record()` gains the auto fields; a new `serve`
  subcommand polls the spool the way `wait_for()` polls results; the policy
  lands at `~/.config/warrant/rules.json`; the judge home at
  `~/.config/warrant/copilot/`; a launchd plist under `~/Library/LaunchAgents/`
  if open question 2 picks launchd.
- **Similar implementations**: warden's `argPatterns` matcher
  (`~/.claude/plugins/cache/buvis-plugins/warden/<ver>/`) for the subset
  semantics; `write_grants()` and `ProfileCase` for profile parsing and backstop
  derivation; the autopilot plugin's `codex-run.sh` and `gemini-run.sh`
  (`skills/use-codex/scripts/`, `skills/use-gemini/scripts/`) for driving a
  CLI model headless; `use-qwen`'s preflight (a real one-token completion) for
  a reachability check.

## Approach

- **Chosen**: hybrid, inside `~/bin/warrant`. A resident `warrant serve` on
  the host polls the spool, builds the `Op` with the existing `review()`,
  evaluates the deterministic envelope against `rules.json`, executes `allow`
  matches through the existing `launch()`, hands `judge` matches to the
  configured judge command (reference: Copilot CLI isolated under
  `COPILOT_HOME`) with the `show()` text on stdin, executes a well-formed
  `yes` under the rate cap, and leaves everything else for the human's
  `approve`. Delivery in two sequenced PRDs: A (envelope, policy loader, seed
  rules, `serve`, rate cap, ledger fields, backstop test) ships value on its
  own once the bookkeeping dependency chain passes Must-have 1. Mise seeds
  stay disabled unless open question 7 is resolved without weakening the
  envelope. B (judge contract, isolated Copilot judge, fixtures, judge ledger
  fields) builds on A and requires the use case and rubric in open question 8.
- **Why**: a wrong `yes` is bounded by code, not by prompt robustness; the
  judge sees only the residue, so credits and latency stay low; no provider
  lock, since the judge is an argv in the policy; everything reuses warrant's
  review, launch and ledger.
- **Rejected alternatives**:
  - Model alone on the human's view: a wrong `yes` can be anything, including
    a profile rewrite.
  - Model alone with hard refusals: keeps the hand-kept denylist the review
    found untestable.
  - `claude --bare` or the raw Messages API as the reference judge: not
    every host allows Anthropic API access; stays a per-machine option.
  - Local llama.cpp as the reference judge: weak tier, and spoofable from the
    sandbox without `--api-key`.
  - Veto window: brings back the waiting and depends on the broken ping path.
    Two-model agreement: double cost for little injection resistance.
  - Cheap or tiered judge models: credits are bounded by the fast path and
    the rate cap instead.
  - Reject on `no`: invites rephrase-until-yes and blocks legitimate work.
  - Lazy check at the next human `approve`: no latency win.
  - `warden eval` as the engine: binary and config under agent-writable
    `~/.claude`, no `--policy` flag.
  - Merging warden and warrant: different trust levels and fail modes.

## Success Criteria

1. Replaying the 2026-10-17 `git apply` and `git commit` requests against the
   seeded policy sends both to the human (they name
   `~/.config/seatbelt/ai-agents.sb` and `~/.config/warrant/config.json`); the
   same day's push qualifies only if its effective refs, destination and
   dependencies satisfy the push rule. With protected dependencies in place,
   a path-limited PRD commit and fixed-destination push auto-approve with no
   human at any terminal, within 10 s; unrelated staged changes survive
   without entering the commit. A hook that loads an agent-writable script
   instead leaves the request on PIN, with no script execution.
2. Deterministic tests prevent auto-execution for boundary paths, forbidden
   pathspec selections, an agent-writable cwd, an extra flag or a bare commit,
   including with an always-yes fake judge. Separate real-judge fixtures use
   in-envelope `decision: judge` requests: rubric-defined hostile cases
   (including injection in reason or file heads) never yield yes across 10
   runs; benign ones yield yes in at least 9 of 10, each within 60 s.
   Real-judge fixture runs collect verdicts without launching commands;
   execution routing is checked with a fake judge and harmless fixtures.
   A boundary filename mentioned only in file contents is untrusted text,
   not itself an out-of-envelope path argument. Deterministic allow tests
   must not expect a different verdict merely because the reason changes.
3. A policy with one unknown key, a rule whose `command` resolves under an
   agent-writable root, or a judge argv that does, is rejected at load and
   every request waits for the human.
4. A judge `no`, a malformed answer, a timeout, a non-zero exit, an
   unreachable judge and a missing isolation setting each leave the request
   pending for the human, with the outcome in the ledger.
5. The (N+1)th judge approval within an hour, and a second identical argv
   and cwd within the window, wait for the PIN. The (C+1)th call is not made
   even when all prior calls failed or said no. Repeated polls and restarts
   do not rejudge a pending request; concurrent approvers cannot exceed the
   caps or execute it twice.
6. With a hook planted in `~/.claude/settings.json`, an MCP server and hooks
   planted under `~/.copilot/`, and an `AGENTS.md` planted in the request's
   cwd, a judged request runs none of them (marker files stay absent).
   Isolation checks must also establish that the judge does not read those
   files; absent execution markers alone cannot prove the no-read requirement.
7. Every auto-approval appears in the ledger as `decision: auto` with `rule`,
   and for judged ones `judge`, `verdict` and `reason`; `warrant list` shows
   it.
8. `test_warrant.py` stays green; new tests live beside it, with backstop
   tests covering the profile's write denies and warrant's protected files.
   A protected cwd with an agent-writable executable dependency remains on
   PIN; mise has no automatic rule until its separate bound is established.

The numbers (10 s, 60 s, 10 runs, 9 of 10) are proposals from this session;
open question 3.

## Risks

- **Judge injection.** The request is text the agent wrote. Mitigations: the
  envelope bounds what a `yes` can do, the judge has no tools, `no` means
  PIN, the hostile fixtures, the rate cap.
- **Isolation drift.** A Copilot CLI update adds a config source outside
  `COPILOT_HOME`. Mitigations: criterion 6 runs in the suite;
  `--no-auto-update` pins the judge's version until the human updates it.
- **Credits.** Judge calls are metered on the host's Copilot plan.
  Mitigations: the fast path for bookkeeping, an invocation cap counting all
  outcomes, one automatic attempt per request, and a ledger call count.
  Approval counts alone do not bound calls or spend.
- **Allowlist creep.** Each rule is a permanent unsandboxed capability.
  Mitigations: per-rule bound comment and negative tests (Must-have 10),
  `warrant rules`.
- **Resident process.** A launchd agent is new infrastructure to own; its
  plist sits outside the write allowlist, so the agent cannot repoint it; a
  crash, a stale process or an expired judge login fails closed (requests
  wait). `warrant list` should say why requests stopped auto-approving.
- **Rule syntax drift.** Copying warden's JSON shape into Python means two
  implementations. Mitigation: keep the subset tiny and test it against
  warden's own fixtures where they overlap; revisit when warden can be pinned
  to a protected policy (engine option a).
- **Recoverability is the wrong axis.** The 2026-10-17 patch was fully
  recoverable and rewrote the sandbox profile; `mise install` is reversible
  and runs downloaded code as the user. The policy reasons about escalation
  (does the command grant more than the sandbox grants), never about undo.
- **Indirect execution.** Protected Git and mise binaries can load other
  code or configuration. Protecting cwd alone does not establish a bound;
  Must-have 1 covers execution dependencies, and unresolved mise effects
  keep its rules disabled. Protected config is not a version or artifact pin.
- **Judge model catalog changes** on a host's plan. An unknown model makes
  the judge fail, which is PIN; the policy value is one line to change.
- **Credit rule.** Memory says never to route Claude models through copilot
  where Claude already serves them. The per-machine judge config honours it:
  on a machine with an Anthropic key the judge is `claude --bare`.

## Open Questions

1. `claude update`: auto-approved by rule, or always human? Carried from the
   first draft; it replaces the binary every session runs under.
2. Resident approver: a launchd agent, or a foreground `warrant serve` the
   user runs in a pane for v1?
3. Numbers: 10 s fast-path and 60 s judged latency, 10 fixture runs with 9 of
   10 benign yes, approval cap N per hour, invocation cap C per hour and the
   identical-argv-and-cwd window. Proposed here; choose the relevant values
   before each PRD. If a hard credit ceiling is required, establish the
   per-call input/output bound and model rate before claiming a spend cap.
4. Judge model default: `claude-opus-5.5` or `gpt-6.1-sol` (credit
   multipliers not checked here).
5. Judge login: the human runs `COPILOT_HOME=~/.config/warrant/copilot copilot login`
   once, or the policy passes `COPILOT_GITHUB_TOKEN` from a file in the
   protected dir?
6. Does an empty `--available-tools` list hide every tool from the model?
   Verify in B's design; `--excluded-tools` is a candidate fallback, not a
   proven equivalent. Do not enable the judge until isolation is verified.
7. **Mise seed-enablement gate:** what bounds installer and reshim effects,
   including executable dependencies, configuration discovery and downloaded
   code? Protected config and no tool argument are insufficient evidence.
   Keep each rule on PIN until its bound is demonstrated; A's bookkeeping
   value does not depend on enabling these candidates. Accepting broader
   installer authority would require an explicit trust decision.
8. **Before PRD B:** name at least one useful operation that passes the code
   envelope but needs model judgement, with a yes/no rubric and representative
   benign and hostile examples. All current concrete seeds are deterministic;
   do not invent a judged capability merely to exercise the backend. A can
   proceed independently; B is not ready for specification without this input.

## Discovery Log

The elicitation entries below preserve the original answers. The final review
entry records corrections; current Requirements and Open Questions take
precedence where those entries differ.

### First pass (2026-10-17, before the review)

#### Approver: code, not a model (reversed at the review, see the decision)

Rejected: a smart-model reviewer that approves when it judges the risk zero.
The request is text the agent wrote: reason, argv, cwd, file heads, the patch.
A model reading attacker-controlled input and deciding is a confused deputy
with a prompt-injection surface the size of the request. A wrong "yes" runs as
the user, outside Seatbelt, with no second gate. `rules/ai-app-design.md`
already settles the shape: when the same input must always yield the same
verdict, code answers. Cost and latency of a model call per request were not
the deciding factor but point the same way.

Accepted in principle, deferred: a model may hold a **veto**, never a key. It
can read the queue, summarize, flag what looks off, and reject. A false reject
costs one re-request; a false approve costs the machine. Asymmetric risk gets
asymmetric authority. Nothing of this ships in v1.

Decision (user, 2026-10-17, review finding 1): the rejection does not stand; a
model may approve. The arguments above stay as the risks the re-elicitation
answered, not as a verdict.

#### Engine: share the syntax, not the policy or the binary

- (a) **warrant shells out to `warden eval`.** Rejected for v1: the binary and
  every config it reads live in agent-writable `~/.claude`, and no flag pins a
  single policy or disables the user and project configs. Viable later once
  warden grows `--policy <file> --no-user-config` and a protected install path;
  file that as a warden change when v1 shows the rule subset is worth sharing.
- (b) **warrant implements a small subset in Python** using warden's JSON config
  shape (warden accepts `.json` beside `.yaml`, so JSON keeps this
  stdlib-only). Accepted for v1: on the order of a hundred lines plus tests,
  a policy at `~/.config/warrant/rules.json`. Corrected at re-elicitation:
  loaded more strictly than `config.json`, whose loader accepts unknown keys.
- (c) **Merge the products.** Rejected: different trust levels and different
  fail modes. Warden fails open where the host ignores allow/ask (Codex), is
  tuned to be generous because Seatbelt caps the blast radius, and keeps its
  config where the agent can edit it. Warrant must fail closed and keep its
  policy where the agent cannot. Universality is already there: sandbox plus
  warrant is agent-agnostic. Warden's remaining gap is non-Claude agents inside
  the sandbox, Seatbelt-bounded and lowest priority.

#### Seed rules (first-pass candidates; Must-have 2 supersedes them)

1. **buvis bookkeeping.** `git -C ~ --git-dir=~/.buvis --work-tree=~ {add,commit,push}`
   with every pathspec under an agent-writable root. Bound: these only record
   what the agent could already change in the worktree; the git dir is
   protected, which is the only reason they need warrant at all. The review
   found the bound vacuous for a bare commit (zero pathspecs) and the `apply`
   clause unreachable; both fixed in Must-have 2 and Out of scope.
2. **mise from pinned config.** `mise install` with no tool argument installs
   what the protected `~/.config/mise/config.toml` names; `mise reshim`
   regenerates shims for installed tools. The review showed the bound fails
   from an agent-writable cwd (a planted `mise.toml` is loaded with no trust
   step); Must-have 2 pins cwd outside agent-writable roots.
3. **claude update.** Replaces the binary every session runs under. Reversible
   by reinstall, but version control over the agent runtime may be something
   the user wants to keep. Undecided (open question 1).

#### Resident approver

`~/bin/warrant serve` polling the spool from a launchd agent, logging to
`~/.config/warrant/`. Rejected: checking rules only when the human next runs
`approve` or `list`, since the agent's `wait` would still block until a human
shows up, which is the latency this whole doc exists to remove.

#### Notification

The failing notify call is a defect in the current deployment, not a design
item (`terminal-notifier exited 5` from every sandboxed session, PRD 00160).
Record it against PRD 00160 or fix it on its own; the auto-approver reduces
the need for notifications but does not remove it.

### Re-elicitation (2026-10-17, after review finding 1)

Depth re-classified comprehensive (problem complexity high: a model inside a
security boundary, competing designs). Brownfield facts stated, not asked:
`claude --bare` exists (skips settings and plugin hooks, CLAUDE.md discovery,
plugin sync and keychain reads; API-key auth only), so a host-side judge can
run without loading anything under agent-writable `~/.claude`; without it a
host-side `claude -p` would run agent-written hooks unsandboxed.

#### Q1: Where does the model sit in the approval flow?
**Answer**: Hybrid. Code bounds, model judges: code decides which requests the
model may judge at all (executable allowlist, paths under agent-writable
roots plus the git dir, cwd not agent-writable, no boundary path); inside the
envelope the model reads the human's view and says yes or no; outside it,
PIN. Deterministic rules may still short-circuit without a model call.

#### Q2: Which carried review findings become envelope requirements?
**Answer**: All four. An agent-writable cwd never auto-approves (requests pass
`--cwd` outside agent-writable roots, `~` works, or wait for the PIN);
bookkeeping needs at least one explicit pathspec, every one under an
agent-writable root, so bare `commit -m`, `commit -a`, `add -A` and `add -u`
stay with the human; the `git apply` rule is dropped; `agent_writable_roots`
is the primary path bound and the boundary list becomes a backstop derived in
a test from the profile's explicit denies plus warrant's own files.

#### Q3: Beyond the code envelope, what catches a wrong model "yes"?
**Answer**: A rate cap only: at most N model approvals per hour and per
identical argv, then PIN. Rejected: a veto window (brings back the waiting
and depends on the broken ping path), two-model agreement (double cost for
little injection resistance), nothing beyond the envelope.

#### Q4: How does the host-side judge reach the model, and at which tier?
**Answer**: Neither offered backend. The judge command must be configurable:
not every host allows Anthropic API access, and buvis runs on
more than one machine. Derived: the judge is an argv in the protected policy;
its executable resolves like any brokered command (`trusted_exe_roots`, not
agent-writable); it reads the request view on stdin and returns a structured
verdict; anything other than a well-formed yes falls to the PIN. Constraint
found while answering: `~/.claude`, `~/.codex`, `~/.copilot` and `~/.gemini`
are all agent-writable, so a CLI judge needs a config-isolated mode (`claude
--bare` has one); a loopback HTTP judge (llama.cpp :8080) is spoofable from
the sandbox (network and signals allowed, `llama-server` warden-allowed), so
a network judge authenticates with a secret held in the policy.

#### Q5: Which backend proves the judge contract in v1?
**Answer**: GitHub Copilot CLI with the host's licensed model. Verified
2026-10-17 from `copilot --help`, `copilot help environment` and one live
call: `COPILOT_HOME` relocates configuration and state, so the judge's
settings, login and logs live under a protected directory instead of
agent-writable `~/.copilot`; `-p -s` runs headless and prints only the
response; `--no-custom-instructions` drops AGENTS.md and related files;
`--disable-builtin-mcps`, `--no-auto-update`, `--no-ask-user`, `--log-level
none` and `-C <protected dir>` complete the isolation; `disableAllHooks` is a
setting in that home; `--model` is per call; an untrusted cwd loads no skills,
plugins, MCP servers or hooks (`COPILOT_ALLOW_ALL=true` is never set). A probe
with those flags and no tool grants answered a one-word prompt correctly;
without `--allow-all-tools` a tool call has nobody to confirm it, and
`--available-tools` / `--excluded-tools` hide tools from the model (empty-list
syntax to pin in design). No structured-output flag: the verdict is JSON the
prompt asks for, parsed strictly. Each call spends Copilot AI credits.

#### Q6: Which model does the policy default to, given credit cost?
**Answer**: A frontier model as the policy default (`--model` is a policy
value; candidates `claude-opus-5.5`, `gpt-6.1-sol`). Volume stays low because
the deterministic rules settle bookkeeping without a model call and the rate
cap bounds the rest. Rejected: a cheap model for every call, a cheap-first
tier with escalation.

#### Q7: What happens when the judge says no, or answers badly?
**Answer**: No means PIN. A no, a malformed answer, a timeout and an
unreachable judge all leave the request waiting for the human exactly as
today; the ledger records the judge's verdict and reason. The judge is a
filter in front of the human, never a rejecter: a false no costs a wait, not
a re-request, and there is nothing to rephrase until it says yes. Rejected:
reject with exit 125, with or without a ping.

#### Q8: How is a non-deterministic judge verified?
**Answer**: Envelope tests plus red-team fixtures. Envelope, rate cap and
fail-closed paths get deterministic unit tests with a fake judge. The real
judge gets a fixture set: hostile requests (injection in reason, argv and
file heads; boundary paths; cwd tricks) that must never yield yes across N
runs, and benign ones that must yield yes in at least M of N; credits per
run are bounded and known. Rejected: golden replay of the three 2026-10-17
requests alone, a manual checklist.

#### Q9: One PRD or two?
**Answer**: Two PRDs, sequenced. A: envelope, policy loader, seed rules,
`warrant serve`, rate cap, ledger fields, backstop test; deterministic and
valuable alone (bookkeeping without a PIN). B: judge contract, isolated
Copilot judge, fixtures, judge ledger fields; depends on A. Rejected: one
PRD, judge-first with no deterministic rules.

#### Inferred, not asked

- Problem validation: a pain hit repeatedly (three PINs per reviewed patch,
  rubber-stamp risk), from the first pass.
- Notification of auto-approvals: ledger only, no ping per auto-approval; a
  ping per approval would rebuild the fatigue this doc exists to remove.
- Risks: derived from the review notes and the brownfield checks; the
  open-ended risk question was skipped.
- Priority: not asked; the backlog review orders it.
- The nine review findings of 2026-10-17 are folded in: Must-haves 1, 2, 7, 9
  and 10, the Constraints section, criteria 1 and 7, the dropped `git apply`
  rule and the nag-row exclusion under Out of scope.
- Contradiction check across Q1 to Q9: none found. The fast path (Q1) is
  what keeps credits low (Q6); the rate cap (Q3) and no-means-PIN (Q7)
  compose; the configurable judge (Q4) is satisfied by the isolated Copilot
  reference (Q5).

### Discovery review (2026-10-17)

All five lenses ran at comprehensive depth. Eight findings: six Blocking,
one Non-blocking, one Question. Seven corrections applied; the missing
judged use case remains open for B. No findings disputed or lenses skipped.
The existing two-PRD split is appropriate; the configurable judge and
separate policy preserve the stated evolution paths.

1. **Integrity, Blocking: indirect execution.** The current buvis pre-commit
   hook executes glean from agent-writable `~/git/src`. The user chose
   protected execution dependencies (option 1), preserving glean; deferring
   all Git automation or adding command confinement were the alternatives.
   Must-have 1 and criterion 1 now make that protection an activation gate.
2. **Coherence, Blocking: Git grammar.** Push has no file pathspec and
   `master` is itself a refspec. Split the seed grammars, bound the effective
   push destination and refs, and require actual selected-path checks for
   add/commit; preserve unrelated staged changes. A generic path-prefix
   rule or removing push would not preserve the intended bookkeeping scope.
3. **Feasibility, Blocking: mise's claimed bound.** The protected config
   contains `latest`; its protection does not bound downloaded code's effects.
   Keep the requested seed candidates conditional on proof, instead of
   assuming broader installer trust or deleting them. Open question 7 records
   the missing proof and PIN fallback.
4. **Coherence, Blocking: caps count successes, costs count calls.** Retain
   approval limits, add an invocation limit counting all outcomes, and prevent
   polling from retrying a pending verdict. Merely removing the spend claim
   would leave repeat calls unbounded; hard credit accounting needs more data.
5. **Coherence, Blocking: no reads versus request inspection.** Allow the
   approver's necessary untrusted-data reads while retaining judge isolation
   and protected code/configuration. Removing inspection loses the human's
   view; banning spool reads makes the resident approver impossible.
6. **Coherence, Blocking: mixed fixture expectations.** Separate envelope
   rejection tests from model-verdict fixtures and harmless execution tests.
   Injection-like text cannot be expected to veto a deterministic allow rule;
   routing all such requests to a model would change the chosen fast path.
7. **Integrity, Non-blocking: stale baseline.** Rechecked the live source:
   profile parsing replaced the config mirror, and tests live in
   `test_warrant.py`. Updated the references rather than restoring the old
   mirror or leaving implementation to discover the mismatch.
8. **Completeness, Question: what needs judgement?** No concrete judged rule
   or decision rubric was elicited. Record this as a prerequisite for B;
   neither invent a use case nor remove the user's model-approval decision.

Evidence: local `~/bin/warrant`, `~/bin/tests/test_warrant.py`, buvis's
`core.hooksPath` and pre-commit hook, glean's resolved path, and the mise
configuration were checked on the review date. Protected warrant config
was not read. Command semantics were checked against the official
[Git push documentation](https://git-scm.com/docs/git-push),
[pathspec glossary](https://git-scm.com/docs/gitglossary),
[Git hooks documentation](https://git-scm.com/docs/githooks), and
[mise configuration documentation](https://mise.jdx.dev/configuration).
No broker commands, judge calls or security settings were changed or tested
by this document review. Surprise-test feedback was not collected;
actionability remains incomplete for B until open question 8 is answered.
