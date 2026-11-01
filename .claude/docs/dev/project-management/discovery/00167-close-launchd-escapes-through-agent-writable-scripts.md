# Discovery: Close Scheduled Escapes Through Agent-Writable Code

## Classification

Depth: comprehensive | Date: 2026-10-18 | Status: specified as PRD 00174
(backlog, 2026-10-19); live deployment remains separate
Seeded from session 523838c3 follow-ups; user instruction 2026-10-18: "all of
them must be recorded as discovery documents that I will go through".
Written from a sandboxed session, read-only: nothing was planted or run to
prove an escape. Every fact below comes from the files named, read on
2026-10-18 between 22:45 and 23:00 local.

## Premise check

**Confirmed, and wider than one script.** The Seatbelt profile lets agents
write `~/git/src` (`ai-agents.sb:121`) and denies only `.git/hooks` and
`.mcp.json` below it (`ai-agents.sb:153-154`). Two jobs then run git or a
script in that tree outside the sandbox, with no human act beyond opening a
shell.

1. **`com.buvis.cellar-sync`** (`~/Library/LaunchAgents/com.buvis.cellar-sync.plist`):
   `StartInterval` 3600, `ProgramArguments` is
   `/Users/bob/git/src/github.com/buvis/cellar/sync.sh`, no sandbox. The
   script is four lines: `cd` to its own dir, `git add -A`, `git commit -m
   "chore: sync"` with `commit.gpgsign=false`, `git push`. An agent can take
   it three ways:
   - rewrite `sync.sh` itself (owner `bob`, mode 755, under `~/git/src`);
   - leave `sync.sh` alone and write `.git/config` in the cellar repo:
     `core.hooksPath` pointing at an agent dir gets around the `.git/hooks`
     deny for `pre-commit` and `pre-push`; `core.fsmonitor` runs on `git
     add`; a `filter.*.clean` driver plus a `.gitattributes` line runs on
     `git add -A`; `core.sshCommand` runs on `git push`. Today the config holds
     only `core`, `remote "origin"` and `branch "master"` (read directly);
   - point the log at a file of its choice. `StandardOutPath` and
     `StandardErrorPath` are `/tmp/cellar-sync.log`, under the
     agent-writable `/private/tmp` (`ai-agents.sb:124`). If launchd follows
     a symlink there, the job appends git's output to the target hourly. That
     output carries agent-chosen file names (`create mode 100644 NAME`, 17,199
     such lines in the 5.3 MB log today). Not exercised; whether launchd opens
     the path with `O_NOFOLLOW` is unknown.
2. **The `gita-pull` shell hook.** Every interactive shell runs
   `~/bin/run-shell-hooks` before the first prompt
   (`~/.config/bash/plugins/shell-hooks.plugin.bash:6-11`). It runs
   `gita pull` once a day (`~/.config/shell-hooks/tasks.yaml:6-8`), in the
   user's unsandboxed shell, across the 28 repos `~/.config/gita/repos.csv`
   lists under `~/git/src`. Each `git pull` reads that repo's agent-writable
   `.git/config`, so the same `core.hooksPath` (`post-merge`),
   `core.fsmonitor` and `core.sshCommand` routes apply, once a day, in up to 28
   repos.

Checked and clean:

- The other 12 LaunchAgents run binaries under `/Applications`,
  `/opt/homebrew`, `~/Library/Application Support/<vendor>` or `~/bin`
  (`rg` over every `<string>/` in the dir). None of those is an agent write
  root. `app.getmoshi.moshi-hook` runs `~/.local/bin/moshi-hook`, read-only
  to agents since 2026-10-17.
- `com.buvis.herdr-relay` runs `~/bin/herdr-relay`, which agents cannot
  write. Its log is `~/Library/Logs/herdr-relay.log`, an agent write root
  (`ai-agents.sb:184`), so it has the same open question as the cellar log.
  The relay prints only a fixed start line and Python tracebacks, so it
  matters less.
- The herdr agent-activity publisher (pid 86939) runs
  `~/.config/herdr/plugins/github/resilient-software.agent-activity-*/bin/cli.mjs`
  under mise's node. Neither path is an agent write root.
