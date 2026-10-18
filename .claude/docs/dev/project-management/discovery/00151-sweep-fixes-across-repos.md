# Discovery: Sweep a Fix Across the Portfolio

## Classification

Depth: standard | Date: 2026-08-27 | Status: elicitation complete
Elicited from the 2026-08-26 seed of the same number. Original source:
`discovery/inbox/skill-ideas-2026-07-14.md` (2026-07-14 transcript sweep; trashed
2026-08-26 once split into per-idea docs).

## Problem

`rules/development-workflow.md` § Bug Fix Discipline asks "Is this mistake
somewhere else also?" after every fix. Nothing enforces it, so the answer is
whatever the session has energy for. The same bug shapes then recur in sibling
repos, and each one pays full price to rediscover them.

## Requirements

### Must have

1. **Skill `sweep-fix`** (verb-led, per the naming convention). Takes a fix
   commit - sha or range, default `HEAD` - and derives the anti-pattern from its
   diff.
2. **Two derivation paths, chosen per fix**: an ast-grep rule when the bug has a
   code shape, an `rg` pattern when it is textual. The report states which was
   used and why, so a bad choice is visible rather than inferred.
3. **Portfolio scope every run**: the gita registry plus the repo you are
   standing in, registered or not. Repos found on disk under
   `~/git/src/github.com/*/*` (the Conventions layout; `~/.buvis` is the
   bare-repo special case in Open Questions) but absent from the registry get
   one gap line in the report.
4. **Read-only everywhere except the current repo.** Fixes land only in the repo
   you are in, only on approval. No writes of any kind into other worktrees.
5. **One report** at `dev/local/audit-results/sweep-{slug}-{date}.md`: per-repo
   hit rows with `file:line`, the derived pattern, and the verbatim
   how-to-proceed block at the end.
6. **Installable guard text**: for structural sweeps the report carries an
   ast-grep rule block in loupe's rule-pack shape, ready to paste. The sweep
   never installs it.
7. **Fix-commit nag**: a `PostToolUse` / `Bash` handler registered in aegis's
   `hooks/hooks.json` (decided at the 2026-08-28 review; not `~/.claude/hooks`
   `dispatch.py`), fires after a `git commit` whose conventional type is `fix`
   and prints one line naming the short sha and the sweep command.
8. **No silent caps**: if per-repo hits are capped, the report states the
   suppressed count.

### Nice to have

- `--dry-run`: print the derived pattern and the repo list, sweep nothing.
- A pattern fingerprint stored per sweep, so a later "seen twice, install the
  rule" promotion has data to stand on.

### Out of scope

- Auto-fixing in any repo other than the current one.
- Installing rules into loupe's pack (report the text, nothing more).
- Repairing the gita registry (report the gap; do not write the CSV).
- **bisect-bug**: test-first git-bisect automation, cut in the same 2026-07-14
  sweep because ddb was the only deep-history repo. Re-check if a second one
  grows history.

## Constraints

- `rg` here is a bash function re-execing the claude binary, not a binary
  (`reference_rg_is_a_shell_function`). A sweep script must resolve it the way
  `hooks/cartographer-echo.py` does (`_resolve_rg()` plus `executable=`) or it
  dies with `FileNotFoundError` - and an empty result is unverified until a
  control term proves the pattern shape works.
- `ast-grep` 0.45.0 lives at
  `~/.local/share/mise/installs/ast-grep/0.45.0/ast-grep`. Resolve it with
  `mise which`; do not assume PATH.
- `PostToolUse` exit 2 cannot block; stderr is fed to the model
  (`reference_posttooluse_exit2_cannot_block`). The nag can inform, never gate.
- Other worktrees may be edited live by the user during a sweep
  (`feedback_subagents_vs_live_worktree`): read-only by construction.
- Both halves are released-plugin-repo work, so product spend, not meta: the
  skill in `agent-skills`, the hook in aegis.
