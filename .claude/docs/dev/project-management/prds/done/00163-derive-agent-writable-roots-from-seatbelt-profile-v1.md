---
default_model: opus
model_tier_rationale: broker trust code where a parser misread silently widens trust; no exact final text is given for the parser, and deploy is a human warrant act
design: skip
eligibility: /usr/bin/false
---

# Derive agent-writable roots from the Seatbelt profile

Source: discovery 00162
(`docs/dev/project-management/discovery/00162-derive-agent-writable-paths-from-seatbelt-profile.md`),
premise confirmed 2026-10-17. Lane: hand-built in a sandboxed or attended
session like PRDs 00159 and 00160; the eligibility field keeps the unattended
drain from picking it, since every deploy target sits outside the sandbox write
allowlist and needs a human.

## Problem

`~/bin/warrant` decides "could an agent have written here?" from two keys in
`~/.config/warrant/config.json`, `agent_writable_roots` and
`agent_writable_globs`, which are a hand copy of the `(allow file-write* ...)`
forms in `~/.config/seatbelt/ai-agents.sb`. The profile is the only thing
`~/bin/run-agent` hands to `sandbox-exec`, so it alone decides what agents can
write. PRD 00160 added a drift test (`~/bin/tests/test_warrant_mirror.py`),
which runs only on the host and only when someone runs it; between a profile
edit and that run, `approve` trusts a stale copy. Two files encode one fact and
the broker trusts the copy.

## Solution

The human side of warrant (`list`, `init`, `approve`) reads the profile at
startup, keeps every top-level `(allow file-write* ...)` form, turns each
`subpath` or `literal` filter into a resolved root (with `_HOME` replaced by
the resolved home, as run-agent passes it), and refuses to broker on any
filter shape it cannot read, on a missing or unreadable profile, and on a
profile with no write grant at all. `Site` carries the roots;
`agent_writable()` tests a resolved path against them by equality or
ancestry, which is what Seatbelt `subpath` does on real paths. Per-session
parameters (`_PROJECT_DIR`, `_TMPDIR`) are skipped, as the mirror skipped them;
`_TMPDIR` lands under `/private/var/folders/`, which the profile grants
literally. Deny carve-outs are ignored on purpose: honoring them could only
make warrant trust more. `preflight()` also refuses when the profile or
run-agent lies under a grant, since such a profile lets an agent rewrite its
own sandbox. The two config keys go, `fnmatch` goes with the glob branch, and
the mirror test is deleted: its parser moves into warrant and its cases become
parser tests that run inside the sandbox too, because the profile is readable
there. Decided in discovery 00162: the profile path is a constant, not a config
key; regex grants fail closed until one exists (none since buvis `14f93f50`);
the `_PROJECT_DIR` gap stays documented and out of scope.

## Requirements

### Must have
- `agent_writable()` answers from roots parsed out of
  `~/.config/seatbelt/ai-agents.sb`; `agent_writable_roots` and
  `agent_writable_globs` are gone from `REQUIRED_CONFIG`, from `~/bin/warrant`
  and from `~/.config/warrant/config.json`.
- Recognized filters, exactly: `(subpath|literal (string-append (param "_HOME") "/REL"))`,
  `(subpath|literal "/ABS")`, `(subpath (param "_PROJECT_DIR"))`,
  `(subpath (param "_TMPDIR"))`. Any other sub-form of an allow-write form
  (`regex`, `prefix`, `require-all`, an unknown param) raises `Refused` naming
  the form; so does an unreadable profile or one yielding zero roots.
- `preflight()` refuses when `~/bin/warrant`, its interpreter,
  `~/.config/warrant`, `~/.config/seatbelt/ai-agents.sb` or `~/bin/run-agent`
  resolves under a parsed root.
- `~/bin/tests/test_warrant.py` builds its `Site` from an explicit root tuple;
  the glob test is removed with the feature; every other existing test name
  stays; the new parser and preflight tests listed under Success Criteria pass
  inside the sandbox.
- `~/bin/tests/test_warrant_mirror.py` is deleted. Premise: it is the PRD
  00160 drift test (its docstring starts `Drift check:`); re-check before
  deleting, skip and report if the file differs.

### Nice to have
- None. Regex-grant support and the `_PROJECT_DIR` request field are
  deliberately deferred (discovery 00162).

## Implementation

### Module: warrant
- **Location**: `~/bin/warrant`
- **Responsibility**: parse write grants from the profile, hold them on
  `Site`, answer `agent_writable()`, extend `preflight()`.
