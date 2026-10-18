# Discovery: Put Config Maintenance on a Calendar

## Classification

Depth: minimal | Date: 2026-08-28 | Status: decisions resolved, ready for create-prd
Seeded 2026-08-26 from `discovery/inbox/skill-ideas-2026-07-14.md` (2026-07-14
transcript sweep; source trashed 2026-08-26 once split into per-idea docs). Full
elicitation skipped by the seed's own judgement; the two open questions it left
were answered directly on 2026-08-28 (see Discovery Log).

## Problem

The maintenance tooling already exists and nothing invokes it on a schedule. The
audits run when someone remembers, which means they run after the drift has
already cost something. The 2026-07-14 sweep looked for a maintenance skill gap
and found none - the gap is a cadence, not a capability.

## Requirements

Added at the 2026-08-28 review, derived only from the Discovery Log below.

### Must have

1. **No new skill.** One nag row per audit in `brief-portfolio`, seven today:
   `audit-filesystem`, `audit-context`, `audit-config`, `audit-authoring`,
   `audit-sessions`, `audit-mcp-health`, `purge-devlocal`.
2. A row turns red when the last run is older than its horizon (30d / 90d per
   the Cadence decision below), shows "never" when no run is recorded, and
   names the command to run.
3. No new interactive step: the rows are read-only output of the existing
   monthly brief.

### Out of scope

- Running any audit from the brief.
- A cloud routine via the `schedule` skill, or a local launchd job (rejected
  below).
- Automating `purge-devlocal`, or shortening its idle horizons (the deferred
  hybrid).

### Success Criteria

- A unit test on the row state at ages 0, horizon-1 and horizon+1 days, and
  with no run recorded, passes for both horizons.
- The rendered brief shows one row per audit with its command name.
- No prompt or question is added to the brief run.

## Evidence (2026-07-14)

claude-checkup already ships `audit-filesystem`, `audit-context`,
`audit-sessions`, and `audit-authoring`; `purge-devlocal` GCs working docs;
`brush` covers repo hygiene and nags at 30 days. One hand-run cleanup that day
reclaimed ~46 MB of stale plugin versions and archived 9 legacy project dirs -
work nothing would have scheduled.

## Freshness check 2026-08-26

- All named audits still ship, plus `audit-mcp-health` and `audit-config`.
- The original chain named a `check-links` step; it shipped instead **inside**
  `purge-devlocal` as the pre-trash reference check (PRD 00081), so the chain is
  one step shorter than proposed.
- `brief-portfolio` now surfaces the meta-budget share monthly, so a nag row has
  a proven host.
- Still not scheduled: no cron or routine runs any of it.

## Risks

- An unattended audit that asks questions stalls (`WARDEN_UNATTENDED` class of
  problem). A scheduled run must be report-only, never interactive.
- If the deferred hybrid ever automates `purge-devlocal`, it would trash while a
  loop may be mid-flight; its own idle horizons handle this, and they must not
  be shortened. Moot while the host is a nag, not a run.

## Discovery Log (2026-08-28)

### Host: a `brief-portfolio` nag row

A row goes red when an audit's last-run stamp ages past its horizon, exactly like
brush's 30-day nag. The host is proven, already runs monthly with the meta-budget
share, and reads local files by construction. Accepted: a nag is a reminder, not
a run, so drift still accrues between the row turning red and the audit being
performed.

Rejected:

- **A cloud routine via the `schedule` skill.** Those routines execute as cloud
  agents, which cannot read `~/.claude` on this machine - `audit-filesystem` and
  `audit-context` would run against an environment that lacks the thing they
  audit. This kills the seed's first-named option outright.
- **A local launchd job running `claude` headless.** It would genuinely execute,
  but it is new infrastructure to own and an unattended run that hits a question
  stalls - the `WARDEN_UNATTENDED` failure class this doc already names as a risk.
- **A hybrid** (nag rows for audits, a local job for `purge-devlocal`). Deferred,
  not dismissed: the GC is trash-first with its own idle horizons and needs no
  decisions, so it is the one piece that could safely automate later.

### Cadence: by drift rate, not one clock

- **30 days**: `audit-filesystem`, `purge-devlocal`. Disk and `dev/local` drift in
  weeks - one hand-run reclaimed ~46 MB of stale plugin versions and archived nine
  legacy project dirs. `purge-devlocal` is a per-repo row like brush's, stamped
  by the newest `dev/local/.trash/<date>/` directory in that repo (the GC's own
  trash-first artifact), not `skills.jsonl`.
- **90 days**: `audit-context`, `audit-config`, `audit-authoring`,
  `audit-sessions`, `audit-mcp-health`.

Accepted: both horizons are guesses with no measurement behind them, and one set
too long hides drift while the row looks green. Rejected: monthly for all seven
(up to seven red rows a month becomes wallpaper, and the response degrades to
clearing rows), quarterly for all (the fastest-drifting item gets the slowest
response), and a rotating one-audit-per-month row (never wallpaper, but an
individual audit comes round barely twice a year).

### Stamp source: `skills.jsonl`, not an audit report

Resolved at the 2026-08-28 review. Verified: `audit-filesystem`, `audit-context`
and `audit-config` write no `audit-results` report and no `generated:` line, so
the brush pattern has no source without a claude-checkup change (second repo,
release-and-install gate). `~/.local/share/agents/metrics/skills.jsonl` already
records one `{skill, ts}` row per invocation via `track_skills.py` (plugin
skills namespaced, e.g. `claude-checkup:audit-filesystem`; `purge-devlocal`
unnamespaced), and `brief-portfolio/scripts/collect.py:242` already parses it.
The audit rows use the newest `ts` for that skill. Accepted: a run that was
invoked but abandoned still counts, and the log records no repo (hence the
per-repo `purge-devlocal` row reads `.trash/` instead).

## Open questions

- Does a red row link to the command, or run it on click? The former is the
  smaller build.

## Bookkeeping from the same 2026-07-14 sweep

Two ideas were dropped on 2026-08-26 rather than split into docs; recorded here
so they are not re-proposed from scratch:

- **debrief-batch** (batch autopsy skill): superseded by `autopilot render
  report` plus `review-batch`, which now render cycles, loop metrics, the
  deferred ledger, and `attempts.jsonl`. The only piece still missing is $/PRD.
- **prep-repo** (make a repo batch-ready): composed of skills that no longer
  exist - `verify` is gone and `sort-agent-setup` is archived - and `brush`
  covers repo hygiene.

## Next step

Host, cadence and stamp source are decided. Ready for `/create-prd` - one PRD
adding drift-rate nag rows to `brief-portfolio`, with the one open question
above resolved during PRD creation.