- syncthing's live config is `~/Library/Application Support/Syncthing/config.xml`,
  not agent-writable. `~/.config/syncthing` links into the cellar repo but
  holds only a notes file (`hawking.buvis.net.md`).
- The shell-hooks task files are `~/.config/shell-hooks/tasks.yaml`
  (tracked, not agent-writable) and `~/.local/.config/shell-hooks/tasks.yaml`
  (absent; `~/.local/.config` is not an agent write root). Their state dir
  `~/.local/state/shell-hooks` is agent-writable (`ai-agents.sb:185`), but
  it holds only timestamps and a lock pid. An agent can make a task skip or
  run early, not change what it runs.
- `crontab -l` is blocked by warden, and `/usr/lib/cron/tabs` is unreadable
  from the sandbox. So cron is **unverified**.
- autoclaude goes through run-agent
  (`~/.config/bash/plugins/development.plugin.bash:401`), and so do the
  `claude`, `codex`, `copilot`, `kiro` and `pi` aliases
  (`~/.config/bash/aliases/development.bash:2-10`).

## Problem

The profile and warrant assume that whatever an agent writes is run only
inside the sandbox, or only after a human approves it. Two scheduled jobs
break that: an hourly launchd job and a daily shell hook run code and git
config from agent-writable repos as the unsandboxed user. A hostile or
prompt-injected agent needs one write and at most an hour to run anything
with the user's full rights: the 1Password-backed ssh, the Keychain,
`~/.config/gh` and warrant's PIN hash. That makes the herdr fix of PRD 00160
Q2 moot.

## Context: the wider class (not in scope here)

The same shape exists where a human act triggers the run, not a schedule:

- **mise trust.** `~/.bashrc:74` runs `mise activate bash`. mise trusts 119
  configs listed as symlinks in `~/.local/state/mise/trusted-configs`. Agents
  can write that dir, and most of the targets are repos under `~/git/src`. A
  `cd` into one in an unsandboxed shell runs the repo's `mise.toml` env and
  hooks.
- **Any unsandboxed tool run in an agent-written repo**: `make`, `npm run`,
  `direnv`, an editor's workspace config, a plain `git status` (which reads
  `core.fsmonitor`).
- **Agent CLIs started outside run-agent** (a plain `command claude`, the
  Claude desktop app if it reads `~/.claude/settings.json`) load hooks and
  settings from `~/.claude`, `~/.codex` and similar dirs that agents can
  write. Whether the desktop app does this is unverified.

These need a different fix (trust is a human act, not a schedule) and
belong in their own discovery. This one covers only code that runs with no
human act.

## Requirements (proposed)

### Must have

1. **cellar-sync runs inside the sandbox.** The plist starts the job through
   `~/bin/run-agent` with `WorkingDirectory` set to the cellar repo, so
   `sync.sh`, the repo's `.git/config` and every helper run under
   `ai-agents.sb`. The commit and push use the agent identity and key that
   run-agent already sets (`GIT_SSH_COMMAND` with `~/.ssh/agent_github`).
   Whatever an agent plants then runs with an agent's rights, not more.
   This guarantee includes the launcher's bootstrap: current run-agent runs
   `git rev-parse` in the caller's cwd before `sandbox-exec`. Before enabling
   either scheduled job, establish that bootstrap executable resolution,
   environment and configuration discovery cannot execute agent-written code
   outside the sandbox. A protected launcher file alone is insufficient.
2. **gita-pull runs inside the sandbox.** The task's `run:` line becomes a
   run-agent call with a fixed project dir, so the daily pull runs each
   repo's git config sandboxed. run-agent refuses `$HOME` as the project dir,
   so the line names one (see Open Questions).
3. **Job logs live outside every agent write root**, for every LaunchAgent
   the user owns (cellar-sync, herdr-relay). Or, if a host check shows
   launchd will not follow a symlink at `StandardOutPath`, record that and
   leave the paths alone.