- **Exports**: `PROFILE` (constant beside `NOTIFY_HOOK`:
  `Path.home() / ".config" / "seatbelt" / "ai-agents.sb"`), `LAUNCHER`
  (`Path.home() / "bin" / "run-agent"`), `write_grants(text, home)` (pure:
  profile text plus resolved home to a tuple of resolved roots, raises
  `Refused` on an unreadable form or zero roots), `load_profile(path, home)`
  (reads the file, `OSError` becomes `Refused`, delegates to `write_grants`),
  `Site.writable` (`tuple[Path, ...]`, default `()`, so the agent side's
  `Site(SPOOL, CONFIG_DIR)` keeps working), `agent_writable(site, path)`
  (`any(path == root or root in path.parents for root in site.writable)`).
  `main()` builds the human-side `Site` with
  `load_profile(PROFILE, Path.home().resolve())` before `preflight(site)`.
  The module docstring's trust-boundary paragraph names the profile as the
  source of the roots.
- New symbols: `PROFILE`, `LAUNCHER`, `write_grants`, `load_profile`, `writable`

### Module: test_warrant
- **Location**: `~/bin/tests/test_warrant.py`
- **Responsibility**: existing broker tests on an explicit root tuple, plus
  parser, live-profile and preflight tests in a new `ProfileCase`.
- **Exports**: none (tests). `setUp` passes
  `writable=(self.agentw.resolve(),)`; `test_preflight_refuses_agent_writable_config_dir`
  forwards `writable=self.site.writable` when it rebuilds the `Site`;
  `test_executable_matching_agent_writable_glob_is_refused` is removed.
- New symbols: `ProfileCase`, `test_home_relative_and_absolute_grants_become_roots`, `test_runtime_params_are_skipped_not_refused`, `test_unreadable_grant_refuses_and_names_the_form`, `test_deny_forms_and_read_grants_yield_no_root`, `test_missing_or_grantless_profile_refuses`, `test_live_profile_parses_completely`, `test_live_profile_path_matches_run_agent`, `test_preflight_refuses_a_profile_that_grants_its_own_directory`, `test_preflight_refuses_a_grant_over_run_agent`

### Module: config
- **Location**: `~/.config/warrant/config.json` (unreadable from the sandbox;
  edited by the human on the host)
- **Responsibility**: policy only: `trusted_exe_roots`, `exec_path`,
  `allowed_env`, `inherit_env`, `request_ttl_sec`, `exec_timeout_sec`.
- **Exports**: none

### Dependencies
- warrant: No dependencies (stdlib `re`, `pathlib`; `fnmatch` removed)
- test_warrant: Depends on [warrant], loads it by path as today
- config: Depends on [warrant] (keys dropped only after the new binary is in place)

## Tasks

Staging dir for the agent side: `~/.claude/docs/dev/tmp/00163-stage/bin/`
with `warrant` and `tests/test_warrant.py`, the layout `test_warrant.py`
expects (`WARRANT = parent.parent / "warrant"`). Suite command, run from
inside the sandbox:
`/opt/homebrew/bin/python3 -m unittest discover -s <stage>/bin/tests -t <stage>/bin/tests -p 'test_warrant.py'`.

### Phase 0: Stage and test (agent, inside the sandbox)
- [x] (2026-10-17, baseline 36/36 green in the sandbox) Copy `~/bin/warrant` and `~/bin/tests/test_warrant.py` into the staging
  layout - the staged suite is green before any edit.
- [x] (2026-10-17; `grants_write()` and four filter regexes added beside the named symbols) In the staged `warrant`: add `PROFILE`, `LAUNCHER`, `write_grants()`,
  `load_profile()`, `Site.writable`; repoint `agent_writable()`; extend
  `preflight()`; drop the two keys from `REQUIRED_CONFIG` and the `fnmatch`
  import; build the human-side `Site` in `main()` from `load_profile`; update
  the docstring - `rg -n "agent_writable_roots|agent_writable_globs|fnmatch" <stage>/bin/warrant`
  prints nothing while `rg -n "agent_writable" <stage>/bin/warrant` still
  prints the four call sites and the definition.
- [x] (2026-10-17, 44/44 green in the sandbox: 36 minus the glob test plus nine `ProfileCase` tests) In the staged `test_warrant.py`: `setUp` root tuple, the preflight test
  forwards `writable`, the glob test is removed, `ProfileCase` added with the
  nine tests named above; the live tests read the real `~/.config/seatbelt/ai-agents.sb`
  and `~/bin/run-agent` and skip only when the file is absent - the staged
  suite is green inside the sandbox.

Exit criteria: staged suite green; both `rg` checks above hold. Met
2026-10-17; the unreadable-grant test also covers an unfiltered
`(allow file-write*)`, `(allow default)` and `(allow file*)`, each of which
would otherwise be a silent wholesale grant the parser skipped.