- The skill belongs in `~/git/src/github.com/buvis/agent-skills`, reaching
  `~/.claude/skills` through the `~/.agents` braid. Never edit through the link
  farm. The hook belongs in the aegis plugin repo (`hooks/hooks.json` plus a
  Python handler in `hooks/`) and is live only once aegis is released and
  `/plugin update` has run (`feedback_plugin_prd_not_done_until_released`).

## Codebase Context

- **Registry**: `~/.config/gita/repos.csv`, 26 rows. Already parsed in one line
  by `brief-portfolio/scripts/collect.py:429` (`csv.reader`, `row[0]`). Reuse
  that; do not build a registry reader.
- **Registry gaps, measured 2026-08-27**: `agent-skills`, `claude-agoge`,
  `claude-autopilot`, `claude-loupe`, `agoge-gym`, `calcard-mcp` and `ovcaq` are
  absent, and row 15 points at the `buvis/home` clone rather than the live
  `$HOME` work-tree of the `~/.buvis` bare repo. That is where much of the fix
  traffic lands, so the blind spot is not marginal.
- **Hook host**: aegis `hooks/hooks.json` (installed cache
  `~/.claude/plugins/cache/buvis-plugins/aegis/0.3.2/`) - `PreToolUse` on
  `Edit|Write|MultiEdit`, `Bash` and `Monitor` today, no `PostToolUse` at all;
  handlers are Python files in `hooks/`. `~/.claude/hooks/dispatch.py` `ROUTES`
  stays untouched.
- **Rule-pack shape**: `claude-loupe/rules/ast-grep/{python,rust,javascript,typescript}/rules.yml`.
- **Similar implementations**: `brush` (per-repo hygiene pass), `purge-devlocal`
  (trash-first GC across repos), `brief-portfolio` (portfolio-wide read).

## Success Criteria

- A `fix:` commit made through the Bash tool prints exactly one nag line naming
  the short sha and `/sweep-fix {sha}`; a `feat:` commit prints none. Pinned by a
  test in aegis's hook suite.
- `/sweep-fix` against a seeded fixture bug planted in three repos reports three
  hits with `file:line`, and `git status --porcelain` in the two non-current
  repos is byte-identical before and after.
- A structural sweep's report contains an ast-grep rule block that runs unedited
  via `ast-grep scan --rule {file}`.
- The report names every on-disk repo missing from the registry (seven today).
- The report ends with the verbatim how-to-proceed block.

## Risks

- **Over-general patterns spam findings**: report-first, never auto-fix outside
  the current repo, and state hit counts plus any suppressed count.
- **The rg-as-function trap silently returns nothing**: it killed
  cartographer-echo's gate for months. Resolve `rg` like echo does and self-check
  with a known-present term before trusting an empty sweep.
- **Nag fatigue**: one line, `fix:` only, always naming the sha. If a month of
  nags goes unacted, delete the hook rather than tune it.
- **ast-grep grammar gaps make structural sweeps quietly partial**: the report
  names the languages the rule could not cover.
- **Sweeping live worktrees**: read-only, and no git command that writes.

## Open Questions

- Per-repo hit cap before the report summarizes instead of listing. Suggest 20,
  tune after the first real run.
- Does the nag fire on `fix(scope):` and breaking `fix!:`? Assumed yes; confirm
  at PRD time.
- Is the `~/.buvis` bare repo (work-tree `$HOME`) swept at all? Every pathspec
  there resolves against cwd and needs `:(top)`, so it is a special case the
  registry cannot express.
- **Resolved 2026-08-28**: two PRDs. (A) `sweep-fix` in `agent-skills`; (B) the
  nag in aegis, depending on A only for the command name, and done only when
  released and installed (`feedback_plugin_prd_not_done_until_released`).
- Fingerprint store for the seen-twice promotion (Nice-to-have 2): a
  machine-wide append-only file such as `~/.local/share/agents/sweeps.jsonl`
  (same plane as `metrics/skills.jsonl`), never the per-repo report - reports
  scatter across 26 repos' `dev/local`, so "seen twice" cannot be computed from
  them.