4. **A test pins the rule.** A check in `~/bin/tests` parses every plist in
   `~/Library/LaunchAgents` and every `run:` line in the shell-hooks task
   files. Execution checks cover script operands, executable configuration
   (including Git config/helpers), and the launcher bootstrap, not just the
   first executable's path. Agent-writable execution dependencies must run
   only after sandbox entry. Check log paths independently: launchd opens
   them outside the child sandbox, so run-agent never exempts a writable log.
   Use roots from `warrant.load_profile` (PRD 00163), documenting its skipped
   runtime project grant and conservative treatment of denies; it is not a
   complete permission oracle. Unsupported dependency chains remain
   unverified rather than passing on the absence of a direct writable path.

### Nice to have

- `sync.sh` and the cellar plist copy are tracked in buvis, so the job
  survives a new machine. Today only the cellar repo holds them.

### Out of scope

- The human-triggered class above (mise trust, tools run in agent-written
  repos, agent CLIs outside run-agent).
- Cron, until a host `crontab -l` shows any entries.
- Making the cellar repo or `~/git/src` read-only to agents: that ends agent
  work in repos.

## Constraints

- `~/bin`, `~/.config/shell-hooks` and `~/Library/LaunchAgents` are not
  agent-writable. Deploy goes through warrant: a `cp` request for each file,
  then `launchctl bootout` and `bootstrap` for the changed job.
- Nested `sandbox-exec` fails from a session (exit 71), so a host check
  is the only way to prove that run-agent works under launchd and from the
  shell hook.
- run-agent needs `HOME` and a non-HOME cwd. It was built for interactive
  use: a launchd start without a tty, a login shell or `HERDR_*` env is
  untested.

## Codebase Context

- **Relevant code**: `~/Library/LaunchAgents/com.buvis.cellar-sync.plist`;
  `~/git/src/github.com/buvis/cellar/sync.sh` (also `sync.ps1`,
  `cellar-sync.service`, `cellar-sync.timer` for other OSes, and the repo's
  own plist copy); `~/bin/run-shell-hooks`; `~/.config/shell-hooks/tasks.yaml`;
  `~/bin/run-agent` (the HOME refusal at lines 42-45, the agent git
  identity at 64-81, per discovery 00161/PRD 00165).
- **Conventions**: warrant-brokered deploys with the source hashed;
  `~/bin/tests/test_*.py` loaded with `SourceFileLoader`; profile roots from
  `warrant.load_profile`.
- **Integration points**: the plist `ProgramArguments`, `WorkingDirectory`
  and log keys; the `gita-pull` `run:` line.
- **Similar implementations**: `com.buvis.herdr-relay` (2026-10-18) is a
  user LaunchAgent deployed through warrant. Its program lives in `~/bin` for
  this exact reason.

## Success Criteria

- Isolated representative repository fixtures exercise the cellar-sync and
  gita-pull launch paths. A marker helper records that it ran under confinement
  and that an attempted read of a known denied fixture path failed; it must
  not copy or print secrets. Do not alter live repository config for this test.
- cellar-sync still commits and pushes hourly. The commits read `Agent ran by
  Tomáš Bouška`.
- The pinning test fails on today's plist and passes after the fix.
- Isolated host fixtures establish that malicious repository configuration
  and executable-resolution inputs cannot execute during launcher bootstrap.
  Do not plant payloads in live repositories or run escape commands.
- A sandboxed job with an agent-writable launchd log still fails the log
  check unless the documented no-follow host qualification applies.

## Risks

- **The cellar push key.** The agent key must have write access to
  `buvis/cellar` on GitHub. If it does not, the push fails each hour and the
  backup stops. Check with one host run before the switch.
- **gita pulls private repos the agent key cannot read.** Those pulls would
  start to fail. The task output shows each failure, and `run-shell-hooks`
  reports a failed task on every shell start until a run exits 0.
- **A silent backup gap.** If run-agent fails under launchd, the job dies
  every hour into a log nobody reads. Mitigation: the first run happens by
  hand through warrant, and its output is checked.
- **This narrows, it does not close.** The human-triggered class above stays
  open, so a hostile agent can still wait for the user to `cd` into a
  trusted repo.