### Phase 1: Deploy (human on the host, or warrant requests the human approves)
Submitted 2026-10-17 as warrant requests `79e50bf6…` (cp warrant),
`87c9e395…` (cp tests), `04d06838…` (rm mirror test); the premise check named
the file. Commit `7fae2ab4…` and push `202c5fa6…` submitted after the user
reported the config edit done.
- [x] (2026-10-17, approved on the host; `diff` of both deployed files against
  the staged copies is empty) `cp <stage>/bin/warrant ~/bin/warrant` and
  `cp <stage>/bin/tests/test_warrant.py ~/bin/tests/test_warrant.py` (depends
  on: Phase 0) - `~/bin/warrant list` passes preflight against the real
  profile and prints the spool or `spool empty`.
- [x] (2026-10-17, `~/bin/tests` holds only `test_warrant.py`; the host suite
  run is the user's, not observed from the sandbox) `rm ~/bin/tests/test_warrant_mirror.py` after the premise re-check
  `rg -l "Drift check" ~/bin/tests/test_warrant_mirror.py` names the file -
  `/opt/homebrew/bin/python3 -m unittest discover -s ~/bin/tests -t ~/bin/tests -p 'test_warrant*.py'`
  is green on the host with no skipped test.
- [x] (2026-10-17, done by the user on the host; unverifiable from the
  sandbox, where git shows the deny-read file as deleted) `jq 'del(.agent_writable_roots, .agent_writable_globs)' ~/.config/warrant/config.json`
  written back in place - `jq 'has("agent_writable_roots")' ~/.config/warrant/config.json`
  prints `false`; `~/bin/warrant list` still passes preflight. Left over: the
  file's `_comment` still calls it a mirror of the profile; reword it on the
  host before or after the commit.
- [x] (2026-10-17, buvis `b1cea72e`, 4 files, mirror test deleted, pushed
  `f0d0c7fe..b1cea72e`; the `_comment` rewording follows as its own commit) One commit for the four paths, then push:
  `git --git-dir=~/.buvis --work-tree=~ commit -m "feat(warrant): derive agent-writable roots from the Seatbelt profile" -- ':(top)bin/warrant' ':(top)bin/tests/test_warrant.py' ':(top)bin/tests/test_warrant_mirror.py' ':(top).config/warrant/config.json'`
  - `git --git-dir=~/.buvis --work-tree=~ show --stat HEAD` lists exactly
  those four paths, the mirror test as deleted; never stage
  `passphrase.scrypt` or `ledger.jsonl`.

Exit criteria: host suite green, config without the two keys, commit pushed.
Met 2026-10-17. Hand-off lesson recorded in `~/.claude/AGENTS.md` (Handing
work to the user): the config-comment fix was listed below the approve
commands and was skipped; it ships in the follow-up commit.

## Success Criteria

- Parser and preflight behavior is pinned by
  `test_home_relative_and_absolute_grants_become_roots`,
  `test_runtime_params_are_skipped_not_refused`,
  `test_unreadable_grant_refuses_and_names_the_form` (a `prefix` filter, a
  `regex` grant, a `require-all` form and `(subpath (param "_X"))` each raise
  `Refused` whose message contains the offending form),
  `test_deny_forms_and_read_grants_yield_no_root`,
  `test_missing_or_grantless_profile_refuses`,
  `test_preflight_refuses_a_profile_that_grants_its_own_directory` and
  `test_preflight_refuses_a_grant_over_run_agent`, all green inside the
  sandbox.
- `test_live_profile_parses_completely` parses the real profile with zero
  unread forms and finds the resolved `~/.claude` and `/private/tmp` among the
  roots and not `~/bin`; `test_live_profile_path_matches_run_agent` reads the
  `SANDBOX_PROFILE=` line of `~/bin/run-agent` and asserts it names `PROFILE`.
- The 00159 trust tests keep passing on the new root source:
  `test_executable_in_agent_writable_root_is_refused`,
  `test_symlink_in_agent_writable_root_runs_the_reviewed_target`,
  `test_small_agent_writable_file_head_is_shown`,
  `test_agent_writable_cwd_is_flagged`, `test_trusted_cwd_is_not_flagged`,
  `test_preflight_refuses_agent_writable_config_dir`.
- On the host: `~/bin/warrant list` passes preflight, `config.json` has no
  `agent_writable_*` key, `test_warrant_mirror.py` is gone, and the buvis
  commit is pushed.

## Risks

- **A grant the parser misreads** is the one failure that matters, since a
  missed grant makes warrant trust a path agents can write. Every sub-form of
  an allow-write form must be recognized or the broker refuses; the live
  test fails the moment the profile gains a shape the parser lacks.
- **Sessions running under an older profile** keep older grants until they
  exit; reading today's profile under-approximates for them. Shared with the
  mirror; restart sessions after tightening the profile.
- **`Path.parents` versus Seatbelt `subpath`**: both are component-prefix
  matches on real paths; `"/private/tmp/"` normalizes in `Path`. Pinned by
  `test_home_relative_and_absolute_grants_become_roots`.
- **Two hardcodes of one path** (run-agent and warrant) are tied together by
  `test_live_profile_path_matches_run_agent`.
