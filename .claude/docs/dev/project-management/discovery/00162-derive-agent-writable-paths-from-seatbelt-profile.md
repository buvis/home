# Discovery: Derive Agent-Writable Paths From the Seatbelt Profile

## Classification

Depth: standard | Date: 2026-10-17 | Status: done as PRD 00163
(`prds/done/00163-derive-agent-writable-roots-from-seatbelt-profile-v1.md`,
buvis `b1cea72e`); open question 1 deferred there as out of scope
Seeded from the user's premise of 2026-10-17: warrant should not rely on its
config to know which paths an agent can write; the Seatbelt profile already
says so. Written from a sandboxed session, so `~/.config/warrant/config.json`
was not read; its shape comes from PRD 00159 and `~/bin/warrant`.

## Premise check

**Confirmed.** `~/bin/run-agent` is the only sandbox launcher and it passes
exactly one profile, `~/.config/seatbelt/ai-agents.sb`, to `sandbox-exec`.
That file is the sole authority on what an agent can write. Warrant's
`agent_writable_roots` and `agent_writable_globs` in `config.json` are a hand
copy of its `(allow file-write* ...)` forms. PRD 00160 Phase 1 (buvis
`f0d0c7fe`, this morning) added a drift test instead of removing the copy, and
that test only runs on the host and only when someone runs it. Between a
profile edit and the next test run, `approve` trusts a stale mirror.

The profile is as trustworthy as the config it would replace: `~/.config/seatbelt`
appears in no write grant, so an agent cannot edit it, and the host-side
`approve` can read it. Parsing it is stdlib work and already exists: the mirror
test's `write_allow_forms()` plus three regexes read every grant in the live
profile today with zero unparsed forms.

Three bounds hold the premise short of "the profile answers everything":

1. **Two grants are per-session parameters.** `_PROJECT_DIR` and `_TMPDIR`
   are set by run-agent at launch and unknown to the broker. `_TMPDIR` lands
   under `/private/var/folders/`, which the profile also grants literally, so
   it is covered. `_PROJECT_DIR` is not, and never was in the mirror either;
   the 00159 review closed the executable case with `trusted_exe_roots`, and
   file arguments and cwd inside an unusual project dir stay a documented gap
   (open question 1).
2. **A profile edit does not reach running sessions.** A session launched
   yesterday still holds yesterday's grants (the mise directories, until it
   exits). Reading today's profile under-approximates for it. The mirror had
   the same property, since it was edited in lockstep. Not a regression; a
   shared limitation to state.
3. **Only an over-approximation is needed.** Warrant asks "could an agent have
   written here?" and every use of the answer tightens on yes: preflight
   refuses, `resolve_exe` refuses, file heads get shown and re-hashed, cwd gets
   a warning. Ignoring the profile's `deny file-write*` carve-outs
   (`.git/hooks`, `.mcp.json` under `~/git/src`) is therefore safe, and the
   parser needs only `allow` forms.

## Problem

Two files encode one fact. The mirror can lag the profile and the broker has
no way to notice at approve time. The drift test narrows the window but
leaves the wrong source of truth in place: warrant trusts a copy of the
policy rather than the policy.

## Requirements (proposed)

### Must have

1. **One source of truth.** `agent_writable()` answers from the parsed
   profile; `agent_writable_roots` and `agent_writable_globs` leave
   `config.json` and `REQUIRED_CONFIG`. The profile path is a constant next to
   `NOTIFY_HOOK`, the same path run-agent hardcodes.
2. **Fail closed on anything unread.** Any `(allow file-write* ...)` sub-form
   other than `(subpath|literal (string-append (param "_HOME") "..."))`,
   `(subpath|literal "/abs")` and `(subpath (param "_PROJECT_DIR"|"_TMPDIR"))`
   makes `approve`, `list` and `init` refuse to broker, naming the form. A
   missing or unreadable profile refuses the same way `config.json` lacking a
   key does today. No regex grants exist since buvis `14f93f50`; support for
   `(regex ...)` waits until one returns and comes with dialect tests.
3. **Resolve as Seatbelt does.** Each parsed root is `expanduser`-free (the
   parser substitutes `_HOME` with the resolved home, as run-agent passes
   `pwd -P` of `$HOME`) and `.resolve()`d, since Seatbelt matches real paths
   and `/tmp`, `/var` and `~/.claude/projects` are symlinks here.
4. **Preflight covers the profile itself.** A profile that grants writes to
   `~/.config/seatbelt`, `~/bin/run-agent`, `~/bin/warrant`, the interpreter
   or `~/.config/warrant` means an agent could rewrite its own sandbox or its
   broker; refuse to broker, as preflight does for the last three today.
5. **Tests move, not multiply.** `test_warrant.py` builds its `Site` from a
   fixture profile string instead of config roots; `test_warrant_mirror.py` is
   deleted and its parser cases (unreadable filter, regex grant, dropped root)
   become parser tests. One test reads the live profile and asserts zero
   unparsed forms; it runs inside the sandbox too, since the profile is
   readable there.

### Out of scope

- Changing any grant in the profile.
- The `_PROJECT_DIR` gap (open question 1); it is independent of where the
  roots come from.
- Deny carve-outs. Honoring them would only loosen warrant.
- The warrant notify defect and the 00161 auto-approver; both unchanged.