## Decisions and qualification gates

- User confirmed on 2026-10-18: preserve both hourly cellar-sync and daily
  gita-pull inside the agent sandbox; cellar commits use the agent identity.
- Use the cellar repository as the fixed non-HOME working directory for the
  gita-pull wrapper. This is an implementation default, not another user answer.
- Keep human-triggered tools outside this PRD. Cron remains unverified until
  host inventory is available; the known scheduled jobs remain actionable.
- Qualify launcher bootstrap, repository access and log handling before live
  activation. Implementation delivers candidates and automated qualification
  tools; live deployment is a separate operational step.

## Discovery Log (2026-10-18)

### Q4: Should cellar-sync and daily gita-pull both continue inside the sandbox?
**Answer** (user, 2026-10-18): yes. The question explicitly included the agent
commit identity and launcher/repository-access qualification.

### Q1: Is the sync.sh rewrite the whole hole?
**Answer** (from the profile and the repo, not asked): no. The `.git/hooks`
deny is the only git guard, and `core.hooksPath`, `core.fsmonitor`,
filters and `core.sshCommand` in `.git/config` get around it. So protecting
`sync.sh` alone (moving it to `~/bin`) leaves the job open. That is why (a)
sandboxes the whole job.

### Q2: Are other scheduled jobs affected?
**Answer** (from all 13 LaunchAgents and the shell-hooks files): yes, one,
the daily `gita pull` from the user's shell. Two log paths (`/tmp`,
`~/Library/Logs`) carry an unverified symlink risk. Cron is unverified.

### Q3: Does the herdr agent-activity publisher run agent-writable code?
**Answer** (from `plugins.json` and the process list): no. It runs from
`~/.config/herdr/plugins`, which agents cannot write.

## Next step

Create the implementation PRD from the recorded scheduling decision. Live
activation remains a separate host operation through warrant.

## Discovery review (2026-10-18)

All five standard-depth lenses ran. F2 (Completeness, Blocking) adds the
pre-sandbox bootstrap requirement; F3 (Coherence, Blocking) separates
dependency and log checks and states the parser's limits. Both use option 1
from the review decision summary. Evidence: `~/bin/run-agent` performs Git
discovery before sandbox entry, and the premise already names indirect Git
execution. No escape was exercised and no schedule or profile was changed.
Open Questions 1 and 2 remain actual scheduling decisions, not authorization
to deploy from this review.

## PRD coverage check (2026-10-18)

PRD created: yes, [00174](/Users/bob/.claude/docs/dev/project-management/prds/backlog/00174-confine-scheduled-repository-jobs-v1.md) (backlog), saved 2026-10-19.
The earlier no-match audit was superseded by the requested PRD creation.

### Elicitation refresh

Elicitation active. Live reads confirm that the cellar plist executes sync.sh directly, the shell task runs gita pull, and run-agent performs git rev-parse before sandbox entry. The user confirmed preserving both jobs inside confinement. This records the requirements decision; live activation remains separate. Keep bootstrap qualification, credential access and log-path checks as acceptance gates; keep human-triggered tools outside this scope.

These are code-derived findings and planning defaults, not new user answers
or a new discovery-review pass. Existing Discovery Log answers remain valid.

Depth raised to comprehensive for this elicitation: clear requirements,
cross-cutting scope, shared launcher impact, and confinement design choices.
The earlier review remains a historical standard-depth review.

Resolved: preserve both scheduled jobs inside the agent sandbox, as confirmed
by the user. Bootstrap and repository-access qualification remain required.

## PRD creation (2026-10-19)

Specified as [00174](/Users/bob/.claude/docs/dev/project-management/prds/backlog/00174-confine-scheduled-repository-jobs-v1.md). The user requested creation of the missing PRDs.
The earlier elicitation and review entries remain historical evidence.
The PRD records final authoring defaults, dependency ordering and scope.
Implementation uses an isolated checkout and headless acceptance checks;
live deployment and host-only operational steps remain separate.
Template, guess-density and grounding gates passed before saving.

The user explicitly confirmed sandboxing both scheduled jobs.