## Evidence (2026-07-14)

Portfolio bugs repeated two shapes across repos: path-resolution assumptions
(buvis pathspecs resolving against cwd, the gemini symlink blindness on
`dev/local`) and string-match false positives (the codex exit-4 "quota" grep
matching codex's own command args).

## Freshness check 2026-08-26

- Still unbuilt: no `sweep-fix` in `~/.agents/skills`, `~/.claude/skills`, or any
  plugin.
- The rule that motivates it is unchanged and still unenforced.
- Both cited bug shapes are still live memories, so the pattern class is real.

## Discovery Log

### Q1: How should a sweep get triggered?

**Answer**: Manual `/sweep-fix` **plus a nag on fix commits**. Manual-only was
recommended on the grounds that skills self-fire ~1/30 on real work
(`project_rules_attach_skills_dont_fire`), but that measurement is the argument
*for* a deterministic trigger, not against one - the skill stays manual and the
hook supplies the reminder the standing rule cannot.

### Q2: Where should the fix-commit nag live?

**Answer**: A Claude `PostToolUse` hook. One install covers every repo, the
dispatcher and its suite already exist, and blast radius outside Claude Code is
zero. Accepted blind spot: commits made by hand in a terminal, or by another
agent, are never nagged. Rejected: a global `core.hooksPath` git hook (silently
overrides any repo's own hooks), per-repo hooks (26 installs, lost on clone), and
a session-start scan (same fatigue, slower).
*Revised at the 2026-08-28 review*: the hook lives in aegis, not the
`~/.claude/hooks` dispatcher (finding 1), accepting the plugin release gate.

### Q3: How should the sweep derive the pattern it hunts for?

**Answer**: **Both, chosen per fix** - ast-grep for shape, `rg` for text. The two
bug shapes in the 2026-07-14 evidence are one of each, so a single mechanism
misses half the class. Accepted cost: two code paths, the model picks between
them, and a sloppy pattern gets amplified across the whole portfolio at once.
Rejected: ast-grep only (blind to config, docs and bad literals), rg only (false
positives are its default failure mode), and a model-judged semantic sweep (breaks
`rules/ai-app-design.md` - code answers when code can).

### Q4: What is the default search scope for one sweep?

**Answer**: **Whole portfolio, always**, with no flag to remember. The scan
itself costs seconds; the real expense is triaging hits, so a narrower default
saves nothing while missing the cross-repo class that motivated the idea.
Accepted: hits arrive from repos you are not working in today.

### Q5: What should a hit in another repo turn into?

**Answer**: **One report plus fixes in the current repo only**, on approval.
Other repos stay read-only rows. Rejected: auto-filing PRDs into every affected
repo's backlog (one loose pattern spams a dozen backlogs with unverified
premises), discovery seeds per repo (five unelicited seeds already exist), and
report-only with no fixes anywhere (leaves the same "someone must act on a file"
gap the rule already has).

### Q6: How should the sweep decide which repos count as the portfolio?

**Answer**: **Registry plus the current repo, and report the gaps.** The
registry stays authoritative, the repo you are standing in is always swept even
when unregistered, and repos on disk but missing from the CSV get named in the
report instead of being silently skipped. Asked after the scan found the registry
seven repos short and pointing at a clone of `home` rather than the live `$HOME`
work-tree. Rejected: registering the missing repos and trusting the CSV alone
(rots again, silently), disk discovery (sweeps forks and playgrounds, drops the
curation other skills depend on), and a second list of extra roots (two sources
of truth is how this gap happened).

### Inferred (not asked - answered by the scan)

- Report location and shape: `dev/local/audit-results/` with a verbatim
  how-to-proceed block, per `feedback_skill_reports_to_audit_results`.
- Repo enumeration: reuse `collect.py`'s one-line CSV read rather than writing a
  registry parser.
- Tooling: `ast-grep` 0.45.0 present via mise; `rg` needs the cartographer-echo
  resolution dance.