### Success Criteria

- `config.json` holds no `agent_writable_*` key and `~/bin/warrant list`
  passes preflight on the host against the real profile.
- Adding `(allow file-write* (subpath (string-append (param "_HOME") "/.config/warrant")))`
  to a temp copy of the profile and pointing warrant at it makes preflight
  refuse with no config change; the same for `~/.config/seatbelt` and `~/bin`.
- A temp profile with `(allow file-write* (prefix "/opt"))` or a regex grant
  refuses to broker and names the form.
- A request naming a file under `~/.claude` prints `AGENT-WRITABLE` and its
  head; one naming a file under `~/bin` prints neither.
- `test_warrant.py` green; `test_warrant_mirror.py` gone.

## Evidence (2026-10-17)

- `run-agent:8,113-118`: profile path hardcoded, parameters `_HOME`
  (`pwd -P` of `$HOME`), `_PROJECT_DIR` (git root or cwd), `_TMPDIR`.
- `ai-agents.sb:106-120,157-207`: every write grant is `subpath` or `literal`
  on `_HOME`-relative or absolute strings, plus `(subpath (param "_PROJECT_DIR"))`
  and `(subpath (param "_TMPDIR"))`. Zero regex grants since `14f93f50`.
- `warrant:174-184`: `agent_writable()` reads the two config keys and
  `fnmatch`es globs; called from `preflight`, `resolve_exe`, `file_args`,
  `show`. Four callers, one function to repoint.
- `test_warrant_mirror.py:35-69`: `write_allow_forms()` strips comments,
  splits top-level forms, keeps `(allow file-write* ...)`; `drift()` counts
  filters and reports any it cannot read. This is the parser; it moves.
- Kernel query probed from this session via `ctypes` on
  `libsystem_sandbox.dylib`: `sandbox_check(pid, "network-outbound", 0)`
  answers 0 (allowed), but every path-filtered call returns -1 with
  `errno 22`, with and without `SANDBOX_CHECK_NO_REPORT`, likely the arm64
  variadic ABI through ctypes or a changed filter enum. Private API, and the
  approver runs where no sandboxed pid exists, so it would need a
  `sandbox-exec` helper per approve. Not pursued (Discovery Log).
- Size: parser about 40 lines into `warrant`, minus `fnmatch` and the glob
  branch; `test_warrant_mirror.py` (104 lines) deleted; two config keys
  removed; about ten `setUp` lines change in `test_warrant.py`.

## Risks

- **A grant the parser misreads.** The one failure that matters, since a
  missed grant makes warrant trust a path agents can write. Mitigation: the
  filter count check (every sub-form must be recognized), refusal on mismatch,
  and the live-profile test. A grant can be added to the profile only by the
  human, who sees the refusal on the next `approve`.
- **Running sessions under an older profile** (bound 2). Restart sessions
  after tightening the profile; no code answer short of per-session grant
  hashes, which the agent would control.
- **Semantic drift between `Path.parents` and Seatbelt `subpath`.** Both are
  component-prefix matches on the real path; trailing slashes in the profile
  (`"/private/tmp/"`) normalize away in `Path`. A test pins both.
- **Two hardcodes of one path** (run-agent and warrant). One assertion in the
  live-profile test reads run-agent's `SANDBOX_PROFILE=` line and compares.

## Discovery Log (2026-10-17)

### Source: parse the profile, not the kernel

- (a) **Parse `ai-agents.sb` at approve time.** Accepted. The parser exists,
  the grammar in use is three shapes, unknown shapes refuse. Stdlib only.
- (b) **Ask the kernel with `sandbox_check()`.** Rejected for now: private
  API, path-filtered calls failed from this session (Evidence), and the
  approver is unsandboxed so it would spawn a sandboxed helper per request. A
  one-hour spike could settle viability if the parser ever cannot express a
  grant; until then it buys nothing.
- (c) **Probe by opening paths inside a sandboxed child.** Rejected: creating
  a file is a side effect, nested `sandbox-exec` is refused inside sessions
  (PRD 00160 findings), and the approver would again need a helper.
- (d) **Keep the mirror and the drift test.** Rejected by the premise, and the
  evidence agrees: it fixes the symptom (drift noticed later) and not the
  cause (two sources of truth).

### Decisions taken here

- Profile path is a constant, not a config key; a value that never changes.
- `literal` roots match by equality or ancestry like `subpath`; the only
  literal grant (`~/.claude.json`) is a file, so the difference is moot and
  the conservative branch is one condition shorter.
- Regex grants fail closed until one exists to test against.
- Deny forms are ignored on purpose (bound 3).

## Open questions

1. `_PROJECT_DIR`: leave the gap documented, or have run-agent export the
   resolved project dir and `warrant request` carry it so the broker treats
   it as writable? A lying agent can only make warrant stricter, so it is
   safe; it costs a run-agent change and a request field, both outside this
   doc's scope.

## Next step

`/create-prd` for one PRD: parser into `~/bin/warrant`, config keys and
`test_warrant_mirror.py` removed, tests rehomed, preflight extended. Deploy
is a human act as in 00159 Phase 1: `~/bin` and `~/.config/warrant` are
written only through warrant. Record question 1 in the PRD's open questions
rather than deciding it there.
